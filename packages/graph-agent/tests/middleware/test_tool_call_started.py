"""A tool call must announce itself before it runs, and own an identity.

Studio's trace panel wants a step to appear the moment it starts and collapse
into a summary once it finishes. ``ToolCallEvent`` alone cannot serve that: it
carries ``result``/``duration_ms``, so it can only be emitted after the fact.
``ToolCallStartedEvent`` is the "about to run" half, and ``tool_call_id`` is
what lets a consumer pair the two halves when several tool calls are in flight
inside one agent turn.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import ToolCallEvent, ToolCallStartedEvent
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.tracing import TracingMiddleware


class _RecordingCallback(Callback):
    def __init__(self, timeline: list[Any] | None = None) -> None:
        self.events: list[Any] = []
        self._timeline = timeline

    def on_event(self, event: Any) -> None:
        self.events.append(event)
        if self._timeline is not None:
            self._timeline.append(event)


def _state() -> WorkflowState:
    return {
        "data": BusinessData(),
        "flow": FrameworkState(thread_id="run-1"),
        "messages": [],
    }


def _request(*, name: str, call_id: str | None, args: dict[str, Any]) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "id": call_id, "args": args},
        tool=None,
        state=_state(),
        runtime=None,  # type: ignore[arg-type]
    )


def _started_events(callback: _RecordingCallback) -> list[ToolCallStartedEvent]:
    return [e for e in callback.events if isinstance(e, ToolCallStartedEvent)]


def _tool_call_events(callback: _RecordingCallback) -> list[ToolCallEvent]:
    return [e for e in callback.events if isinstance(e, ToolCallEvent)]


def test_started_and_finished_events_pair_on_one_tool_call_id() -> None:
    callback = _RecordingCallback()
    tracing = TracingMiddleware(callbacks=[callback], phase_name="draft")
    request = _request(name="lookup", call_id="call-1", args={"topic": "pairing"})

    def handler(_request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="found", name="lookup", tool_call_id="call-1")

    tracing.wrap_tool_call(request, handler)

    started = _started_events(callback)
    finished = _tool_call_events(callback)
    assert len(started) == 1
    assert len(finished) == 1
    # The provider already named this call; the engine must not invent a second
    # identity for the same call.
    assert started[0].tool_call_id == "call-1"
    assert started[0].tool_call_id == finished[0].tool_call_id
    assert started[0].tool_name == finished[0].tool_name == "lookup"
    assert started[0].phase_name == finished[0].phase_name == "draft"
    assert started[0].args == {"topic": "pairing"}


def test_started_event_is_emitted_before_the_tool_body_runs() -> None:
    timeline: list[Any] = []
    callback = _RecordingCallback(timeline)
    tracing = TracingMiddleware(callbacks=[callback], phase_name="draft")
    request = _request(name="slow_tool", call_id="call-1", args={})

    def handler(_request: ToolCallRequest) -> ToolMessage:
        timeline.append("tool-body-ran")
        return ToolMessage(content="done", name="slow_tool", tool_call_id="call-1")

    tracing.wrap_tool_call(request, handler)

    kinds = [item if isinstance(item, str) else type(item).__name__ for item in timeline]
    assert kinds == ["ToolCallStartedEvent", "tool-body-ran", "ToolCallEvent"]


def test_two_tool_calls_keep_their_own_identities() -> None:
    callback = _RecordingCallback()
    tracing = TracingMiddleware(callbacks=[callback], phase_name="draft")

    for name, call_id in (("lookup", "call-a"), ("write_file", "call-b")):

        def handler(_request: ToolCallRequest, _id: str = call_id, _n: str = name) -> ToolMessage:
            return ToolMessage(content="ok", name=_n, tool_call_id=_id)

        tracing.wrap_tool_call(_request(name=name, call_id=call_id, args={}), handler)

    started = _started_events(callback)
    finished = _tool_call_events(callback)
    assert [e.tool_call_id for e in started] == ["call-a", "call-b"]
    assert [e.tool_call_id for e in finished] == ["call-a", "call-b"]
    by_id = {e.tool_call_id: e.tool_name for e in started}
    assert by_id == {"call-a": "lookup", "call-b": "write_file"}
    assert {e.tool_call_id: e.tool_name for e in finished} == by_id


def test_provider_without_a_tool_call_id_still_yields_one_shared_identity() -> None:
    """Some providers omit the id; the pair must still be pairable."""
    callback = _RecordingCallback()
    tracing = TracingMiddleware(callbacks=[callback], phase_name="draft")
    request = _request(name="lookup", call_id=None, args={})

    def handler(_request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="ok", name="lookup", tool_call_id="whatever")

    tracing.wrap_tool_call(request, handler)

    started = _started_events(callback)
    finished = _tool_call_events(callback)
    assert started[0].tool_call_id
    assert started[0].tool_call_id == finished[0].tool_call_id


def test_started_event_is_emitted_even_when_the_tool_returns_a_command() -> None:
    """The announcement happens before the result exists, so its shape is moot.

    The completion half is only emitted for a ToolMessage; a Command-returning
    tool has its completion reported by the agent node instead. That asymmetry
    must not leak backwards into whether the call was announced.
    """
    from langgraph.types import Command

    callback = _RecordingCallback()
    tracing = TracingMiddleware(callbacks=[callback], phase_name="draft")
    request = _request(name="finish_task", call_id="finish-1", args={"reasoning": "done"})

    def handler(_request: ToolCallRequest) -> Command[Any]:
        return Command(update={})

    tracing.wrap_tool_call(request, handler)

    started = _started_events(callback)
    assert [e.tool_name for e in started] == ["finish_task"]
    assert started[0].tool_call_id == "finish-1"
