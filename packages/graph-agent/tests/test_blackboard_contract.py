"""The graph's output contract is a fact about the graph, derived once."""

from __future__ import annotations

from typing import Any

from graph_agent.core.blackboard_contract import (
    blackboard_fields_at_output,
    undeclared_output_names,
)


class _Node:
    def __init__(self, phase_name: str, frontmatter: dict[str, Any]) -> None:
        self.phase_name = phase_name
        self.frontmatter = frontmatter


class _Compiled:
    def __init__(self, raw: dict[str, Any], nodes: list[_Node]) -> None:
        self.raw = raw
        self.nodes = nodes


def _phase(name: str, outputs: dict[str, Any]) -> _Node:
    return _Node(name, {"io": {"outputs": {"type": "object", "properties": outputs}}})


def _graph(inputs: dict[str, Any], outputs: dict[str, Any], nodes: list[_Node]) -> Any:
    return _Compiled({"io": {"inputs": {"properties": inputs}, "outputs": {"properties": outputs}}}, nodes)


def test_inputs_seed_the_blackboard_and_phase_outputs_are_laid_over_them() -> None:
    compiled = _graph(
        inputs={"chapter_content": {"type": "string"}},
        outputs={"segmentation_result": {"type": "object"}},
        nodes=[
            _phase("setup", {"chapter_lines": {"type": "array"}}),
            _phase("segment", {"segmentation_result": {"type": "object"}}),
        ],
    )

    fields = {field.name: field for field in blackboard_fields_at_output(compiled)}

    assert fields["chapter_content"].produced_by == "input"
    assert fields["chapter_lines"].produced_by == "setup"
    assert fields["segmentation_result"].produced_by == "segment"
    assert fields["chapter_lines"].type == "array"


def test_a_field_written_twice_belongs_to_the_phase_the_output_boundary_sees() -> None:
    compiled = _graph(
        inputs={},
        outputs={"segments": {"type": "array"}},
        nodes=[
            _phase("segment", {"segments": {"type": "array"}}),
            _phase("review", {"segments": {"type": "array"}}),
        ],
    )

    fields = {field.name: field for field in blackboard_fields_at_output(compiled)}

    assert fields["segments"].produced_by == "review"


def test_declared_outputs_are_marked_and_the_rest_are_merely_available() -> None:
    compiled = _graph(
        inputs={"chapter_content": {"type": "string"}},
        outputs={"segmentation_result": {"type": "object"}},
        nodes=[
            _phase("setup", {"chapter_lines": {"type": "array"}}),
            _phase("segment", {"segmentation_result": {"type": "object"}}),
        ],
    )

    fields = {field.name: field for field in blackboard_fields_at_output(compiled)}

    assert fields["segmentation_result"].declared_output is True
    assert fields["chapter_lines"].declared_output is False


def test_an_output_nothing_produces_is_reported() -> None:
    # A declared output no phase writes is a contract the graph cannot honour.
    compiled = _graph(
        inputs={},
        outputs={"summary": {"type": "string"}},
        nodes=[_phase("segment", {"segments": {"type": "array"}})],
    )

    assert undeclared_output_names(compiled) == ["summary"]


def test_a_graph_that_honours_its_outputs_reports_nothing_missing() -> None:
    compiled = _graph(
        inputs={},
        outputs={"segments": {"type": "array"}},
        nodes=[_phase("segment", {"segments": {"type": "array"}})],
    )

    assert undeclared_output_names(compiled) == []
