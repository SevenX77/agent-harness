"""A design unit's ``binds_code`` may only name code that exists.

Every design unit under ``docs/graph-agent-gateway/mvp1/`` carries a
``binds_code`` line in its frontmatter listing the source coordinates that unit
is answerable for. Unlike the prose below it, that line is a machine-readable
claim in the present tense: *this is where the code is now*. When a domain moves
or deletes a file the claim silently becomes false, and a design doc that points
at a file which no longer exists sends the next reader hunting for a ghost.

That is measured, not hypothetical: on 2026-08-13 fourteen coordinates across
eight units named deleted files — ``call/dispatch.py`` and ``call/models.py``
(deleted by #718 as the call path no route could reach), ``copilot_test.py``
(#267), ``llm_import_drafts.py``, and the three capability modules that had just
sunk into this package (#771, #772). Only three of the fourteen were fresh; the
rest had been wrong for months, because nothing reads a document.

**Scope, and what it deliberately does NOT cover.** This checks the frontmatter
claim only. The prose bodies of six ``baseline.md`` files still describe code
deleted by #718 and #267 — real drift, recorded in ``DELIVERY_LEDGER.md``
rather than papered over. It is not covered here because a body is written text
that needs a person to rewrite it faithfully, whereas ``binds_code`` is a list
of paths a machine can hold to account. Do not read a green result as "the
design docs are accurate"; read it as "no design unit points at a file that is
gone".

``mvp1-alignment.md`` bodies are excluded for a further reason: that document
records the target design *and the baseline it migrates away from*, so naming a
since-deleted file in its prose is history doing its job.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DESIGN_UNITS = _REPO_ROOT / "docs" / "graph-agent-gateway" / "mvp1"

_BINDS_CODE = re.compile(r"^binds_code:\s*(.+)$", re.MULTILINE)
_PYTHON_PATH = re.compile(r"([A-Za-z_][\w./-]*\.py)")


def _frontmatter(text: str) -> str:
    """Return the YAML frontmatter block, or an empty string when there is none."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[:end] if end > 0 else ""


def test_every_design_unit_binds_code_that_exists() -> None:
    missing: list[str] = []
    checked = 0

    for doc in sorted(_DESIGN_UNITS.rglob("*.md")):
        match = _BINDS_CODE.search(_frontmatter(doc.read_text(encoding="utf-8")))
        if match is None:
            continue
        for candidate in _PYTHON_PATH.findall(match.group(1)):
            checked += 1
            if not (_REPO_ROOT / candidate).is_file():
                missing.append(f"{doc.relative_to(_REPO_ROOT).as_posix()} -> {candidate}")

    assert checked, "no binds_code coordinates found — did the frontmatter format change?"
    assert missing == [], (
        "these design units bind code that does not exist — point the binding at "
        "where the code lives now, or drop it if the capability is gone:\n  "
        + "\n  ".join(missing)
    )
