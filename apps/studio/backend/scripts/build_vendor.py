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
"""

from __future__ import annotations

import argparse
import logging
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[build_vendor] %(message)s")
logger = logging.getLogger("build_vendor")

BACKEND_DIR = Path(__file__).resolve().parents[1]
STUDIO_DIR = BACKEND_DIR.parent
DEFAULT_TARGET = STUDIO_DIR / "tauri" / "vendor" / "site-packages"

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
    logger.info("vendored backend closure (%d local pkgs) into %s", len(local_paths), target)


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
