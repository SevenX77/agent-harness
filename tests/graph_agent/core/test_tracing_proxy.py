"""TracingClientProxy behavior tests for loop_index counter semantics."""
from __future__ import annotations

from typing import Any

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import CallbackEvent, PromptCapturedEvent
from graph_agent.core.tracing_proxy import TracingClientProxy


class _CapturingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[CallbackEvent] = []

    def on_event(self, event: CallbackEvent) -> None:  # type: ignore[override]
        self.events.append(event)


class _StubChatModel:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages: Any, *args: Any, **kwargs: Any) -> str:
        self.calls += 1
        return f"reply-{self.calls}"


class TestTracingClientProxyLoopIndex:
    def test_first_invoke_emits_loop_index_1(self) -> None:
        cb = _CapturingCallback()
        proxy = TracingClientProxy(
            wrapped_client=_StubChatModel(),
            callbacks=[cb],
            phase_name="p1",
        )
        proxy.invoke("hello")

        prompt_events = [e for e in cb.events if isinstance(e, PromptCapturedEvent)]
        assert len(prompt_events) == 1
        assert prompt_events[0].loop_index == 1

    def test_loop_index_monotonically_increases(self) -> None:
        cb = _CapturingCallback()
        proxy = TracingClientProxy(
            wrapped_client=_StubChatModel(),
            callbacks=[cb],
            phase_name="p1",
        )

        for _ in range(4):
            proxy.invoke("msg")

        prompt_events = [e for e in cb.events if isinstance(e, PromptCapturedEvent)]
        assert [e.loop_index for e in prompt_events] == [1, 2, 3, 4]

    def test_separate_proxies_have_independent_counters(self) -> None:
        cb = _CapturingCallback()
        proxy_a = TracingClientProxy(
            wrapped_client=_StubChatModel(),
            callbacks=[cb],
            phase_name="phase_a",
        )
        proxy_b = TracingClientProxy(
            wrapped_client=_StubChatModel(),
            callbacks=[cb],
            phase_name="phase_b",
        )

        proxy_a.invoke("a1")
        proxy_a.invoke("a2")
        proxy_b.invoke("b1")
        proxy_a.invoke("a3")

        events_a = [
            e
            for e in cb.events
            if isinstance(e, PromptCapturedEvent) and e.phase_name == "phase_a"
        ]
        events_b = [
            e
            for e in cb.events
            if isinstance(e, PromptCapturedEvent) and e.phase_name == "phase_b"
        ]

        assert [e.loop_index for e in events_a] == [1, 2, 3]
        assert [e.loop_index for e in events_b] == [1]

    def test_counter_increments_before_emit_failure(self) -> None:
        class _BrokenCallback(Callback):
            def on_event(self, event: CallbackEvent) -> None:  # type: ignore[override]
                raise RuntimeError("broken")

        cb_good = _CapturingCallback()
        cb_bad = _BrokenCallback()
        proxy = TracingClientProxy(
            wrapped_client=_StubChatModel(),
            callbacks=[cb_bad, cb_good],
            phase_name="p1",
        )

        proxy.invoke("first")
        proxy.invoke("second")

        prompt_events = [e for e in cb_good.events if isinstance(e, PromptCapturedEvent)]
        assert [e.loop_index for e in prompt_events] == [1, 2]
