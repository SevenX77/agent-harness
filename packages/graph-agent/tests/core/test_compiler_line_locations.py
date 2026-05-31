"""Line-location helpers for V2.1 YAML frontmatter."""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.parser import locate_line_for_pydantic_loc, parse_markdown_parts


def test_loader_validation_error_mentions_graph_md(tmp_path: Path, mock_skill_resolver: object) -> None:
    (tmp_path / "phases" / "hello").mkdir(parents=True)
    (tmp_path / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: ""
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - hello
---
<phase depends_on="input" output>hello</phase>
""",
        encoding="utf-8",
    )
    (tmp_path / "phases" / "hello" / "SKILL.md").write_text(
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
<role>Hello</role>
<goal>Done.</goal>
""",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert "GRAPH.md" in str(excinfo.value)
    assert "manifest validation failed" in str(excinfo.value)


def test_locate_line_returns_one_indexed_line(tmp_path: Path, mock_skill_resolver: object) -> None:
    graph = tmp_path / "GRAPH.md"
    graph.write_text(
        "---\n"  # line 1
        'schema_version: "2.1"\n'  # line 2
        "name: hello\n"  # line 3
        "phases:\n"  # line 4
        "  - id: phase_a\n"  # line 5
        "    src: phases/phase_a\n"  # line 6
        "    depends_on: []\n"  # line 7
        "---\n",
        encoding="utf-8",
    )
    frontmatter, _, _ = parse_markdown_parts(graph)

    assert locate_line_for_pydantic_loc(frontmatter, ("name",)) == 3
    assert locate_line_for_pydantic_loc(frontmatter, ("phases", 0, "src")) == 6


def test_locate_line_returns_none_for_plain_dict() -> None:
    plain = {"name": "x", "phases": [{"id": "p"}]}

    assert locate_line_for_pydantic_loc(plain, ("name",)) is None
