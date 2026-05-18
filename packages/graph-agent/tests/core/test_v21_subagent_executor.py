from __future__ import annotations

import pytest

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.graph_assembler import (
    _SubagentRuntime,
    _invoke_subagent_once_t23,
    _invoke_subagent_tool_t21,
)
from graph_agent.core.subagents import build_subagent_input_model, validate_subagent_tool_args


def _input_model() -> type:
    return build_subagent_input_model(
        "BeatInput",
        {
            "type": "object",
            "properties": {"scene_text": {"type": "string"}},
            "required": ["scene_text"],
        },
    )


class _Subagent:
    name = "beat"
    input_model = _input_model()
    expected_schema = input_model.model_json_schema()


def test_subagent_runtime_rejects_non_array_inputs() -> None:
    model = _input_model()

    result = validate_subagent_tool_args(
        tool_name="call_subagent_beat",
        subagent_name="beat",
        input_model=model,
        expected_schema=model.model_json_schema(),
        args={"inputs": {"scene_text": "x"}},
        retry_count=1,
    )

    assert not isinstance(result, list)
    payload = result.to_tool_result()
    assert payload["ok"] is False
    assert payload["error_type"] == "validation"
    assert payload["expected_schema"]["properties"]["scene_text"]["type"] == "string"
    assert payload["errors"][0]["loc"] == ["inputs"]


def test_subagent_runtime_rejects_invalid_item_schema() -> None:
    model = _input_model()

    result = validate_subagent_tool_args(
        tool_name="call_subagent_beat",
        subagent_name="beat",
        input_model=model,
        expected_schema=model.model_json_schema(),
        args={"inputs": [{"text": "wrong"}]},
        retry_count=1,
    )

    assert not isinstance(result, list)
    payload = result.to_tool_result()
    assert payload["retry_count"] == 1
    assert payload["errors"][0]["loc"] == ["inputs", 0, "scene_text"]


def test_subagent_runtime_accepts_valid_input_array() -> None:
    model = _input_model()

    result = validate_subagent_tool_args(
        tool_name="call_subagent_beat",
        subagent_name="beat",
        input_model=model,
        expected_schema=model.model_json_schema(),
        args={"inputs": [{"scene_text": "a"}, {"scene_text": "b"}]},
        retry_count=1,
    )

    assert isinstance(result, list)
    assert [item.model_dump() for item in result] == [{"scene_text": "a"}, {"scene_text": "b"}]


def test_subagent_runtime_fails_after_ten_schema_retries() -> None:
    model = _input_model()

    with pytest.raises(RuntimeError, match="retry_count=11"):
        validate_subagent_tool_args(
            tool_name="call_subagent_beat",
            subagent_name="beat",
            input_model=model,
            expected_schema=model.model_json_schema(),
            args={"inputs": []},
            retry_count=11,
        )


def test_subagent_depth_zero_allows_call() -> None:
    result = _invoke_subagent_tool_t21(
        tool_name="call_subagent_beat",
        subagent=_Subagent(),
        args={"inputs": [{"scene_text": "x"}]},
        flow={"subagent_depth": 0},
    )

    assert result["ok"] is True


def test_subagent_depth_one_blocks_nested_call() -> None:
    with pytest.raises(
        GraphAgentFatalError,
        match="Max Depth 1 exceeded: subagent cannot call another subagent",
    ):
        _invoke_subagent_tool_t21(
            tool_name="call_subagent_beat",
            subagent=_Subagent(),
            args={"inputs": [{"scene_text": "x"}]},
            flow={"subagent_depth": 1},
        )


class _RecordingGraph:
    def __init__(self) -> None:
        self.states: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.states.append(state)
        data = dict(state["data"])
        data["child_result"] = data["scene_text"].upper()
        return {"data": data, "flow": {"child": True}}


def test_subagent_invoke_uses_isolated_messages_and_parent_run_id() -> None:
    graph = _RecordingGraph()
    runtime = _SubagentRuntime(subagent=_Subagent(), graph=graph)

    result = _invoke_subagent_once_t23(
        runtime,
        {"data": {"parent": "kept"}, "flow": {"parent_flow": True}, "messages": ["dirty"], "run_id": "run-1"},
        {"scene_text": "hello"},
    )

    assert graph.states[0]["messages"] == []
    assert graph.states[0]["run_id"] == "run-1"
    assert graph.states[0]["data"] == {"parent": "kept", "scene_text": "hello"}
    assert result["data"] == {"scene_text": "hello", "child_result": "HELLO"}


def test_subagent_valid_runtime_call_invokes_cached_graph() -> None:
    graph = _RecordingGraph()
    runtime = _SubagentRuntime(subagent=_Subagent(), graph=graph)

    result = _invoke_subagent_tool_t21(
        tool_name="call_subagent_beat",
        subagent=_Subagent(),
        args={"inputs": [{"scene_text": "a"}, {"scene_text": "b"}]},
        state={"data": {}, "flow": {}, "messages": ["parent"], "run_id": "run-2"},
        flow={},
        runtime=runtime,
    )

    assert result["ok"] is True
    assert [item["data"]["child_result"] for item in result["results"]] == ["A", "B"]
    assert len(graph.states) == 2
