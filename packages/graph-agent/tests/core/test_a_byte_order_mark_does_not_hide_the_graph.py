"""A UTF-8 byte-order mark is encoding, not content.

Measured first (2026-08-21, ledger K7): `D:/coding/skills/text-segmentation-v2-lab`
had a GRAPH.md whose first three bytes are `EF BB BF`. Studio drew the two
boundary nodes and nothing else — every phase gone, no error anywhere. The
frontmatter matcher is anchored (`^---`) and the BOM decodes to a `\\ufeff`
character sitting in front of it, so the document read as having no frontmatter
at all, and `phases` came back empty.

Windows editors write that mark routinely (Notepad, PowerShell redirection), so
a skill authored outside Studio arrives with it. The engine already tolerated it
on ONE read path — `graph_assembler` stripped it from runtime input files with a
call-site `.lstrip("\\ufeff")` — which is the tell: one question, two answers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.parser import parse_markdown_parts, parse_markdown_parts_best_effort
from graph_agent.core.topology_projection import load_graph_topology_projection

GRAPH = """---
name: bom-skill
schema_version: "2.1"
phases:
  - alpha
  - beta
---

## alpha

## beta
depends_on: [alpha]
"""


@pytest.fixture
def skill_with_bom(tmp_path: Path) -> Path:
    """A skill directory exactly as a Windows editor leaves it."""
    (tmp_path / "GRAPH.md").write_bytes(b"\xef\xbb\xbf" + GRAPH.encode("utf-8"))
    for phase in ("alpha", "beta"):
        phase_dir = tmp_path / "phases" / phase
        phase_dir.mkdir(parents=True)
        (phase_dir / "LOGIC.md").write_text(f"---\nname: {phase}\n---\n", encoding="utf-8")
    return tmp_path


def test_a_graph_written_by_a_windows_editor_still_has_its_phases(skill_with_bom: Path) -> None:
    projection = load_graph_topology_projection(skill_with_bom)

    assert projection.phases == ["alpha", "beta"]


def test_the_mark_never_reaches_the_frontmatter(skill_with_bom: Path) -> None:
    frontmatter, body, _ = parse_markdown_parts(skill_with_bom / "GRAPH.md")

    assert frontmatter["name"] == "bom-skill"
    assert "\ufeff" not in body


def test_the_tolerant_parser_agrees_with_the_strict_one(skill_with_bom: Path) -> None:
    """Both parsers read the same file; a BOM must not make them disagree."""
    strict, _, _ = parse_markdown_parts(skill_with_bom / "GRAPH.md")
    tolerant, _, _ = parse_markdown_parts_best_effort(skill_with_bom / "GRAPH.md")

    assert strict["phases"] == tolerant["phases"] == ["alpha", "beta"]
