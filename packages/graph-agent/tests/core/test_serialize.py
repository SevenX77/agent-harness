"""V0.3 serialization tests for the retained GraphManifest alias."""

from __future__ import annotations

import pytest

from graph_agent.core.manifest import GraphManifest
from graph_agent.core.parser import parse_markdown_parts
from graph_agent.core.serialize import serialize_skill


def _manifest() -> GraphManifest:
    return GraphManifest(
        schema_version="v0.3.0",
        name="demo-v21",
        description="Line 1\nLine 2",
        io={
            "inputs": {"type": "object", "properties": {}},
            "outputs": {"type": "object", "properties": {}},
        },
        phases=["prepare", "write"],
        metadata={"owner": "tests", "notes": "multi\nline"},
    )


def test_output_is_fenced_yaml() -> None:
    out = serialize_skill(_manifest())

    assert out.startswith("---\n")
    assert out.endswith("---\n")
    assert "schema_version: v0.3.0" in out


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
    out = serialize_skill(
        GraphManifest(
            schema_version="v0.3.0",
            name="minimal",
            io={
                "inputs": {"type": "object", "properties": {}},
                "outputs": {"type": "object", "properties": {}},
            },
        )
    )

    assert "null" not in out
    assert "phases: []" in out


def test_non_pydantic_input_raises_type_error() -> None:
    with pytest.raises(TypeError):
        serialize_skill({"not": "a model"})  # type: ignore[arg-type]
