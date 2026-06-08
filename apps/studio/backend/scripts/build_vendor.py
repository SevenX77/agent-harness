#!/usr/bin/env python3
"""Install Studio backend dependencies into the Tauri vendor layout."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
STUDIO_DIR = BACKEND_DIR.parent
DEFAULT_REQUIREMENTS = BACKEND_DIR / "requirements.txt"
DEFAULT_TARGET = STUDIO_DIR / "tauri" / "vendor" / "site-packages"


def _build_local_requirement_wheel(requirement_path: Path, wheelhouse: Path) -> Path:
    before = set(wheelhouse.glob("*.whl"))
    command = [
        "uv",
        "build",
        "--wheel",
        "--out-dir",
        str(wheelhouse),
        str(requirement_path),
    ]
    subprocess.run(command, check=True)
    new_wheels = sorted(set(wheelhouse.glob("*.whl")) - before)
    if not new_wheels:
        raise SystemExit(f"local requirement did not build a wheel: {requirement_path}")
    return new_wheels[-1]


def _resolved_requirements_text(requirements: Path, wheelhouse: Path) -> str:
    base_dir = requirements.parent
    resolved_lines: list[str] = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(("./", "../")):
            indentation = line[: len(line) - len(line.lstrip())]
            wheel = _build_local_requirement_wheel((base_dir / stripped).resolve(), wheelhouse)
            resolved_lines.append(f"{indentation}{wheel}")
        else:
            resolved_lines.append(line)
    return "\n".join(resolved_lines) + "\n"


def _assert_bundle_safe_vendor(target: Path) -> None:
    editable_paths = sorted(target.glob("_editable*.pth"))
    if editable_paths:
        names = ", ".join(path.name for path in editable_paths)
        raise SystemExit(f"editable vendor paths are not bundle-safe: {names}")


def install_vendor(requirements: Path, target: Path, *, clean: bool = True) -> None:
    if not requirements.exists():
        raise SystemExit(f"requirements file not found: {requirements}")
    if clean:
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="studio-vendor-requirements.") as temp_dir:
        wheelhouse = Path(temp_dir) / "wheels"
        wheelhouse.mkdir()
        resolved_requirements = Path(temp_dir) / requirements.name
        resolved_requirements.write_text(
            _resolved_requirements_text(requirements, wheelhouse),
            encoding="utf-8",
        )
        command = [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--requirement",
            str(resolved_requirements),
            "--target",
            str(target),
            "--upgrade",
        ]
        subprocess.run(command, check=True)
    _assert_bundle_safe_vendor(target)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        type=Path,
        default=DEFAULT_REQUIREMENTS,
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
    )
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args(argv)
    install_vendor(args.requirements, args.target, clean=not args.no_clean)


if __name__ == "__main__":
    main()
