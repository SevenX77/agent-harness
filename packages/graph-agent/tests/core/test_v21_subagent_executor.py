from __future__ import annotations

import logging
import threading
import time

import pytest
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.graph_assembler import (
    _invoke_subagent_many_t24,
    _invoke_subagent_once_t23,
    _invoke_subagent_tool_t21,
    _subagent_runnable_config,
    _SubagentRuntime,
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
        self.configs: list[dict] = []

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        self.states.append(state)
        self.configs.append(config or {})
        data = dict(state["data"]["inputs"])
        data["child_result"] = data["scene_text"].upper()
        return {
            "data": {"inputs": {}, "phase_outputs": {"beat": data}, "scratch": {}},
            "flow": {"child": True},
        }


def test_subagent_invoke_uses_isolated_messages_and_parent_run_id() -> None:
    graph = _RecordingGraph()
    runtime = _SubagentRuntime(subagent=_Subagent(), graph=graph)

    result = _invoke_subagent_once_t23(
        runtime,
        {
            "data": {"parent": "kept"},
            "flow": {"parent_flow": True},
            "messages": ["dirty"],
            "run_id": "run-1",
        },
        {"scene_text": "hello"},
    )

    assert graph.states[0]["messages"] == []
    assert graph.states[0]["run_id"] == "run-1"
    assert graph.states[0]["data"] == {
        "inputs": {"scene_text": "hello"},
        "phase_outputs": {},
        "scratch": {},
    }
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


class _ConcurrentGraph(_RecordingGraph):
    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.01)
            return super().invoke(state, config=config)
        finally:
            with self.lock:
                self.active -= 1


def test_subagent_fanout_preserves_order_and_limits_concurrency() -> None:
    graph = _ConcurrentGraph()
    runtime = _SubagentRuntime(subagent=_Subagent(), graph=graph)

    results = _invoke_subagent_many_t24(
        runtime,
        {"data": {}, "flow": {}, "messages": [], "run_id": "parent-run"},
        [{"scene_text": str(index)} for index in range(5)],
        parent_config={"tags": ["parent"], "callbacks": ["cb"]},
        depth=0,
    )

    assert [item["index"] for item in results] == [0, 1, 2, 3, 4]
    assert [item["data"]["child_result"] for item in results] == ["0", "1", "2", "3", "4"]
    assert all(item["status"] == "ok" for item in results)
    assert graph.max_active <= 3
    assert all(config["tags"] == ["parent", "subagent", "beat"] for config in graph.configs)
    assert all(config["metadata"]["parent_run_id"] == "parent-run" for config in graph.configs)
    assert all(config["metadata"]["subagent_depth"] == 1 for config in graph.configs)
    assert all(config["callbacks"] == ["cb"] for config in graph.configs)


def test_subagent_runnable_config_contains_tracing_metadata() -> None:
    config = _subagent_runnable_config(
        parent_state={"run_id": "parent-run"},
        parent_config={"tags": ["root"], "metadata": {"trace": "t"}, "callbacks": ["cb"]},
        subagent_name="beat",
        depth=0,
    )

    assert config["tags"] == ["root", "subagent", "beat"]
    assert config["metadata"] == {
        "trace": "t",
        "parent_run_id": "parent-run",
        "subagent_depth": 1,
    }
    assert config["callbacks"] == ["cb"]
    assert config["run_id"]


class _FailingGraph(_RecordingGraph):
    def invoke(self, state: dict, config: dict | None = None) -> dict:
        self.states.append(state)
        self.configs.append(config or {})
        if state["data"]["inputs"]["scene_text"] == "bad":
            raise RuntimeError("child boom")
        return super().invoke(state, config=config)


def test_subagent_aggregator_preserves_item_failure_and_trace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = _FailingGraph()
    runtime = _SubagentRuntime(subagent=_Subagent(), graph=graph)

    with caplog.at_level(logging.ERROR):
        results = _invoke_subagent_many_t24(
            runtime,
            {"data": {}, "flow": {}, "messages": [], "run_id": "parent-run"},
            [{"scene_text": "ok"}, {"scene_text": "bad"}],
            parent_config={"tags": ["parent"]},
            depth=0,
        )

    assert results[0]["status"] == "ok"
    assert results[1]["index"] == 1
    assert results[1]["status"] == "error"
    assert results[1]["error"] == "child boom"
    assert results[1]["parent_run_id"] == "parent-run"
    assert results[1]["child_run_id"]
    assert "subagent item failed" in caplog.text


def test_subagent_retry_limit_logs_and_fails(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(GraphAgentFatalError, match="retry_count=11"),
    ):
        _invoke_subagent_tool_t21(
            tool_name="call_subagent_beat",
            subagent=_Subagent(),
            args={"inputs": []},
            state={"data": {}, "flow": {}, "messages": [], "run_id": "parent-run"},
            flow={"subagent_validation_retries": {"call_subagent_beat": 10}},
        )

    assert "subagent validation retry limit exceeded" in caplog.text
