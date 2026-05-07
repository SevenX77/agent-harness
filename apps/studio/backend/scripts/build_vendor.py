#!/usr/bin/env python3
"""Install Studio backend dependencies into the Tauri vendor layout."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
STUDIO_DIR = BACKEND_DIR.parent
DEFAULT_REQUIREMENTS = BACKEND_DIR / "requirements.txt"
DEFAULT_TARGET = STUDIO_DIR / "tauri" / "vendor" / "site-packages"


def install_vendor(requirements: Path, target: Path, *, clean: bool = True) -> None:
    if not requirements.exists():
        raise SystemExit(f"requirements file not found: {requirements}")
    if clean:
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--requirement",
        str(requirements),
        "--target",
        str(target),
        "--upgrade",
    ]
    subprocess.run(command, check=True)


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
