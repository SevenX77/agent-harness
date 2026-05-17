"""V2.1 serialization tests for the retained GraphManifest alias."""

from __future__ import annotations

import pytest
from graph_agent.core.manifest import GraphManifest, GraphPhaseRef
from graph_agent.core.parser import parse_markdown_parts
from graph_agent.core.serialize import serialize_skill


def _manifest() -> GraphManifest:
    return GraphManifest(
        name="demo-v21",
        description="Line 1\nLine 2",
        io_inputs_ref="io/inputs.json",
        io_outputs_ref="io/outputs.json",
        phases=[
            GraphPhaseRef(id="prepare", src="phases/prepare", depends_on=[]),
            GraphPhaseRef(id="write", src="phases/write", depends_on=["prepare"]),
        ],
        metadata={"owner": "tests", "notes": "multi\nline"},
    )


def test_output_is_fenced_yaml() -> None:
    out = serialize_skill(_manifest())

    assert out.startswith("---\n")
    assert out.endswith("---\n")
    assert "schema_version: '2.1'" in out


def test_multiline_strings_use_block_scalar() -> None:
    out = serialize_skill(_manifest())

    assert "description: |" in out
    assert "notes: |" in out


def test_graph_manifest_round_trip_through_parser(tmp_path) -> None:
    path = tmp_path / "GRAPH.md"
    path.write_text(serialize_skill(_manifest()), encoding="utf-8")

    frontmatter, body, _ = parse_markdown_parts(path)
    parsed = GraphManifest.model_validate(frontmatter)

    assert body == ""
    assert parsed == _manifest()


def test_none_like_defaults_are_not_serialized_as_null() -> None:
    out = serialize_skill(GraphManifest(name="minimal"))

    assert "null" not in out
    assert "phases: []" in out


def test_non_pydantic_input_raises_type_error() -> None:
    with pytest.raises(TypeError):
        serialize_skill({"not": "a model"})  # type: ignore[arg-type]
