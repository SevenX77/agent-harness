#!/usr/bin/env python3
"""Fail when codemod review markers remain in V2.1 phase markdown files."""

from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "<!--TODO: CODEMOD_REVIEW"


def scan_roots(roots: list[Path]) -> list[tuple[Path, int]]:
    hits: list[tuple[Path, int]] = []
    for root in roots:
        paths = [root] if root.is_file() else sorted((root / "phases").glob("**/*.md"))
        if not paths and root.is_dir():
            paths = sorted(root.glob("**/*.md"))
        for path in paths:
            if not path.is_file():
                continue
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if MARKER in line:
                    hits.append((path, line_no))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan V2.1 phase markdown for CODEMOD_REVIEW markers.")
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args(argv)

    hits = scan_roots(args.roots)
    for path, line_no in hits:
        print(f"{path}:{line_no}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
