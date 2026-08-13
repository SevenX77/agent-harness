"""The gateway's own two documents may only name files that exist.

The README and USAGE.md are what someone reads before touching this package,
and a path in them is a promise about where to look. When a domain moves a file
the promise breaks silently: nothing imports a document, so nothing fails.

That is not hypothetical. The module-tree work moved and deleted files across
six domains, and the README kept advertising `registry/probe_contracts.py` as a
present capability months after #713 deleted it, plus five more paths that had
moved. It was found by scanning by hand — a measurement, not a gate, and a
measurement only holds until the next move.

Scope is deliberately these two files. They are the ones this package ships and
is answerable for; `docs/graph-agent-gateway/mvp1/` carries per-module design
with its own baseline/history conventions, and history is supposed to name
files that are gone.
"""

from __future__ import annotations

import re
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PACKAGE_ROOT.parents[1]

_DOCS = (
    _PACKAGE_ROOT / "README.md",
    _REPO_ROOT / "docs" / "graph-agent-gateway" / "USAGE.md",
)

# Where a path in those documents is allowed to be rooted. A bare
# `registry/schema.py` means the gateway package; `services/llm_x.py` means the
# studio backend, which the README names as the home of capabilities that have
# not sunk into this package yet.
_TREES = (
    _REPO_ROOT / "packages" / "graph-agent-gateway" / "src" / "graph_agent_gateway",
    _REPO_ROOT / "packages" / "graph-agent-gateway",
    _REPO_ROOT / "apps" / "studio" / "backend" / "app",
    _REPO_ROOT / "apps" / "studio" / "backend",
    _REPO_ROOT,
)

# `path.py` or `path.py:symbol`, inside backticks — the form both documents use.
_NAMED_PATH = re.compile(r"`([A-Za-z_][\w./-]*\.py)(?::([A-Za-z_][\w.]*))?`")


def _resolve(candidate: str) -> Path | None:
    for tree in _TREES:
        target = tree / candidate
        if target.is_file():
            return target
    return None


def test_every_python_path_the_gateway_docs_name_exists() -> None:
    missing: list[str] = []
    for doc in _DOCS:
        for line_no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for candidate, _symbol in _NAMED_PATH.findall(line):
                if _resolve(candidate) is None:
                    missing.append(f"{doc.relative_to(_REPO_ROOT).as_posix()}:{line_no} -> {candidate}")

    assert missing == [], (
        "these documents name files that do not exist — move the reference with "
        "the file, or say plainly that it is gone:\n  " + "\n  ".join(missing)
    )


def test_every_symbol_the_gateway_docs_name_is_in_the_file_they_name() -> None:
    """A path that resolves is not enough: `a.py:b` claims b is defined in a.

    The README named `registry/lint.py:lint_role_routes` after lint moved to
    `resolve/`, and a check that only looked at filenames would have called that
    fine, because a file named `lint.py` still existed — somewhere else.
    """

    wrong: list[str] = []
    for doc in _DOCS:
        for line_no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for candidate, symbol in _NAMED_PATH.findall(line):
                if not symbol:
                    continue
                target = _resolve(candidate)
                if target is None:
                    continue  # the path test above owns this failure
                if not re.search(rf"\b{re.escape(symbol)}\b", target.read_text(encoding="utf-8")):
                    wrong.append(
                        f"{doc.relative_to(_REPO_ROOT).as_posix()}:{line_no} -> "
                        f"{symbol} is not in {candidate}"
                    )

    assert wrong == [], (
        "these documents point a name at a file that does not define it:\n  " + "\n  ".join(wrong)
    )
