from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import GraphAgentFatalError
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

    with pytest.raises(GraphAgentFatalError, match=r"\[F-v3-runtime-state-mapping-failed\]"):
        mapper.wrap_phase_output({"data": {"answer": "ok", "extra": True}})


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

    assert wrapped({"data": {"topic": "A", "extra": True}, "flow": {}, "messages": []}) == {
        "data": {"inputs": {}, "phase_outputs": {"unknown": {"answer": "A"}}, "scratch": {}}
    }
    assert seen == {"topic": "A"}


def test_reader_sandbox_state_does_not_inherit_parent_blackboard(tmp_path: Path) -> None:
    sandbox = ReaderSandboxState(skill_id="demo.skill", phase_id="main", root=tmp_path)

    state = sandbox.to_blackboard()

    assert state["data"] == {
        "inputs": {
            "skill_id": "demo.skill",
            "phase_id": "main",
            "references": [],
            "max_output_tokens": 3000,
            "language": "zh",
            "timeout_s": 60,
        },
        "phase_outputs": {},
        "scratch": {},
    }
    assert state["messages"] == []
    assert state["flow"]["timeout_s"] == 60
    assert state["run_id"] is None
