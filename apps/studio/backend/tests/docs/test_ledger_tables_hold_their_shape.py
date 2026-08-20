"""A ledger row that splits itself files its own contents under the wrong headings.

The ledgers are markdown tables, and a markdown row is delimited by ``|``. So a
row whose prose happens to contain one — a Python union type ``str | None``, a
quoted table row from a run report — silently grows extra columns. Everything
after the stray pipe shifts one heading to the left, and the row goes on looking
perfectly ordinary.

That is not hypothetical. Both ledgers had one on 2026-08-20:

* ``PROBLEM_LEDGER.md`` row E7 quoted two lines of a run report verbatim
  (``| Run | … |`` / ``| Started | … |``) inside its 状态 cell. The row rendered
  with 8 cells instead of 6, so its 出处 column showed a fragment of the status
  text and its 验收判据 column showed another fragment — while the real 出处 and
  the real 验收判据 fell off the end of the table entirely.
* ``DELIVERY_LEDGER.md`` row W2-36 wrote the annotation ``T | None`` and split
  the same way.

A reader cannot catch this: the rendered table looks like a table, just with the
wrong things in the wrong columns. Only counting catches it, which is why this
is a test and not a note in a style guide — the same reasoning the repo already
applied to the run report in #907, where a provider message containing ``|``
quietly reshaped a table cell.

The fix in the documents is to escape the pipe as ``\\|``. This test therefore
splits on UNESCAPED pipes only, which is exactly the rule markdown itself
applies.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]

#: The documents whose rows carry per-item truth, where a row landing under the
#: wrong heading misfiles a fact rather than merely looking untidy.
LEDGERS = (
    "docs/development/PROBLEM_LEDGER.md",
    "docs/development/DELIVERY_LEDGER.md",
    "docs/development/STUDIO_REQUEST_AUDIT.md",
)

#: A markdown cell boundary: a pipe that is not escaped. ``\|`` is content.
CELL_BOUNDARY = re.compile(r"(?<!\\)\|")

#: The row of dashes under a header, e.g. ``|---|---|``. It carries no content,
#: and its own cell count is not what a reader relies on.
_ALIGNMENT_CHARS = set("-: ")


def _cells(row: str) -> list[str]:
    """The cells of one markdown row, honouring ``\\|`` as literal content.

    The leading and trailing pipes are punctuation rather than cell boundaries,
    and GitHub-flavoured markdown lets a row omit either one — so they are
    stripped when present instead of being assumed. Slicing them off blindly
    would eat a real cell from a row written without its closing pipe, which is
    a shape this repo's ledgers do contain.
    """
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [part.strip() for part in CELL_BOUNDARY.split(body)]


def _is_alignment_row(row: str) -> bool:
    return bool(row.strip()) and set(row.strip().replace("|", "")) <= _ALIGNMENT_CHARS


def _mis_shaped_rows(text: str) -> list[tuple[int, int, int, str]]:
    """Every row whose cell count differs from the header it sits under."""
    findings: list[tuple[int, int, int, str]] = []
    width: int | None = None
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip().startswith("|"):
            # A blank line or a paragraph ends the table; the next one gets to
            # declare its own width.
            width = None
            continue
        if _is_alignment_row(line):
            continue
        count = len(_cells(line))
        if width is None:
            width = count
            continue
        if count != width:
            findings.append((number, count, width, line.strip()[:60]))
    return findings


@pytest.mark.parametrize("relative_path", LEDGERS)
def test_every_ledger_row_has_as_many_cells_as_its_header(relative_path: str) -> None:
    document = REPO_ROOT / relative_path
    assert document.exists(), f"{relative_path} is missing"

    findings = _mis_shaped_rows(document.read_text(encoding="utf-8"))

    assert not findings, "\n".join(
        f"{relative_path}:{number} has {count} cells under a {width}-column header "
        f"— escape the stray `|` as `\\|`: {preview}"
        for number, count, width, preview in findings
    )


def test_the_splitter_treats_an_escaped_pipe_as_content() -> None:
    """Without this, the fix the test recommends would fail the test."""
    assert _cells(r"| a | b \| c | d |") == ["a", r"b \| c", "d"]


def test_a_row_written_without_its_closing_pipe_keeps_every_cell() -> None:
    """The shape that made an earlier version of this gate accuse a good row."""
    assert _cells("| a | b | c") == ["a", "b", "c"]
    assert _cells("a | b | c |") == ["a", "b", "c"]


def test_a_stray_pipe_is_what_the_gate_catches() -> None:
    """The defect this test exists for, in miniature."""
    table = "| # | note |\n|---|---|\n| 1 | a str | None annotation |\n"

    findings = _mis_shaped_rows(table)

    assert [(count, width) for _, count, width, _ in findings] == [(3, 2)]
