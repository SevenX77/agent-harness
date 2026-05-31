from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.runtime.state_mapper import (
    PhaseWrapper,
    ReaderSandboxState,
    StateMapper,
    filter_runtime_inputs,
)


def test_filter_runtime_inputs_uses_declared_schema_properties() -> None:
    schema = {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    }

    assert filter_runtime_inputs({"topic": "A", "extra": True}, schema) == {"topic": "A"}


def test_state_mapper_rejects_undeclared_output_keys() -> None:
    mapper = StateMapper(output_schema={"type": "object", "properties": {"answer": {}}})
    state = WorkflowState(data=BusinessData(), flow=FrameworkState(), messages=[])

    with pytest.raises(GraphAgentFatalError) as exc_info:
        mapper.wrap_phase_output(state, {"data": {"answer": "ok", "extra": True}})
    assert exc_info.value.payload.code == "[F-v3-runtime-state-mapping-failed]"


def test_phase_wrapper_maps_input_and_output() -> None:
    mapper = StateMapper(
        input_schema={"type": "object", "properties": {"topic": {}}},
        output_schema={"type": "object", "properties": {"answer": {}}},
    )
    seen: dict[str, object] = {}

    def node(state):
        seen.update(state["data"]["inputs"])
        return {"data": {"answer": state["data"]["inputs"]["topic"]}}

    wrapped = PhaseWrapper(mapper).wrap(node)

    state = WorkflowState(
        data=BusinessData.model_validate({"topic": "A", "extra": True}),
        flow=FrameworkState(),
        messages=[],
    )
    res = wrapped(state)

    assert res["data"].model_dump() == {"topic": "A", "extra": True, "answer": "A"}
    assert seen == {"topic": "A"}


def test_reader_sandbox_state_does_not_inherit_parent_blackboard(tmp_path: Path) -> None:
    sandbox = ReaderSandboxState(skill_id="demo.skill", phase_id="main", root=tmp_path)

    state = sandbox.to_blackboard()

    assert state["data"].model_dump() == {
        "skill_id": "demo.skill",
        "phase_id": "main",
        "references": [],
        "max_output_tokens": 3000,
        "language": "zh",
        "timeout_s": 60,
    }
    assert state["messages"] == []
    assert state["flow"].timeout_s == 60
    assert getattr(state["flow"], "run_id", None) is None
