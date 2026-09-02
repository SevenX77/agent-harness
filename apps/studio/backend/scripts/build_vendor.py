#!/usr/bin/env python3
"""Install the Studio backend dependency closure into the Tauri vendor layout.

The backend is a uv workspace member whose real dependencies (``graph-agent``,
``graph-agent-gateway`` and their langchain/langgraph/anthropic/openai closure)
are NOT expressible in a hand-maintained ``requirements.txt`` -- they include the
local workspace packages under ``packages/``. So vendoring is driven from the uv
workspace (the single source of truth) via ``uv export`` + ``uv pip install``.

Two correctness rules this script enforces (both were latent bugs before):
  1. Install for the *vendored* CPython (downloaded by ``download_runtime.js``),
     not whatever interpreter runs this script -- native wheels (pydantic-core,
     etc.) must match the runtime ABI.
  2. Install the full workspace closure, including the local ``graph-agent`` /
     ``graph-agent-gateway`` packages, so the bundled sidecar can ``import
     graph_agent`` at startup.

The build also leaves a provenance stamp (``vendor-stamp.json``) inside the
snapshot. See ``build_stamp`` for what it records and why.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

logging.basicConfig(level=logging.INFO, format="[build_vendor] %(message)s")
logger = logging.getLogger("build_vendor")

BACKEND_DIR = Path(__file__).resolve().parents[1]
STUDIO_DIR = BACKEND_DIR.parent
DEFAULT_TARGET = STUDIO_DIR / "tauri" / "vendor" / "site-packages"

STAMP_FILENAME = "vendor-stamp.json"
STAMP_SCHEMA = 2

_TRIPLE_BY_HOST: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "aarch64-apple-darwin",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("windows", "amd64"): "x86_64-pc-windows-msvc",
}


def host_target_triple() -> str:
    key = (platform.system().lower(), platform.machine().lower())
    triple = _TRIPLE_BY_HOST.get(key)
    if triple is None:
        raise SystemExit(f"unsupported host for vendoring: {key}")
    return triple


def find_workspace_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / "uv.lock").exists():
            return parent
    raise SystemExit(f"uv.lock not found above {start}; cannot resolve workspace root")


def default_vendored_python(studio_dir: Path) -> Path:
    runtime = studio_dir / "tauri" / "vendor" / "python" / host_target_triple()
    candidates = [runtime / "bin" / "python3.12", runtime / "bin" / "python3"]
    if platform.system().lower() == "windows":
        candidates = [runtime / "python.exe"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(
        f"vendored python not found under {runtime}; run download_runtime.js first"
    )


def export_closure(workspace_root: Path, out_file: Path) -> None:
    command = [
        "uv", "export", "--package", "studio-backend",
        "--no-hashes", "--no-emit-project", "--no-editable",
        "--format", "requirements-txt", "-o", str(out_file),
    ]
    logger.info("exporting studio-backend closure -> %s", out_file)
    subprocess.run(command, check=True, cwd=workspace_root)


def split_local_paths(requirements: Path) -> tuple[list[str], Path]:
    """Separate local workspace path deps from the third-party requirements.

    Local path deps (``./packages/...``) installed via ``-r`` land as editable
    ``.pth`` shims, which are NOT executed inside a ``--target`` dir mounted on
    PYTHONPATH (only real site dirs run ``.pth``). So they are stripped here and
    re-installed as built wheels.
    """
    local: list[str] = []
    kept: list[str] = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(("./", "../")):
            local.append(line.strip())
        else:
            kept.append(line)
    filtered = requirements.with_name("requirements.thirdparty.txt")
    filtered.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return local, filtered


def install_thirdparty(*, python: Path, requirements: Path, target: Path, root: Path) -> None:
    command = [
        "uv", "pip", "install",
        "--python", str(python), "--target", str(target), "-r", str(requirements),
    ]
    logger.info("installing third-party closure into %s for %s", target, python)
    subprocess.run(command, check=True, cwd=root)


def wheel_package_files(wheel: Path) -> dict[str, dict[str, str]]:
    """``{package name: {path inside the package: sha256}}`` for one wheel.

    This is the ONLY place that decides which files belong to a vendored
    package, and it decides by reading what the build backend actually put in
    the wheel -- never by re-deriving hatchling's file selection here.

    The distinction is not academic. Hatchling honours the repo's VCS ignore
    files, so ``packages/graph-agent/src/graph_agent/_native.pyd`` (root
    ``.gitignore``: ``*.py[cod]``) is NOT shipped, while a dotfile inside the
    package IS -- the opposite of what an "obvious" walk of the source tree
    assumes on both counts. A hand-written filter that guesses wrong fails in
    one of two ways: it lets a shipped file drift unnoticed, or it demands a
    file the wheel will never contain, which no rebuild can satisfy (P11/#732:
    a gate that cannot be satisfied stops the app from starting at all).

    ``*.dist-info`` and ``*.data`` are skipped because they are installer
    metadata about the distribution rather than files of the package; a
    top-level module file is rejected outright rather than guessed at, since
    this script has no source directory to map it back to.

    The shape -- a sorted ``path -> hash`` manifest -- is borrowed from a
    wheel's own ``RECORD`` (PEP 376). What is not borrowed is reading ``RECORD``
    itself: it stores base64 digests describing the INSTALLED tree, and the
    question here is what the ARCHIVE carries, which the archive answers
    directly.
    """
    packages: dict[str, dict[str, str]] = {}
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            parts = PurePosixPath(entry.filename).parts
            if parts[0].endswith((".dist-info", ".data")):
                continue
            if len(parts) == 1:
                raise SystemExit(
                    f"{wheel.name} ships the top-level file {parts[0]}; this script maps a "
                    "wheel to its sources one package directory at a time and has nowhere "
                    "to put a bare module"
                )
            packages.setdefault(parts[0], {})[str(PurePosixPath(*parts[1:]))] = hashlib.sha256(
                archive.read(entry)
            ).hexdigest()
    return packages


def manifest_digest(files: dict[str, str]) -> str:
    """One digest for a package's whole shipped file set.

    Content-addressed, following Bazel's and Nix's treatment of build inputs: an
    input is identified by what it contains, never by where it sits or when it
    was last touched. That is the property that makes the value comparable at
    all -- mtimes and absolute paths differ on every machine and every checkout,
    so a digest that included them could never be matched against anything.

    Paths are hashed alongside contents, so a pure rename moves the digest.
    """
    manifest = "".join(f"{path}\0{files[path]}\n" for path in sorted(files))
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def hatch_package_dirs(project_dir: Path) -> dict[str, str]:
    """``{package name: project-relative source dir}`` from the project's own config.

    ``[tool.hatch.build.targets.wheel] packages`` is the mapping hatchling
    itself uses to decide where a wheel's ``graph_agent/`` came from, so reading
    it is asking the authority rather than assuming ``src/<name>``. A project
    that does not declare it is rejected loudly: guessing would put a wrong path
    in the stamp, and the launcher gate would then compare the snapshot against
    a directory that is not its source.
    """
    config = tomllib.loads((project_dir / "pyproject.toml").read_text(encoding="utf-8"))
    targets = config.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {})
    declared = targets.get("wheel", {}).get("packages")
    if not declared:
        raise SystemExit(
            f"{project_dir / 'pyproject.toml'} declares no [tool.hatch.build.targets.wheel] "
            "packages, so the vendor stamp cannot say where this wheel's sources live"
        )
    return {PurePosixPath(entry).name: str(PurePosixPath(entry)) for entry in declared}


def install_local_wheels(
    *, python: Path, local_paths: list[str], target: Path, root: Path
) -> dict[str, dict[str, object]]:
    """Build and install the local workspace packages; return what they ship.

    Each wheel is built into its own directory so the package it carries can be
    tied back to the project that produced it. That mapping is what lets the
    stamp record a source root per package, which in turn is what frees the
    launcher gate from keeping its own hand-maintained list of SDK packages.
    """
    if not local_paths:
        return {}
    packages: dict[str, dict[str, object]] = {}
    with tempfile.TemporaryDirectory(prefix="studio-vendor-wheels-") as tmp:
        wheels: list[str] = []
        for index, relative in enumerate(local_paths):
            project_dir = root / relative
            wheel_dir = Path(tmp) / str(index)
            logger.info("building wheel for local workspace package %s", relative)
            subprocess.run(
                ["uv", "build", "--wheel", str(project_dir), "-o", str(wheel_dir)],
                check=True, cwd=root,
            )
            built = sorted(wheel_dir.glob("*.whl"))
            if len(built) != 1:
                raise SystemExit(f"expected exactly one wheel for {relative}, got {built}")
            wheels.append(str(built[0]))
            source_dirs = hatch_package_dirs(project_dir)
            for name, files in wheel_package_files(built[0]).items():
                source_dir = source_dirs.get(name)
                if source_dir is None:
                    raise SystemExit(
                        f"{built[0].name} ships {name}, which "
                        f"{project_dir / 'pyproject.toml'} does not list under "
                        "[tool.hatch.build.targets.wheel] packages"
                    )
                packages[name] = {
                    # Workspace-relative and POSIX-spelled: the stamp ships to
                    # machines that have neither this checkout nor this OS.
                    "source_root": (PurePosixPath(*Path(relative).parts) / source_dir).as_posix(),
                    "digest": manifest_digest(files),
                    "files": files,
                }
        logger.info("installing %d local wheel(s) into %s", len(wheels), target)
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--target", str(target),
             "--no-deps", "--reinstall", *wheels],
            check=True, cwd=root,
        )
    return packages


def build_stamp(
    *,
    packages: dict[str, dict[str, object]],
    built_at: str,
    python_version: str,
    target_triple: str,
) -> dict[str, object]:
    """The snapshot's account of what it was built from.

    The desktop app's sidecar imports ``graph_agent`` / ``graph_agent_gateway``
    from this frozen snapshot in dev builds too, so "which engine am I running"
    is a real question with no other answer. On an installed app there is no
    working tree, and without this file the snapshot is anonymous -- neither the
    app nor a bug report about it can name the source state it carries.

    It is also what the launcher gate compares against. Every file the wheels
    shipped is listed with its hash, so the gate can ask both halves of the
    freshness question -- "do the sources still match what was built?" and "does
    the snapshot still hold what was installed?" -- without enumerating either
    tree, and therefore without inventing a second opinion about which files a
    package consists of.

    Deliberately absent: the absolute path of the interpreter that built it, and
    of the checkout it was built from. The stamp ships inside the installer
    (``bundle.resources: vendor/**/*``), a build-machine path tells a user
    nothing, and baking one into a shipped file is the mistake
    ``verify_installed_sidecar.ps1`` exists to catch elsewhere. Source roots are
    recorded relative to the workspace root for the same reason. The interpreter
    VERSION stays, because that is the ABI the vendored native wheels were built
    against.
    """
    ordered = dict(sorted(packages.items()))
    combined = "".join(f"{name}\0{info['digest']}\n" for name, info in ordered.items())
    return {
        "schema": STAMP_SCHEMA,
        "source_digest": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        "packages": ordered,
        "built_at": built_at,
        "python_version": python_version,
        "target_triple": target_triple,
    }


def write_stamp(target: Path, stamp: dict[str, object]) -> Path:
    """Write the stamp INSIDE the snapshot it describes.

    Not one level up in ``vendor/``: ``build_vendor(clean=True)`` removes the
    target before installing, so a stamp stored outside it would survive a build
    that then failed and go on describing a snapshot that no longer exists.
    Inside, its lifetime is exactly the snapshot's -- a wiped snapshot correctly
    reports "no provenance" and the launcher gate rebuilds it.
    """
    path = target / STAMP_FILENAME
    path.write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def discard_stamp(target: Path) -> None:
    """Drop the old provenance BEFORE touching anything it describes.

    Every later step can fail: the clean can be blocked by a file lock, the
    export can fail, a wheel can fail to build. Whatever happens after this
    point, the snapshot is no longer the one the old stamp attested to -- so the
    stamp goes first, and an interrupted build leaves a snapshot that honestly
    reports "no provenance" instead of one wearing a label it no longer earns.
    The launcher gate reads that as stale and rebuilds; the old behaviour left
    it reading a lie as proof of freshness.
    """
    stamp = target / STAMP_FILENAME
    try:
        stamp.unlink(missing_ok=True)
    except OSError as error:
        raise SystemExit(f"cannot remove the old provenance stamp {stamp}: {error}") from error


def remove_snapshot(target: Path) -> None:
    """Delete the snapshot, and prove it is gone.

    ``ignore_errors=True`` was the bug: on Windows the running desktop app holds
    the vendored ``.pyd``/``.dll`` files open, so the removal silently removed
    nothing and the build carried on installing over the remains of the snapshot
    it believed it had wiped. A clean that cannot clean is a build that cannot
    be trusted, so it fails here, naming the usual cause.
    """
    if not target.exists():
        return
    try:
        shutil.rmtree(target)
    except OSError as error:
        raise SystemExit(
            f"cannot clean the vendor snapshot at {target}: {error}. On Windows a running "
            "desktop app holds the vendored .pyd/.dll files open -- close it and run this again"
        ) from error
    if target.exists():
        raise SystemExit(
            f"the vendor snapshot at {target} survived its own removal; something still holds "
            "files in it open (close the desktop app and run this again)"
        )


def interpreter_version(python: Path) -> str:
    completed = subprocess.run(
        [str(python), "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def build_vendor(*, python: Path, target: Path, clean: bool = True) -> None:
    if shutil.which("uv") is None:
        raise SystemExit("uv is required to vendor the backend closure; install uv first")
    workspace_root = find_workspace_root(BACKEND_DIR)
    discard_stamp(target)
    if clean:
        logger.info("cleaning target %s", target)
        remove_snapshot(target)
    target.mkdir(parents=True, exist_ok=True)
    requirements = target.parent / "requirements.lock.txt"
    export_closure(workspace_root, requirements)
    local_paths, thirdparty = split_local_paths(requirements)
    install_thirdparty(python=python, requirements=thirdparty, target=target, root=workspace_root)
    packages = install_local_wheels(
        python=python, local_paths=local_paths, target=target, root=workspace_root
    )
    if not packages:
        # A stamp listing no packages would make the launcher gate unsatisfiable
        # (nothing to compare, so "stale" forever), and a snapshot with no SDKs
        # cannot run the sidecar anyway. Fail where the cause is still visible.
        raise SystemExit(
            "the workspace export named no local packages, so the snapshot would carry no "
            "engine for the sidecar to import"
        )

    # Last, and only on a build that got this far: a stamp written before the
    # install could describe a snapshot the install then failed to produce.
    stamp = build_stamp(
        packages=packages,
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        python_version=interpreter_version(python),
        target_triple=host_target_triple(),
    )
    write_stamp(target, stamp)
    logger.info(
        "vendored backend closure (%d local pkgs) into %s, sources %s",
        len(local_paths),
        target,
        str(stamp["source_digest"])[:12],
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=None, help="vendored interpreter")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args(argv)
    python = args.python or default_vendored_python(STUDIO_DIR)
    build_vendor(python=python, target=args.target, clean=not args.no_clean)


if __name__ == "__main__":
    main()
