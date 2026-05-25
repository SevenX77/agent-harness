"""
Test: test_llm_fallback_event.py
Covers: tasks.md α4 (fallback tracing alignment) +
design.md §4 (β/γ3 tracing boundary) +
requirements.md §4.1 (structured fallback diagnostics).
"""

from __future__ import annotations

from typing import Any


class RecordingCallback:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class FailingCallback:
    def on_event(self, event: Any) -> None:
        raise RuntimeError("callback failed")


def test_build_llm_fallback_event_has_gateway_payload_schema() -> None:
    from graph_agent_gateway.tracing import build_llm_fallback_event

    event = build_llm_fallback_event(
        phase_name="draft",
        from_provider="openai/gpt-5",
        to_provider="anthropic/claude-opus",
        reason="RateLimitError: quota exceeded",
        code="[F-v3-gateway-all-providers-failed]",
        context={"role_name": "balanced"},
    )

    assert event.phase_name == "draft"
    assert event.from_provider == "openai/gpt-5"
    assert event.to_provider == "anthropic/claude-opus"
    assert event.reason == "RateLimitError: quota exceeded"
    assert event.code == "[F-v3-gateway-all-providers-failed]"
    assert event.context == {"role_name": "balanced"}


def test_emit_llm_fallback_event_uses_unified_callback_surface() -> None:
    from graph_agent_gateway.tracing import emit_llm_fallback_event

    callback = RecordingCallback()

    emit_llm_fallback_event(
        callbacks=(callback,),
        phase_name="draft",
        from_provider="openai/gpt-5",
        to_provider="anthropic/claude-opus",
        reason="RateLimitError: quota exceeded",
        code="[F-v3-gateway-all-providers-failed]",
        context={"role_name": "balanced"},
    )

    assert len(callback.events) == 1
    assert callback.events[0].phase_name == "draft"
    assert callback.events[0].from_provider == "openai/gpt-5"
    assert callback.events[0].to_provider == "anthropic/claude-opus"


def test_callback_failure_does_not_mask_fallback_event_delivery() -> None:
    from graph_agent_gateway.tracing import emit_llm_fallback_event

    callback = RecordingCallback()

    emit_llm_fallback_event(
        callbacks=(FailingCallback(), callback),
        phase_name="draft",
        from_provider="openai/gpt-5",
        to_provider="<none>",
        reason="TimeoutError: request timed out",
        code="[F-v3-gateway-all-providers-failed]",
        context={"role_name": "balanced"},
    )

    assert len(callback.events) == 1
    assert callback.events[0].to_provider == "<none>"
