"""Line-location helpers for V2.1 YAML frontmatter."""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.parser import locate_line_for_pydantic_loc, parse_markdown_parts


def _write_minimal_logic_skill(
    root: Path,
    *,
    graph_extra: str = "",
    logic_extra: str = "",
) -> None:
    (root / "phases" / "prepare" / "actions").mkdir(parents=True)
    graph_extra_block = f"{graph_extra}\n" if graph_extra else ""
    logic_extra_block = f"{logic_extra}\n" if logic_extra else ""
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: compiler-line-location-test
{graph_extra_block}io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - prepare
---
<phase depends_on="input" output>prepare</phase>
""",
        encoding="utf-8",
    )
    (root / "phases" / "prepare" / "LOGIC.md").write_text(
        f"""---
{logic_extra_block}io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties:
      answer:
        type: string
---
<action>prepare</action>
""",
        encoding="utf-8",
    )
    (root / "phases" / "prepare" / "actions" / "prepare.py").write_text(
        "def prepare(context):\n    return {'answer': 'ok'}\n",
        encoding="utf-8",
    )


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


def test_graph_frontmatter_validation_payload_uses_relative_source_and_field_path(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_logic_skill(tmp_path, graph_extra="unexpected_root: true")

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    payload = excinfo.value.payload
    assert payload is not None
    assert payload.code == "[F-v3-graph-schema-unknown-field]"
    assert payload.source_path == "GRAPH.md"
    assert payload.field_path == "unexpected_root"
    assert getattr(excinfo.value, "source_path", None) == "GRAPH.md"
    assert getattr(excinfo.value, "field_path", None) == "unexpected_root"


def test_frontmatter_parse_error_payload_uses_relative_source_path(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_logic_skill(tmp_path)
    (tmp_path / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: [unterminated
---
<phase depends_on="input" output>prepare</phase>
""",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    payload = excinfo.value.payload
    assert payload is not None
    assert payload.code == "[F-v3-graph-schema-unknown-field]"
    assert payload.source_path == "GRAPH.md"
    assert payload.field_path is None


def test_phase_frontmatter_validation_payload_uses_relative_source_and_field_path(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_logic_skill(tmp_path, logic_extra='validator: "yes"')

    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    payload = excinfo.value.payload
    assert payload is not None
    assert payload.code == "[F-v3-logic-validator-type-invalid]"
    assert payload.source_path == "phases/prepare/LOGIC.md"
    assert payload.field_path == "validator"
    assert getattr(excinfo.value, "source_path", None) == "phases/prepare/LOGIC.md"
    assert getattr(excinfo.value, "field_path", None) == "validator"


def test_public_compile_error_payload_round_trips_location_axes(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_logic_skill(tmp_path, graph_extra="unexpected_root: true")

    with pytest.raises(SkillLoadError) as excinfo:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert excinfo.value.payload is not None
    dumped = excinfo.value.payload.model_dump(mode="json")
    assert dumped["source_path"] == "GRAPH.md"
    assert dumped["field_path"] == "unexpected_root"
    wire_payload = getattr(excinfo.value, "error_payload", None)
    assert wire_payload is not None
    assert wire_payload["source_path"] == "GRAPH.md"
    assert wire_payload["field_path"] == "unexpected_root"


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
