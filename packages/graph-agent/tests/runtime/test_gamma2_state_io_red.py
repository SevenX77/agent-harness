from __future__ import annotations

from pathlib import Path
from typing import Any
from types import SimpleNamespace

import pytest

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.state import WorkflowState, BusinessData, FrameworkState
from graph_agent.core.graph_assembler import _invoke_subagent_once_t23, _SubagentRuntime
from graph_agent.core.io_manager import IOManager
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
from graph_agent.runtime.state_mapper import PhaseWrapper, StateMapper


class _Subagent:
    name = "gamma2_child"


class _RecordingGraph:
    def __init__(self) -> None:
        self.states: list[WorkflowState] = []

    def invoke(self, state: WorkflowState, config: dict[str, Any] | None = None) -> WorkflowState:
        del config
        self.states.append(state)
        child_inputs = state["data"].model_dump()
        return WorkflowState(
            data=BusinessData.model_validate(child_inputs),
            flow=state["flow"],
            messages=[],
        )


def test_gamma2_parent_data_and_messages_do_not_leak_into_subagent_child() -> None:
    graph = _RecordingGraph()
    runtime = _SubagentRuntime(subagent=_Subagent(), graph=graph)

    parent_state = WorkflowState(
        data=BusinessData.model_validate({
            "root_topic": "private",
            "secret_result": "do-not-leak",
        }),
        flow=FrameworkState(current_phase="planner"),
        messages=["parent-message"],
    )

    _invoke_subagent_once_t23(
        runtime,
        parent_state,
        {"scene_text": "hello"},
    )

    child_state = graph.states[0]
    assert child_state["messages"] == []
    assert child_state["data"].model_dump() == {
        "scene_text": "hello",
    }


def test_gamma2_input_funnel_drops_unknown_fields_into_normalized_inputs() -> None:
    mapper = StateMapper(
        input_schema={"type": "object", "properties": {"topic": {"type": "string"}, "also": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
    )

    state = WorkflowState(
        data=BusinessData.model_validate({
            "topic": "A",
            "undeclared": "drop-me",
            "also": "not implicit",
        }),
        flow=FrameworkState(current_phase="upstream"),
        messages=["parent"],
    )

    phase_state = mapper.build_phase_input(state)

    assert phase_state["data"].model_dump() == {"topic": "A", "also": "not implicit"}


def test_gamma2_phase_wrapper_rejects_writes_to_read_only_inputs() -> None:
    mapper = StateMapper(
        input_schema={"type": "object", "properties": {"topic": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"answer": {}}},
    )

    def node(state: WorkflowState) -> dict[str, Any]:
        return {"data": {"extra": "undeclared"}}

    wrapped = PhaseWrapper(mapper).wrap(node)
    state = WorkflowState(data=BusinessData(topic="A"), flow=FrameworkState(), messages=[])

    with pytest.raises(GraphAgentFatalError) as exc_info:
        wrapped(state)
    assert exc_info.value.payload.code == "[F-v3-runtime-state-mapping-failed]"


def test_gamma2_finish_task_acceptance_writes_phase_outputs_not_flat_data() -> None:
    middleware = CognitiveFlowMiddleware(IOManager([]), phase_name="segment")

    result = middleware.handle_finish_task_tool_result(
        tool_name="finish_task",
        tool_result={"ok": True, "data": {"items": [{"title": "Scene plan"}]}},
        output_schema=None,
        flow=FrameworkState(),
        messages=[],
        critic_metrics={},
    )

    assert result is not None
    assert result["data"]["phase_outputs"]["segment"] == {"items": [{"title": "Scene plan"}]}


def test_gamma2_grep_guard_rejects_flat_state_and_parent_merge_residue() -> None:
    root = Path(__file__).resolve().parents[2]
    forbidden = {
        "src/graph_agent/middleware/cognitive_flow.py": 'response_state["data"] = {phase_name',
        "src/graph_agent/core/graph_assembler.py": "child_data = {**before_data, **input_data}",
        "src/graph_agent/core/graph_assembler.py::before_data": '"data": before_data',
    }

    failures: list[str] = []
    for relative_path, needle in forbidden.items():
        file_part = relative_path.split("::", 1)[0]
        text = (root / file_part).read_text(encoding="utf-8")
        if needle in text:
            failures.append(f"{relative_path} still contains {needle!r}")

    assert failures == []
