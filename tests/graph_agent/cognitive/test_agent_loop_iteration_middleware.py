"""Unit tests for ``AgentLoopIterationMiddleware`` (cognitive/middlewares.py).

The middleware's contract:

* Fires exactly once per ``before_model`` hook — the counter is the
  iteration number Studio uses to group LLM/Tool events within a turn.
* Counter is 1-based and strictly monotonic across hook calls.
* Emits an ``AgentLoopIterationEvent`` with matching ``phase_name`` +
  ``iteration`` to every registered callback.
* A raising callback must not block other callbacks or the hook
  pass-through (middleware never mutates state, always returns None).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src" / "core"))

from graph_agent.callbacks.base import Callback  # noqa: E402
from graph_agent.callbacks.events import AgentLoopIterationEvent  # noqa: E402
from graph_agent.cognitive.middlewares import AgentLoopIterationMiddleware  # noqa: E402


class _RecordingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class _RaisingCallback(Callback):
    def __init__(self) -> None:
        self.call_count = 0

    def on_event(self, event: Any) -> None:
        self.call_count += 1
        raise RuntimeError("boom")


class TestAgentLoopIterationMiddleware:
    """Contract tests for AgentLoopIterationMiddleware."""

    def test_before_model_returns_none(self) -> None:
        """Middleware is pass-through — it never mutates AgentState."""
        mw = AgentLoopIterationMiddleware(phase_name="p1", callbacks=[])
        result = mw.before_model(state={"messages": []}, runtime=None)  # type: ignore[arg-type]
        assert result is None

    def test_iteration_counter_is_one_based_and_monotonic(self) -> None:
        cb = _RecordingCallback()
        mw = AgentLoopIterationMiddleware(phase_name="p2", callbacks=[cb])

        for _ in range(3):
            mw.before_model(state={"messages": []}, runtime=None)  # type: ignore[arg-type]

        assert [e.iteration for e in cb.events] == [1, 2, 3]
        assert all(e.phase_name == "p2" for e in cb.events)
        assert all(isinstance(e, AgentLoopIterationEvent) for e in cb.events)

    def test_multiple_callbacks_all_receive_event(self) -> None:
        cb_a = _RecordingCallback()
        cb_b = _RecordingCallback()
        mw = AgentLoopIterationMiddleware(
            phase_name="p3",
            callbacks=[cb_a, cb_b],
        )
        mw.before_model(state={"messages": []}, runtime=None)  # type: ignore[arg-type]

        assert len(cb_a.events) == 1
        assert len(cb_b.events) == 1
        assert cb_a.events[0].iteration == 1
        assert cb_b.events[0].iteration == 1

    def test_raising_callback_does_not_block_others(self) -> None:
        """A buggy callback must not prevent other callbacks from receiving
        the event, and must not cause ``before_model`` itself to raise.
        """
        bad = _RaisingCallback()
        good = _RecordingCallback()
        mw = AgentLoopIterationMiddleware(
            phase_name="p4",
            callbacks=[bad, good],
        )

        # No exception propagates out of before_model.
        result = mw.before_model(state={"messages": []}, runtime=None)  # type: ignore[arg-type]
        assert result is None

        # Both callbacks were invoked — the good one still received the event
        # even though the bad one raised during its turn.
        assert bad.call_count == 1
        assert len(good.events) == 1
        assert good.events[0].iteration == 1

    def test_no_callbacks_is_valid(self) -> None:
        """Middleware must work when constructed without any callbacks
        (counter still ticks; nothing is emitted).
        """
        mw = AgentLoopIterationMiddleware(phase_name="p5", callbacks=None)
        mw.before_model(state={"messages": []}, runtime=None)  # type: ignore[arg-type]
        mw.before_model(state={"messages": []}, runtime=None)  # type: ignore[arg-type]
        assert mw._iteration == 2
