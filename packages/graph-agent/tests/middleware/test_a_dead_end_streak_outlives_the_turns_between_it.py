"""A failure streak is counted in tool results, not in adjacent list entries.

The dead-end detector exists for one situation: the model keeps calling the
same tool, and that tool keeps failing. In a real agent loop that situation
looks like this in ``state["messages"]``::

    AIMessage(tool_calls=[finish_task])   <- turn 1
    ToolMessage(finish_task, status=error)
    AIMessage(tool_calls=[finish_task])   <- turn 2
    ToolMessage(finish_task, status=error)
    ...

The failures are never adjacent — an AIMessage sits between every pair,
because that AIMessage is what asked for the next call. A streak that stops
at the first non-tool entry can therefore only ever count the results of ONE
turn, which is the shape a model produces when it fires the same tool several
times in parallel. That is a different situation, and it is the only one the
detector could see: a real run of a fixture whose validator rejects every
submission produced SEVEN consecutive rejected ``finish_task`` calls and zero
``DeadEndPrunedEvent`` (ledger E5, measured 2026-08-21, run
``2026-08-21T07-25-48_68808cea``).

These tests pin the window in the shape production actually has.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import DeadEndPrunedEvent
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.execution_control import ExecutionControlMiddleware


class _RecordingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def pruned(self) -> list[DeadEndPrunedEvent]:
        return [event for event in self.events if isinstance(event, DeadEndPrunedEvent)]


def _turn(tool: str, *, error: str | None, index: int) -> list[Any]:
    """One model turn: the call the model made, and the result it got back."""
    call_id = f"call-{index}"
    request = AIMessage(content="", tool_calls=[{"name": tool, "args": {}, "id": call_id}])
    if error is None:
        result = ToolMessage(content="ok", name=tool, tool_call_id=call_id)
    else:
        result = ToolMessage(content=error, name=tool, tool_call_id=call_id, status="error")
    return [request, result]


def _history(*turns: list[Any]) -> list[Any]:
    """The turns so far, plus the call the model just made.

    ``after_model`` runs immediately after the model speaks, so the newest
    entry is always an AIMessage whose result has not come back yet.
    """
    messages: list[Any] = []
    for turn in turns:
        messages.extend(turn)
    messages.append(AIMessage(content="", tool_calls=[{"name": "finish_task", "args": {}, "id": "pending"}]))
    return messages


def _state(messages: list[Any]) -> WorkflowState:
    return {
        "data": BusinessData(),
        "flow": FrameworkState(),
        "messages": messages,
    }


def _after_model(middleware: ExecutionControlMiddleware, messages: list[Any]) -> dict[str, Any] | None:
    return middleware.after_model(_state(messages), runtime=None)  # type: ignore[arg-type]


def test_three_failures_spread_over_three_turns_trip_the_detector() -> None:
    callback = _RecordingCallback()
    middleware = ExecutionControlMiddleware(
        dead_end_threshold=3,
        phase_name="impossible",
        callbacks=[callback],
    )
    messages = _history(*[_turn("finish_task", error="rejected", index=i) for i in range(3)])

    result = _after_model(middleware, messages)

    assert result is not None, "three rejected calls in a row is exactly the dead end this exists for"
    warning = result["messages"][0]
    assert warning.name == "dead_end_warning"
    assert "finish_task" in warning.content
    assert "3" in warning.content
    assert [event.phase_name for event in callback.pruned()] == ["impossible"]


def test_two_failures_over_two_turns_stay_below_the_line() -> None:
    middleware = ExecutionControlMiddleware(dead_end_threshold=3)
    messages = _history(*[_turn("finish_task", error="rejected", index=i) for i in range(2)])

    assert _after_model(middleware, messages) is None


def test_a_success_ends_the_streak_even_with_older_failures_behind_it() -> None:
    middleware = ExecutionControlMiddleware(dead_end_threshold=3)
    messages = _history(
        _turn("finish_task", error="rejected", index=0),
        _turn("finish_task", error="rejected", index=1),
        _turn("finish_task", error="rejected", index=2),
        _turn("finish_task", error=None, index=3),
    )

    assert _after_model(middleware, messages) is None


def test_another_tool_ends_the_streak() -> None:
    middleware = ExecutionControlMiddleware(dead_end_threshold=3)
    messages = _history(
        _turn("finish_task", error="rejected", index=0),
        _turn("finish_task", error="rejected", index=1),
        _turn("read_artifact", error="missing", index=2),
    )

    assert _after_model(middleware, messages) is None


def test_the_streak_restarts_at_the_warning_already_given() -> None:
    """Being warned once is what resets the count — not an instance attribute.

    The warning is a message in the same history the count is read from, so a
    fresh middleware reading that history reaches the same conclusion. That
    matters because ONE middleware instance serves every batch item, loop round
    and resume of a phase (see ``_iterations_by_invocation``), so anything
    remembered on the instance leaks across them.
    """
    middleware = ExecutionControlMiddleware(dead_end_threshold=3)
    warned = _history(*[_turn("finish_task", error="rejected", index=i) for i in range(3)])
    first = _after_model(middleware, warned)
    assert first is not None

    already_warned = [*warned[:-1], first["messages"][0]]
    two_more = [
        *already_warned,
        *_turn("finish_task", error="rejected", index=3),
        *_turn("finish_task", error="rejected", index=4),
        AIMessage(content="", tool_calls=[{"name": "finish_task", "args": {}, "id": "pending"}]),
    ]

    assert _after_model(ExecutionControlMiddleware(dead_end_threshold=3), two_more) is None

    three_more = [
        *two_more[:-1],
        *_turn("finish_task", error="rejected", index=5),
        AIMessage(content="", tool_calls=[{"name": "finish_task", "args": {}, "id": "pending"}]),
    ]

    assert _after_model(ExecutionControlMiddleware(dead_end_threshold=3), three_more) is not None
