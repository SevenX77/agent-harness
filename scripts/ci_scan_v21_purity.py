#!/usr/bin/env python3
"""Scan V2.1 skill-local tools/actions for local filesystem writes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GRAPH_AGENT_SRC = _REPO_ROOT / "packages" / "graph-agent" / "src"
if _GRAPH_AGENT_SRC.is_dir():
    sys.path.insert(0, str(_GRAPH_AGENT_SRC))

from graph_agent.core.purity import scan_python_purity


def _iter_python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    for pattern in ("**/actions/*.py", "**/tools/*.py"):
        files.extend(root.glob(pattern))
    return sorted(set(files))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan V2.1 tools/actions purity.")
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args(argv)

    violations = []
    for root in args.roots:
        for path in _iter_python_files(root):
            if "_v2_pending" in path.parts:
                continue
            violations.extend(scan_python_purity(path))

    for violation in violations:
        print(
            f"{violation.path}:{violation.line} [F-v21-purity] "
            f"{violation.api} {violation.reason}"
        )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
