"""Tests for the V2.1 markdown parser cutover."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.parser import parse_markdown_parts, parse_skill_file


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_parse_markdown_parts_returns_frontmatter_body_and_line_meta(tmp_path: Path) -> None:
    path = tmp_path / "GRAPH.md"
    _write(
        path,
        """---
schema_version: "2.1"
name: demo
description: hello
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
""",
    )

    frontmatter, body, meta = parse_markdown_parts(path)

    assert frontmatter["schema_version"] == "2.1"
    assert frontmatter["name"] == "demo"
    assert '<input src="io/inputs.json" />' in body
    assert meta["body_start"] == 6


def test_parse_markdown_parts_accepts_crlf(tmp_path: Path) -> None:
    path = tmp_path / "GRAPH.md"
    path.write_bytes(b'---\r\nschema_version: "2.1"\r\nname: crlf\r\n---\r\n<body />\r\n')

    frontmatter, body, _ = parse_markdown_parts(path)

    assert frontmatter["name"] == "crlf"
    assert "<body />" in body


def test_parse_markdown_parts_rejects_missing_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "GRAPH.md"
    _write(path, "# no frontmatter\n")

    with pytest.raises(SkillLoadError, match="No YAML frontmatter"):
        parse_markdown_parts(path)


def test_parse_markdown_parts_rejects_non_mapping_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "GRAPH.md"
    _write(path, "---\n- just\n- a\n- list\n---\n")

    with pytest.raises(SkillLoadError, match="YAML dictionary"):
        parse_markdown_parts(path)


def test_parse_skill_file_is_removed_schema20_api(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    _write(path, "---\nname: old\n---\n")

    with pytest.raises(SkillLoadError, match="schema 2.0 parse_skill_file is not supported"):
        parse_skill_file(path)
