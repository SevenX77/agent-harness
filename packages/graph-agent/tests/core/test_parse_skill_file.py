"""Tests for the V2.1 markdown parser cutover."""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.parser import parse_markdown_parts


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


def test_parse_markdown_parts_duplicate_key_error_carries_path_and_line(tmp_path: Path) -> None:
    """A raw ruamel YAMLError must be reformatted into the repo's ``path:line`` convention.

    ruamel's own ``str(exc)`` for a duplicate-key document embeds the location as
    `` in "<file>", line N, column M`` — a dialect none of the engine/Studio
    location regexes understand (they all expect ``<path>:<line>``, e.g.
    ``parser.py:_fatal``'s ``f"{path}:{line} {message}"``). Studio's
    ``_LOCATION_RE``/``_lint_error_from_exception`` therefore silently drops the
    line for this exact case (`apps/studio/backend/app/services/skills.py:69`),
    even though ruamel's exception carries a structured ``problem_mark.line``.
    Fixing the message shape at the point the raw exception is caught benefits
    every downstream consumer instead of teaching each one ruamel's dialect.
    """
    path = tmp_path / "GRAPH.md"
    _write(
        path,
        """---
schema_version: "v0.3.0"
name: demo
io:
  inputs:
    type: object
    properties:
      aa_number:
        type: number
      aa_number:
        type: number
  outputs:
    type: object
    properties: {}
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
""",
    )

    with pytest.raises(SkillLoadError) as exc_info:
        parse_markdown_parts(path)

    message = str(exc_info.value)
    assert f"{path}:10" in message, (
        "duplicate key sits on file line 10 (the second `aa_number:` occurrence); "
        f"the message must lead with '<path>:<line>' per repo convention, got: {message!r}"
    )
