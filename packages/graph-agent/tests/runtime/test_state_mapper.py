from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.runtime.state_mapper import (
    PhaseWrapper,
    ReaderSandboxState,
    ReferenceReaderWrapper,
    StateMapper,
    filter_runtime_inputs,
)


def test_filter_runtime_inputs_uses_declared_schema_properties_in_lenient_mode() -> None:
    schema = {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    }

    assert filter_runtime_inputs(
        {"topic": "A", "extra": True},
        schema,
        strict_unknown=False,
    ) == {"topic": "A"}


def test_filter_runtime_inputs_rejects_unknown_inputs_by_default() -> None:
    schema = {"type": "object", "properties": {"topic": {"type": "string"}}}

    with pytest.raises(GraphAgentFatalError, match="undeclared runtime inputs"):
        filter_runtime_inputs({"topic": "A", "extra": True}, schema)


def test_filter_runtime_inputs_validates_required_schema() -> None:
    schema = {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    }

    with pytest.raises(GraphAgentFatalError, match="runtime inputs invalid"):
        filter_runtime_inputs({}, schema)


def test_state_mapper_rejects_undeclared_output_keys() -> None:
    mapper = StateMapper(output_schema={"type": "object", "properties": {"answer": {}}})

    with pytest.raises(GraphAgentFatalError, match=r"\[F-v3-runtime-state-mapping-failed\]"):
        mapper.wrap_phase_output({"data": {"answer": "ok", "extra": True}})


def test_phase_wrapper_maps_input_and_output() -> None:
    mapper = StateMapper(
        input_schema={"type": "object", "properties": {"topic": {}}},
        output_schema={"type": "object", "properties": {"answer": {}}},
    )
    seen: dict[str, object] = {}

    def node(state):
        seen.update(state["data"])
        return {"data": {"answer": state["data"]["topic"]}}

    wrapped = PhaseWrapper(mapper).wrap(node)

    assert wrapped({"data": {"topic": "A", "extra": True}, "flow": {}, "messages": []}) == {
        "data": {"answer": "A"}
    }
    assert seen == {"topic": "A"}


def test_reader_sandbox_state_does_not_inherit_parent_blackboard(tmp_path: Path) -> None:
    sandbox = ReaderSandboxState(
        skill_id="demo.skill",
        phase_id="main",
        root=tmp_path,
        references=[{"id": "R1", "path": "refs/r1.md", "summary": "Rules"}],
    )

    state = sandbox.to_blackboard()

    assert state["data"] == {
        "skill_id": "demo.skill",
        "phase_id": "main",
        "references": [{"id": "R1", "path": "refs/r1.md", "summary": "Rules"}],
    }
    assert state["messages"] == []
    assert state["flow"]["timeout_s"] == 60
    assert state["run_id"] is None


def test_reference_reader_wrapper_uses_fresh_messages_and_copied_flow() -> None:
    seen: dict[str, object] = {}

    def reader(state):
        seen["messages"] = state["messages"]
        state["flow"]["timeout_s"] = 1
        return {"markdown": "ok", "used_reference_ids": []}

    wrapped = ReferenceReaderWrapper().wrap(reader)
    parent_flow = {"timeout_s": 60}

    result = wrapped({"data": {"skill_id": "demo"}, "flow": parent_flow, "messages": ["old"]})

    assert result["markdown"] == "ok"
    assert seen["messages"] == []
    assert parent_flow == {"timeout_s": 60}


def test_state_mapper_build_child_input_and_flow_are_isolated() -> None:
    mapper = StateMapper(input_schema={"type": "object", "properties": {"topic": {}}})
    parent_flow = {"subagent_depth": 2, "nested": {"keep": True}}

    child_data = mapper.build_child_input({"topic": "A"})
    child_flow = mapper.build_child_flow(parent_flow)
    child_flow["nested"]["keep"] = False

    assert child_data == {"topic": "A"}
    assert child_flow["subagent_depth"] == 3
    assert parent_flow == {"subagent_depth": 2, "nested": {"keep": True}}
