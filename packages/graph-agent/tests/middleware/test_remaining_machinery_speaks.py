"""三台仍然沉默的机器开口说话(决议 2026-08-13 D4 的收尾盘点)。

tool_error 吞掉异常、tool_history 改写送往模型的历史、runtime_input 给首轮
注入输入、exit_control 注入 nudge —— 每一件都改变了执行走向,却全部只留
logger 或什么都不留。按「发决定不发路过」:做了才发,安静通过不发。
"""

from __future__ import annotations

from typing import Any, cast

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from graph_agent.core.state import BusinessData, FrameworkState
from graph_agent.middleware.runtime_input import RuntimeInputMiddleware
from graph_agent.middleware.tool_error import ToolErrorHandlingMiddleware
from graph_agent.middleware.tool_history import ToolHistoryIntegrityMiddleware


class Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def of_type(self, event_type: str) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", "") == event_type]


def _tool_request(name: str = "search") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "id": "call-1", "args": {}},
        tool=None,
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )


def _model_request(messages: list[Any], *, data: BusinessData | None = None) -> ModelRequest:
    return ModelRequest(
        model=cast(Any, object()),
        messages=messages,
        system_message=None,
        tool_choice=None,
        tools=[],
        response_format=None,
        state=cast(Any, {
            "data": data if data is not None else BusinessData(),
            "flow": FrameworkState(),
            "messages": messages,
        }),
        runtime=cast(Any, None),
    )


class TestToolErrorSpeaks:
    def test_a_swallowed_exception_is_an_event(self) -> None:
        recorder = Recorder()
        middleware = ToolErrorHandlingMiddleware(phase_name="work", callbacks=(recorder,))

        def exploding_handler(_request: ToolCallRequest) -> ToolMessage:
            raise ValueError("boom")

        result = middleware.wrap_tool_call(_tool_request("search"), exploding_handler)

        assert isinstance(result, ToolMessage) and result.status == "error"
        (event,) = recorder.of_type("tool_error_handled")
        assert event.phase_name == "work"
        assert event.tool_name == "search"
        assert "ValueError" in event.error and "boom" in event.error
        # 整句说清:哪个工具炸了、机器把它转成了什么。
        assert "search" in event.message and "error" in event.message.lower()

    def test_a_successful_tool_call_emits_nothing(self) -> None:
        recorder = Recorder()
        middleware = ToolErrorHandlingMiddleware(phase_name="work", callbacks=(recorder,))

        def fine_handler(request: ToolCallRequest) -> ToolMessage:
            return ToolMessage(content="ok", name="search", tool_call_id="call-1")

        middleware.wrap_tool_call(_tool_request("search"), fine_handler)

        assert recorder.events == []


class TestToolHistorySpeaks:
    def test_a_repair_that_changed_the_history_is_an_event(self) -> None:
        recorder = Recorder()
        middleware = ToolHistoryIntegrityMiddleware(phase_name="work", callbacks=(recorder,))
        orphaned = AIMessage(
            content="",
            tool_calls=[{"name": "finish_task", "args": {}, "id": "orphan-1"}],
        )

        captured: list[ModelRequest] = []

        def handler(request: ModelRequest) -> Any:
            captured.append(request)
            return None

        middleware.wrap_model_call(_model_request([orphaned]), handler)

        assert any(isinstance(m, ToolMessage) for m in captured[0].messages)
        (event,) = recorder.of_type("tool_history_repaired")
        assert event.phase_name == "work"
        assert event.synthesized_count == 1
        assert "finish_task" in event.message or "1" in event.message

    def test_an_already_legal_history_emits_nothing(self) -> None:
        recorder = Recorder()
        middleware = ToolHistoryIntegrityMiddleware(phase_name="work", callbacks=(recorder,))

        middleware.wrap_model_call(
            _model_request([HumanMessage(content="hi"), AIMessage(content="ok")]),
            lambda request: None,
        )

        assert recorder.events == []


class TestRuntimeInputSpeaks:
    def test_handing_a_turn_its_inputs_is_an_event_naming_the_keys(self) -> None:
        recorder = Recorder()
        middleware = RuntimeInputMiddleware("work", ("topic",), callbacks=(recorder,))
        data = BusinessData.model_validate({"topic": "venus"})

        captured: list[ModelRequest] = []

        def handler(request: ModelRequest) -> Any:
            captured.append(request)
            return None

        middleware.wrap_model_call(_model_request([], data=data), handler)

        assert any(isinstance(m, HumanMessage) for m in captured[0].messages)
        (event,) = recorder.of_type("runtime_input_injected")
        assert event.phase_name == "work"
        assert event.keys == ["topic"]
        assert "topic" in event.message

    def test_a_turn_that_already_carries_the_block_emits_nothing(self) -> None:
        """路过 stays silent — but only a real re-delivery counts as 路过.

        An unrelated HumanMessage (a nudge, a dead-end warning) is not this
        phase's input block, so it must NOT be read as "already delivered";
        that conflation is the defect fixed in
        `test_runtime_input_delivery_criterion.py`.
        """
        recorder = Recorder()
        middleware = RuntimeInputMiddleware("work", ("topic",), callbacks=(recorder,))
        data = BusinessData.model_validate({"topic": "venus"})

        captured: list[ModelRequest] = []

        def handler(request: ModelRequest) -> Any:
            captured.append(request)
            return None

        middleware.wrap_model_call(_model_request([], data=data), handler)
        middleware.wrap_model_call(captured[0], handler)

        assert len(recorder.of_type("runtime_input_injected")) == 1, recorder.events
