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
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[build_vendor] %(message)s")
logger = logging.getLogger("build_vendor")

BACKEND_DIR = Path(__file__).resolve().parents[1]
STUDIO_DIR = BACKEND_DIR.parent
DEFAULT_TARGET = STUDIO_DIR / "tauri" / "vendor" / "site-packages"

STAMP_FILENAME = "vendor-stamp.json"
STAMP_SCHEMA = 1

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


def install_local_wheels(*, python: Path, local_paths: list[str], target: Path, root: Path) -> None:
    if not local_paths:
        return
    with tempfile.TemporaryDirectory(prefix="studio-vendor-wheels-") as tmp:
        wheel_dir = Path(tmp)
        for rel in local_paths:
            logger.info("building wheel for local workspace package %s", rel)
            subprocess.run(
                ["uv", "build", "--wheel", str(root / rel), "-o", str(wheel_dir)],
                check=True, cwd=root,
            )
        wheels = sorted(str(path) for path in wheel_dir.glob("*.whl"))
        logger.info("installing %d local wheel(s) into %s", len(wheels), target)
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--target", str(target),
             "--no-deps", "--reinstall", *wheels],
            check=True, cwd=root,
        )


def iter_source_files(root: Path) -> list[str]:
    """Every file the wheel ships for a package, relative, ``/``-separated, sorted.

    ``__pycache__`` and dotfiles are excluded: bytecode is an output of importing
    the tree, not an input to it, and the wheel carries neither. The launcher
    gate's ``collectPackageFiles``
    (``apps/studio/tauri/scripts/ensure_vendor.js``) excludes the same two, so
    the stamp describes the same file set the gate compares.
    """
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part == "__pycache__" or part.startswith(".") for part in relative.parts):
            continue
        files.append(relative.as_posix())
    return sorted(files)


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_tree_digest(root: Path) -> str:
    """One digest for a package's whole source tree.

    Content-addressed, following Bazel's and Nix's treatment of build inputs: an
    input is identified by what it contains, never by where it sits or when it
    was last touched. That is the property that makes the value comparable at
    all -- mtimes and absolute paths differ on every machine and every checkout,
    so a digest that included them could never be matched against anything.

    Paths are part of the digest as well as contents, so a pure rename moves it.
    The layout borrows from a wheel's ``RECORD`` (PEP 376): a sorted
    ``path -> hash`` manifest as the canonical description of an installed tree.
    What it does NOT borrow is ``RECORD`` itself. ``uv pip install`` writes one
    per distribution over the INSTALLED files, which answers "was this install
    corrupted"; the fact needed here is the other one -- which repo state these
    files came from -- and no per-distribution metadata can express it.
    """
    manifest = "".join(f"{relative}\0{hash_file(root / relative)}\n" for relative in iter_source_files(root))
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def package_source_roots(workspace_root: Path, local_paths: list[str]) -> dict[str, Path]:
    """Map module name -> source root for each local workspace path dep.

    Discovered from the ``src/`` layout rather than by turning ``graph-agent``
    into ``graph_agent``: the distribution name and the module name are separate
    facts, and reading the one that exists on disk cannot be wrong about a
    package that spells them differently.
    """
    roots: dict[str, Path] = {}
    for entry in local_paths:
        src = workspace_root / entry.strip() / "src"
        if not src.is_dir():
            continue
        for candidate in sorted(src.iterdir()):
            if (candidate / "__init__.py").is_file():
                roots[candidate.name] = candidate
    return roots


def build_stamp(
    *,
    package_roots: dict[str, Path],
    built_at: str,
    python_version: str,
    target_triple: str,
) -> dict[str, object]:
    """The snapshot's account of what it was built from.

    The desktop app's sidecar imports ``graph_agent`` / ``graph_agent_gateway``
    from this frozen snapshot in dev builds too, so "which engine am I running"
    is a real question with no other answer. On a developer's machine the
    launcher gate answers it by comparing the snapshot against the working tree;
    on an installed app there IS no working tree, and without this file the
    snapshot is anonymous -- neither the app nor a bug report about it can name
    the source state it carries.

    Deliberately absent: the absolute path of the interpreter that built it. The
    stamp ships inside the installer (``bundle.resources: vendor/**/*``), a
    build-machine path tells a user nothing, and baking one into a shipped file
    is the mistake ``verify_installed_sidecar.ps1`` exists to catch elsewhere.
    The interpreter VERSION stays, because that is the ABI the vendored native
    wheels were built against.

    This stamp is provenance, not enforcement. The launcher gate decides
    staleness by comparing the actual bytes in both trees, never by trusting a
    digest recorded here -- a stamp says what a build intended to install, while
    the bytes say what is there.
    """
    packages = {
        name: {"digest": source_tree_digest(root), "files": len(iter_source_files(root))}
        for name, root in sorted(package_roots.items())
    }
    combined = "".join(f"{name}\0{info['digest']}\n" for name, info in packages.items())
    return {
        "schema": STAMP_SCHEMA,
        "source_digest": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        "packages": packages,
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
    if clean:
        logger.info("cleaning target %s", target)
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    requirements = target.parent / "requirements.lock.txt"
    export_closure(workspace_root, requirements)
    local_paths, thirdparty = split_local_paths(requirements)
    install_thirdparty(python=python, requirements=thirdparty, target=target, root=workspace_root)
    install_local_wheels(python=python, local_paths=local_paths, target=target, root=workspace_root)

    # Last, and only on a build that got this far: a stamp written before the
    # install could describe a snapshot the install then failed to produce.
    stamp = build_stamp(
        package_roots=package_source_roots(workspace_root, local_paths),
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
