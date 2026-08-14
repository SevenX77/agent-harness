"""中间件做出的决定必须自己发声,而不是只留一条日志或一次静默注入。

用户裁决(决议 2026-08-13 D4):tracing 的目的是去黑箱——loop_detection 给模型
注入了纠偏诊断、protocol_validation 判定状态违约并中断执行,这些都改变了
运行走向,却在 trace 里完全不可见。按「发决定不发路过」:检测到循环/发现
违约时发事件;每步安静通过时不发。
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import ToolMessage

from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.loop_detection import LoopDetectionMiddleware
from graph_agent.middleware.protocol_validation import (
    ProtocolValidationError,
    ProtocolValidationMiddleware,
)


class Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def of_type(self, event_type: str) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", "") == event_type]


def _state(*, messages: list[Any] | None = None) -> WorkflowState:
    return {
        "data": BusinessData(),
        "flow": FrameworkState(),
        "messages": messages or [],
    }


def _same_tool_message(times: int) -> list[ToolMessage]:
    return [
        ToolMessage(content="no progress", name="search", tool_call_id=f"call-{i}")
        for i in range(times)
    ]


class TestLoopDetectionSpeaks:
    def test_a_detected_loop_is_an_event_with_the_full_sentence(self) -> None:
        recorder = Recorder()
        middleware = LoopDetectionMiddleware(
            loop_window=5, loop_threshold=3, phase_name="segment", callbacks=(recorder,)
        )

        update = middleware.after_model(_state(messages=_same_tool_message(3)), runtime=None)  # type: ignore[arg-type]

        assert update is not None, "注入了诊断却返回 None——测试前提坏了"
        (event,) = recorder.of_type("loop_detected")
        assert event.phase_name == "segment"
        assert event.tool_name == "search"
        assert event.count == 3
        # 整句说清发生了什么、机器做了什么处置。
        assert "search" in event.message and "3" in event.message

    def test_a_quiet_pass_emits_nothing(self) -> None:
        recorder = Recorder()
        middleware = LoopDetectionMiddleware(phase_name="segment", callbacks=(recorder,))

        update = middleware.after_model(_state(messages=_same_tool_message(1)), runtime=None)  # type: ignore[arg-type]

        assert update is None
        assert recorder.events == []


class TestProtocolValidationSpeaks:
    def test_a_violation_is_an_event_before_the_raise(self) -> None:
        recorder = Recorder()
        middleware = ProtocolValidationMiddleware(phase_name="segment", callbacks=(recorder,))
        bad = _state()
        # Build via model_validate so the underscore key actually lands.
        bad["data"] = BusinessData.model_validate({"_smuggled": "x"})

        with pytest.raises(ProtocolValidationError):
            middleware.before_model(bad, runtime=None)  # type: ignore[arg-type]

        (event,) = recorder.of_type("protocol_violation")
        assert event.phase_name == "segment"
        assert event.boundary == "before_model"
        assert event.violations and "_smuggled" in " ".join(event.violations)
        assert "violation" in event.message

    def test_a_clean_state_emits_nothing(self) -> None:
        recorder = Recorder()
        middleware = ProtocolValidationMiddleware(phase_name="segment", callbacks=(recorder,))

        assert middleware.before_model(_state(), runtime=None) is None  # type: ignore[arg-type]
        assert recorder.events == []
