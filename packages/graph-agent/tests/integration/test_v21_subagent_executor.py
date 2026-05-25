from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.graph_assembler import (
    _invoke_subagent_many_t24,
    _invoke_subagent_tool_t21,
    _SubagentRuntime,
    assemble_graph,
)
from graph_agent.core.subagents import build_subagent_input_model
from langchain_core.messages import AIMessage, ToolMessage

_FIXTURES = Path(__file__).parents[1] / "fixtures"


class _Subagent:
    name = "echo_expert"
    input_model = build_subagent_input_model(
        "EchoInput",
        {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    expected_schema = input_model.model_json_schema()


class _SubagentFixtureChatModel:
    def __init__(self, parent_calls: list[dict[str, Any]]) -> None:
        self.parent_calls = parent_calls
        self.bound_tools: list[Any] = []

    def bind_tools(self, tools: list[Any]) -> _SubagentFixtureChatModel:
        self.bound_tools = tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        system = str(messages[0].content)
        if "Echo the provided text" in system:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "finish_task",
                        "args": {"markdown": "## echoed\n\nok"},
                        "id": "child-finish",
                    }
                ],
            )
        subagent_messages = [
            message
            for message in messages
            if isinstance(message, ToolMessage) and message.name == "call_subagent_echo_expert"
        ]
        if subagent_messages and not json.loads(str(subagent_messages[-1].content)).get("ok"):
            return AIMessage(content="", tool_calls=[self.parent_calls.pop(0)])
        if subagent_messages:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "finish_task",
                        "args": {"markdown": "## done\n\ntrue"},
                        "id": "parent-finish",
                    }
                ],
            )
        return AIMessage(content="", tool_calls=[self.parent_calls.pop(0)])


def _subagent_tool_messages(result: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in result["messages"]:
        if isinstance(message, ToolMessage) and message.name == "call_subagent_echo_expert":
            payloads.append(json.loads(str(message.content)))
    return payloads


def test_subagent_minimal_fixture_fanout_e2e() -> None:
    chat = _SubagentFixtureChatModel(
        [
            {
                "name": "call_subagent_echo_expert",
                "args": {"inputs": [{"text": "a"}, {"text": "b"}, {"text": "c"}]},
                "id": "subagent-1",
            }
        ]
    )

    graph = assemble_graph(
        compile_skill(_FIXTURES / "subagent_minimal", cache=False),
        chat_model=chat,
    ).graph
    result = graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "parent-run"})

    payload = _subagent_tool_messages(result)[0]
    assert payload["ok"] is True
    assert [item["index"] for item in payload["results"]] == [0, 1, 2]
    assert all(item["status"] == "ok" for item in payload["results"])


def test_subagent_minimal_fixture_schema_validation_retry_e2e() -> None:
    chat = _SubagentFixtureChatModel(
        [
            {
                "name": "call_subagent_echo_expert",
                "args": {"inputs": {"text": "wrong"}},
                "id": "subagent-bad",
            },
            {
                "name": "call_subagent_echo_expert",
                "args": {"inputs": [{"text": "fixed"}]},
                "id": "subagent-good",
            },
        ]
    )

    graph = assemble_graph(
        compile_skill(_FIXTURES / "subagent_minimal", cache=False),
        chat_model=chat,
    ).graph
    result = graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "parent-run"})

    bad, good = _subagent_tool_messages(result)
    assert bad["ok"] is False
    assert bad["error_type"] == "validation"
    assert "expected_schema" in bad
    assert good["ok"] is True


def test_subagent_max_depth_blocks_nested_dispatch() -> None:
    with pytest.raises(
        GraphAgentFatalError,
        match="Max Depth 1 exceeded: subagent cannot call another subagent",
    ):
        _invoke_subagent_tool_t21(
            tool_name="call_subagent_echo_expert",
            subagent=_Subagent(),
            args={"inputs": [{"text": "nested"}]},
            state={"data": {}, "flow": {}, "messages": [], "run_id": "parent-run"},
            flow={"subagent_depth": 1},
        )


class _OneFailureGraph:
    def invoke(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        del config
        text = state["data"]["inputs"]["text"]
        if text == "bad":
            raise RuntimeError("planned child failure")
        return {
            "data": {
                "inputs": {},
                "phase_outputs": {"child": {"text": text, "echoed": text}},
                "scratch": {},
            },
            "flow": {},
        }


def test_subagent_failure_aggregation_e2e(caplog: pytest.LogCaptureFixture) -> None:
    runtime = _SubagentRuntime(subagent=_Subagent(), graph=_OneFailureGraph())

    with caplog.at_level(logging.ERROR):
        results = _invoke_subagent_many_t24(
            runtime,
            {"data": {}, "flow": {}, "messages": [], "run_id": "parent-run"},
            [{"text": "ok"}, {"text": "bad"}],
            parent_config={"tags": ["parent"]},
            depth=0,
        )

    assert results[0]["status"] == "ok"
    assert results[1]["index"] == 1
    assert results[1]["status"] == "error"
    assert results[1]["error"] == "planned child failure"
    assert results[1]["parent_run_id"] == "parent-run"
    assert results[1]["child_run_id"]
    assert "subagent item failed" in caplog.text
