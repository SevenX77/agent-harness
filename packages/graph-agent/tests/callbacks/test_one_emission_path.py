"""Every emitter reaches consumers through the one typed-event entrypoint.

Decision 2026-08-15 (docs/design/2026-08-15-edge-as-first-class-run-segment-decision.md
D7): ``Callback.on_event`` is the single entrypoint, ``_safe_emit_event`` the
single emitter, and the legacy ``on_*`` hook family plus its translation layer
are gone. These tests pin the observable consequence rather than the shape:
a consumer that implements ONLY ``on_event`` — which is what the engine itself
wires in (``_EventSinkCallbackAdapter``) — must see every event.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import AgentLoopIterationEvent, DeadEndPrunedEvent
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.execution_control import ExecutionControlMiddleware

_LEGACY_HOOK_NAMES = (
    "on_phase_start",
    "on_phase_end",
    "on_llm_call",
    "on_tool_call",
    "on_nudge",
    "on_working_memory_update",
    "on_dead_end_pruned",
    "on_compaction",
)


class _TypedOnlyConsumer:
    """What the engine actually wires in: an object with ``on_event`` and nothing else.

    Deliberately NOT a ``Callback`` subclass — inheriting would hand it the base
    class's methods and hide exactly the failure this file exists to catch.
    """

    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


def _state(messages: list[Any]) -> WorkflowState:
    return {
        "data": BusinessData(),
        "flow": FrameworkState(metrics={}),
        "messages": messages,
    }


def _failing_tool_message(name: str, content: str) -> ToolMessage:
    msg = ToolMessage(name=name, content=content, tool_call_id=f"call-{name}")
    msg.status = "error"  # type: ignore[attr-defined]
    return msg


class TestBaseCallbackSurface:
    def test_callback_exposes_no_legacy_hooks(self) -> None:
        for name in _LEGACY_HOOK_NAMES:
            assert not hasattr(Callback, name), (
                f"Callback.{name} is a legacy hook -- D7 deleted the hook family; "
                "consumers override on_event and dispatch on the event type."
            )

    def test_on_event_is_the_entrypoint(self) -> None:
        assert callable(Callback.on_event)


class TestExecutionControlEmission:
    def test_dead_end_pruning_reaches_a_typed_only_consumer(self) -> None:
        consumer = _TypedOnlyConsumer()
        mw = ExecutionControlMiddleware(
            dead_end_threshold=3,
            phase_name="probe",
            callbacks=[consumer],  # type: ignore[list-item]
        )
        messages = [
            HumanMessage(content="go"),
            _failing_tool_message("search", "boom"),
            _failing_tool_message("search", "boom"),
            _failing_tool_message("search", "boom"),
        ]

        update = mw.after_model(_state(messages), None)  # type: ignore[arg-type]

        assert update is not None, "the dead-end threshold should have tripped"
        pruned = [e for e in consumer.events if isinstance(e, DeadEndPrunedEvent)]
        assert len(pruned) == 1, (
            "dead-end pruning must reach on_event; it used to call the legacy "
            f"on_dead_end_pruned hook, which this consumer does not have. Got: {consumer.events}"
        )
        assert pruned[0].phase_name == "probe"
        assert pruned[0].summary == update["messages"][0].content

    def test_iteration_events_reach_a_typed_only_consumer(self) -> None:
        consumer = _TypedOnlyConsumer()
        mw = ExecutionControlMiddleware(
            phase_name="probe",
            callbacks=[consumer],  # type: ignore[list-item]
        )

        mw.before_model(_state([]), None)  # type: ignore[arg-type]

        iterations = [e for e in consumer.events if isinstance(e, AgentLoopIterationEvent)]
        assert [e.iteration for e in iterations] == [1]
        assert iterations[0].phase_name == "probe"

    def test_one_failing_consumer_does_not_starve_the_others(self) -> None:
        class _Exploding:
            def on_event(self, event: Any) -> None:
                raise RuntimeError("consumer fault")

        healthy = _TypedOnlyConsumer()
        mw = ExecutionControlMiddleware(
            phase_name="probe",
            callbacks=[_Exploding(), healthy],  # type: ignore[list-item]
        )

        mw.before_model(_state([]), None)  # type: ignore[arg-type]

        assert [type(e).__name__ for e in healthy.events] == ["AgentLoopIterationEvent"]
