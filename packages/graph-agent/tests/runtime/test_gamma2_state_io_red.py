from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.graph_assembler import _invoke_subagent_once_t23, _SubagentRuntime
from graph_agent.core.io_manager import IOManager
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
from graph_agent.runtime.state_mapper import PhaseWrapper, StateMapper


class _Subagent:
    name = "gamma2_child"


class _RecordingGraph:
    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []

    def invoke(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        del config
        self.states.append(state)
        child_inputs = dict(state["data"]["inputs"])
        return {
            "data": {
                "inputs": child_inputs,
                "phase_outputs": {"child": {"answer": child_inputs.get("scene_text", "")}},
                "scratch": {},
            },
            "flow": state.get("flow", {}),
        }


def test_gamma2_parent_data_and_messages_do_not_leak_into_subagent_child() -> None:
    graph = _RecordingGraph()
    runtime = _SubagentRuntime(subagent=_Subagent(), graph=graph)

    _invoke_subagent_once_t23(
        runtime,
        {
            "data": {
                "inputs": {"root_topic": "private"},
                "phase_outputs": {"planner": {"secret_result": "do-not-leak"}},
                "scratch": {"chain_of_thought": "hidden"},
            },
            "flow": {"parent_only": True},
            "messages": ["parent-message"],
            "run_id": "parent-run",
        },
        {"scene_text": "hello"},
    )

    child_state = graph.states[0]
    assert child_state["messages"] == []
    assert child_state["data"] == {
        "inputs": {"scene_text": "hello"},
        "phase_outputs": {},
        "scratch": {},
    }


def test_gamma2_input_funnel_drops_unknown_fields_into_normalized_inputs() -> None:
    mapper = StateMapper(
        input_schema={"type": "object", "properties": {"topic": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
    )

    phase_state = mapper.build_phase_input(
        {
            "data": {
                "inputs": {"topic": "A", "undeclared": "drop-me"},
                "phase_outputs": {"upstream": {"also": "not implicit"}},
                "scratch": {"temp": "hidden"},
            },
            "flow": {},
            "messages": ["parent"],
            "run_id": "r1",
        }
    )

    assert phase_state["data"] == {
        "inputs": {"topic": "A"},
        "phase_outputs": {"upstream": {"also": "not implicit"}},
        "scratch": {},
    }


def test_gamma2_phase_wrapper_rejects_writes_to_read_only_inputs() -> None:
    mapper = StateMapper(
        input_schema={"type": "object", "properties": {"topic": {"type": "string"}}},
        output_schema=None,
    )

    def node(state: dict[str, Any]) -> dict[str, Any]:
        del state
        return {"data": {"inputs": {"topic": "mutated"}}}

    wrapped = PhaseWrapper(mapper).wrap(node)

    with pytest.raises(GraphAgentFatalError) as exc_info:
        wrapped(
            {
                "data": {"inputs": {"topic": "A"}, "phase_outputs": {}, "scratch": {}},
                "flow": {},
                "messages": [],
            }
        )
    assert exc_info.value.payload.code == "[F-v3-runtime-state-mapping-failed]"


def test_gamma2_finish_task_acceptance_writes_phase_outputs_not_flat_data() -> None:
    middleware = CognitiveFlowMiddleware(IOManager([]), phase_name="segment")

    result = middleware.handle_finish_task_tool_result(
        tool_name="finish_task",
        tool_result={"ok": True, "data": {"items": [{"title": "Scene plan"}]}},
        output_schema=None,
        flow={},
        messages=[],
        critic_metrics={},
    )

    assert result is not None
    assert result["data"] == {
        "inputs": {},
        "phase_outputs": {"segment": {"items": [{"title": "Scene plan"}]}},
        "scratch": {},
    }


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
