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
DEFAULT_TARGET = STUDIO_DIR / "tauri" / "vendor" / "site-packages"


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def get_locked_requirements() -> str:
    command = [
        "uv",
        "export",
        "--package",
        "studio-backend",
        "--no-dev",
        "--no-hashes",
        "--no-editable",
        "--frozen",
    ]
    res = subprocess.run(
        command,
        cwd=str(get_repo_root()),
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout


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


def resolve_local_paths(requirements_content: str, wheelhouse: Path) -> str:
    repo_root = get_repo_root()
    resolved_lines: list[str] = []
    for line in requirements_content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("./", "../")):
            indentation = line[: len(line) - len(line.lstrip())]
            absolute_pkg_path = (repo_root / stripped).resolve()
            wheel = _build_local_requirement_wheel(absolute_pkg_path, wheelhouse)
            resolved_lines.append(f"{indentation}{wheel}")
        else:
            resolved_lines.append(line)
    return "\n".join(resolved_lines) + "\n"


def _assert_bundle_safe_vendor(target: Path) -> None:
    editable_paths = sorted(target.glob("_editable*.pth"))
    if editable_paths:
        names = ", ".join(path.name for path in editable_paths)
        raise SystemExit(f"editable vendor paths are not bundle-safe: {names}")


def install_vendor(requirements: Path | None, target: Path, *, clean: bool = True) -> None:
    if clean:
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)

    if requirements is not None:
        if not requirements.exists():
            raise SystemExit(f"requirements file not found: {requirements}")
        requirements_content = requirements.read_text(encoding="utf-8")
        filename_prefix = requirements.name
    else:
        requirements_content = get_locked_requirements()
        filename_prefix = "locked_requirements.txt"

    with tempfile.TemporaryDirectory(prefix="studio-vendor-requirements.") as temp_dir:
        wheelhouse = Path(temp_dir) / "wheels"
        wheelhouse.mkdir()
        resolved_requirements = Path(temp_dir) / filename_prefix
        resolved_requirements.write_text(
            resolve_local_paths(requirements_content, wheelhouse),
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
        default=None,
        help="Path to manual requirements file, defaults to exporting locked packages.",
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
