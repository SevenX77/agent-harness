"""Cohesion plan 方针 3.4 (2026-04-26): SKILL.md authored on Windows or
copied through certain editors / diff tools may use ``\\r\\n`` (CRLF)
line endings. The original frontmatter regex hard-coded ``\\n`` so any
caller that hands the parser raw CRLF content (i.e. anything that does
not go through Python's universal-newline file IO) hit
"Invalid frontmatter format" even though the YAML was perfectly valid.
The parser now accepts both ``\\n`` and ``\\r\\n``.
"""
from __future__ import annotations

from pathlib import Path

from graph_agent.core.parser import _parse_frontmatter, parse_skill_file

_CRLF_FRONTMATTER = (
    "---\r\n"
    'schema_version: "2.0"\r\n'
    "name: x\r\n"
    "description: hello CRLF world\r\n"
    "type: agent\r\n"
    "agent_profile:\r\n"
    "  role: r\r\n"
    "  goal: g\r\n"
    "---\r\n"
    "Body line 1\r\n"
)


def test_parse_frontmatter_accepts_crlf_content() -> None:
    """``_parse_frontmatter`` is callable directly with raw content
    (Studio's UI surface, in-memory Studio editing, programmatic
    callers). It must accept CRLF without normalising upstream."""
    fm = _parse_frontmatter(_CRLF_FRONTMATTER)
    assert fm["name"] == "x"
    assert fm["description"] == "hello CRLF world"


def test_parse_skill_file_accepts_crlf_on_disk(tmp_path: Path) -> None:
    """End-to-end through the file-IO entry point. ``read_text`` does
    universal-newline normalisation so this would already work, but
    we lock the behaviour in."""
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(_CRLF_FRONTMATTER.encode("utf-8"))
    parsed = parse_skill_file(skill)
    assert parsed["frontmatter"]["description"] == "hello CRLF world"
    assert "Body line 1" in parsed["human_body"]


def test_lf_frontmatter_still_parses(tmp_path: Path) -> None:
    """Regression guard: CRLF tolerance must not break the standard LF case."""
    fm = _parse_frontmatter(
        "---\n"
        'schema_version: "2.0"\n'
        "name: x\n"
        "description: standard LF\n"
        "type: agent\n"
        "agent_profile:\n"
        "  role: r\n"
        "  goal: g\n"
        "---\n"
    )
    assert fm["description"] == "standard LF"
