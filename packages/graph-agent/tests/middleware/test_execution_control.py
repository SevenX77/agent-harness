"""Tests for MVP-3 T9 ExecutionControlMiddleware."""

from __future__ import annotations

from typing import Any

import pytest
from graph_agent.callbacks.base import Callback
from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    WorkflowState,
)
from graph_agent.middleware.execution_control import ExecutionControlMiddleware
from langchain_core.messages import HumanMessage, ToolMessage


class _RecordingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[Any] = []
        self.dead_ends: list[tuple[str, str]] = []
        self.loops: list[tuple[str, str, int]] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def on_dead_end_pruned(self, phase_name: str, warning: str) -> None:
        self.dead_ends.append((phase_name, warning))

    def on_loop_detected(self, phase_name: str, signature: str, hits: int) -> None:
        self.loops.append((phase_name, signature, hits))


def _state(messages: list[Any] | None = None) -> WorkflowState:
    return {
        "data": BusinessData(),
        "flow": FrameworkState(metrics={"tokens": 100}),
        "messages": messages if messages is not None else [],
    }


def _failing_tool_message(name: str, content: str) -> ToolMessage:
    msg = ToolMessage(name=name, content=content, tool_call_id=f"call-{name}")
    msg.status = "error"  # type: ignore[attr-defined]
    return msg


class TestInit:
    def test_init_defaults(self) -> None:
        mw = ExecutionControlMiddleware()

        assert mw._max_retries == 3
        assert mw._max_iterations == 20
        assert mw._dead_end_threshold == 3
        assert mw.iteration == 0
        assert mw._phase_name == "unknown"

    def test_init_clamps_invalid_values(self) -> None:
        # ``max_retries`` floors at 0, ``max_iterations`` floors at 1,
        # thresholds floor at sensible minimums.
        mw = ExecutionControlMiddleware(
            max_retries=-5,
            max_iterations=0,
            dead_end_threshold=0,
            loop_window=0,
            loop_threshold=1,
        )

        assert mw._max_retries == 0
        assert mw._max_iterations == 1
        assert mw._dead_end_threshold == 1
        assert mw._loop_window == 1
        assert mw._loop_threshold == 2  # floors at 2 (single hit isn't a loop)


class TestIterationCounter:
    def test_iteration_increments_on_each_before_model(self) -> None:
        mw = ExecutionControlMiddleware()
        state = _state()

        mw.before_model(state, runtime=None)  # type: ignore[arg-type]
        mw.before_model(state, runtime=None)  # type: ignore[arg-type]
        mw.before_model(state, runtime=None)  # type: ignore[arg-type]

        assert mw.iteration == 3

    def test_iteration_event_fires_with_phase_name(self) -> None:
        cb = _RecordingCallback()
        mw = ExecutionControlMiddleware(phase_name="segment", callbacks=[cb])

        mw.before_model(_state(), runtime=None)  # type: ignore[arg-type]
        mw.before_model(_state(), runtime=None)  # type: ignore[arg-type]

        assert len(cb.events) == 2
        # AgentLoopIterationEvent carries phase_name + iteration.
        assert all(e.phase_name == "segment" for e in cb.events)
        assert [e.iteration for e in cb.events] == [1, 2]

    def test_callback_failure_does_not_break_loop(self) -> None:
        class _BadCallback(Callback):
            def on_event(self, event: Any) -> None:
                raise RuntimeError("callback exploded")

        mw = ExecutionControlMiddleware(callbacks=[_BadCallback()])
        # Must not raise; the iteration counter must still advance.
        result = mw.before_model(_state(), runtime=None)  # type: ignore[arg-type]

        assert result is None
        assert mw.iteration == 1


class TestDeadEndDetection:
    def test_no_warning_when_no_failures(self) -> None:
        mw = ExecutionControlMiddleware()
        state = _state(messages=[HumanMessage(content="hi")])

        result = mw.after_model(state, runtime=None)  # type: ignore[arg-type]

        assert result is None

    def test_no_warning_below_threshold(self) -> None:
        mw = ExecutionControlMiddleware(dead_end_threshold=3)
        # Two failures — below the threshold of three.
        messages = [
            _failing_tool_message("read_file", "denied"),
            _failing_tool_message("read_file", "denied"),
        ]
        result = mw.after_model(_state(messages=messages), runtime=None)  # type: ignore[arg-type]

        assert result is None

    def test_warning_injected_at_threshold(self) -> None:
        cb = _RecordingCallback()
        mw = ExecutionControlMiddleware(dead_end_threshold=3, phase_name="probe", callbacks=[cb])
        messages = [
            _failing_tool_message("read_file", "permission denied"),
            _failing_tool_message("read_file", "permission denied"),
            _failing_tool_message("read_file", "permission denied"),
        ]
        result = mw.after_model(_state(messages=messages), runtime=None)  # type: ignore[arg-type]

        assert result is not None
        warnings = result["messages"]
        assert len(warnings) == 1
        warning = warnings[0]
        assert warning.name == "dead_end_warning"
        assert "read_file" in warning.content
        # Callback fired once with the structured payload.
        assert cb.dead_ends == [("probe", warning.content)]

    def test_warning_deduped_by_signature(self) -> None:
        """Calling after_model twice with the same failure pattern must
        emit the warning exactly once — repeated injections would spam
        the LLM context with duplicate guidance."""
        mw = ExecutionControlMiddleware(dead_end_threshold=3)
        messages = [
            _failing_tool_message("read_file", "denied"),
            _failing_tool_message("read_file", "denied"),
            _failing_tool_message("read_file", "denied"),
        ]

        first = mw.after_model(_state(messages=messages), runtime=None)  # type: ignore[arg-type]
        second = mw.after_model(_state(messages=messages), runtime=None)  # type: ignore[arg-type]

        assert first is not None
        assert second is None  # signature unchanged → suppressed

    def test_warning_streak_broken_by_different_tool(self) -> None:
        mw = ExecutionControlMiddleware(dead_end_threshold=3)
        # Two failing read_file then one failing write_file — streak resets.
        messages = [
            _failing_tool_message("read_file", "denied"),
            _failing_tool_message("read_file", "denied"),
            _failing_tool_message("write_file", "denied"),
        ]
        result = mw.after_model(_state(messages=messages), runtime=None)  # type: ignore[arg-type]

        assert result is None


class TestLoopDetection:
    def test_no_callback_when_no_repetition(self) -> None:
        cb = _RecordingCallback()
        mw = ExecutionControlMiddleware(loop_window=5, loop_threshold=3, callbacks=[cb])
        # Three different tool calls — no repetition.
        messages = [
            ToolMessage(name="t1", content="a", tool_call_id="1"),
            ToolMessage(name="t2", content="b", tool_call_id="2"),
            ToolMessage(name="t3", content="c", tool_call_id="3"),
        ]
        mw.after_model(_state(messages=messages), runtime=None)  # type: ignore[arg-type]

        assert cb.loops == []

    def test_loop_callback_fires_at_threshold(self) -> None:
        cb = _RecordingCallback()
        mw = ExecutionControlMiddleware(
            loop_window=5,
            loop_threshold=3,
            dead_end_threshold=999,
            phase_name="loopy",
            callbacks=[cb],
        )
        # Same (name, content) triple — loop_threshold met.
        messages = [
            ToolMessage(name="search", content="q=foo", tool_call_id="1"),
            ToolMessage(name="search", content="q=foo", tool_call_id="2"),
            ToolMessage(name="search", content="q=foo", tool_call_id="3"),
        ]
        mw.after_model(_state(messages=messages), runtime=None)  # type: ignore[arg-type]

        assert len(cb.loops) == 1
        phase, signature, hits = cb.loops[0]
        assert phase == "loopy"
        assert signature.startswith("search:")
        assert hits == 3


class TestCollectMetrics:
    def test_collect_metrics_returns_flow_metrics(self) -> None:
        mw = ExecutionControlMiddleware()
        state = _state()
        # Default fixture sets metrics={'tokens': 100}.

        snap = mw.collect_metrics(state)

        assert snap == {"tokens": 100}
        # Returned a copy — caller mutation must not affect state.
        snap["tokens"] = 0
        assert state["flow"].metrics == {"tokens": 100}

    def test_collect_metrics_handles_non_workflow_state(self) -> None:
        mw = ExecutionControlMiddleware()

        # LangGraph default AgentState — no flow key.
        assert mw.collect_metrics({"messages": []}) == {}
        # Non-dict input — returns empty.
        assert mw.collect_metrics(None) == {}


class TestNoOpForNonWorkflowState:
    def test_after_model_non_workflow_state_returns_none(self) -> None:
        mw = ExecutionControlMiddleware()
        # default LangGraph AgentState (no ``flow``/``data`` keys).
        result = mw.after_model({"messages": []}, runtime=None)  # type: ignore[arg-type]

        assert result is None
        # Iteration counter only fires in before_model, not after_model.
        assert mw.iteration == 0


@pytest.mark.parametrize("threshold", [1, 3, 5])
class TestDeadEndThresholdParametrized:
    def test_threshold_respected(self, threshold: int) -> None:
        mw = ExecutionControlMiddleware(dead_end_threshold=threshold)
        # ``threshold`` consecutive failures — exactly at the line.
        messages = [_failing_tool_message("t", "err") for _ in range(threshold)]
        assert mw.after_model(_state(messages=messages), runtime=None) is not None  # type: ignore[arg-type]

    def test_below_threshold_no_warning(self, threshold: int) -> None:
        if threshold == 1:
            pytest.skip("threshold=1 has no 'below' state")
        mw = ExecutionControlMiddleware(dead_end_threshold=threshold)
        messages = [_failing_tool_message("t", "err") for _ in range(threshold - 1)]
        assert mw.after_model(_state(messages=messages), runtime=None) is None  # type: ignore[arg-type]
