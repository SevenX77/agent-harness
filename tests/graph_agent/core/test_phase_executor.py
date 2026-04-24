"""Tests for PhaseExecutor (D-7.2).

Progressive coverage — methods are added as the extraction migrates phase
by phase. Step 4.1 covers ``execute_code_only_phase`` (the simplest node);
subsequent steps will add coverage for validation and llm phases.
"""

from __future__ import annotations

from typing import Any

from graph_agent.callbacks.base import Callback
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.state import WorkflowState
from graph_agent.core.types import Phase


class _RecordingCallback(Callback):
    """Records every `on_phase_start` / `on_phase_end` invocation."""

    def __init__(self) -> None:
        self.starts: list[tuple[str, dict[str, Any]]] = []
        self.ends: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def on_phase_start(self, phase_name: str, context_snapshot: dict[str, Any]) -> None:
        self.starts.append((phase_name, context_snapshot))

    def on_phase_end(
        self,
        phase_name: str,
        context_snapshot: dict[str, Any],
        metrics_snapshot: dict[str, Any],
    ) -> None:
        self.ends.append((phase_name, context_snapshot, metrics_snapshot))


def _make_state(
    context: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> WorkflowState:
    return {
        "context": dict(context or {}),
        "messages": [],
        "current_phase": "",
        "retry_counts": {},
        "metrics": dict(metrics or {}),
    }


class TestExecuteCodeOnlyPhase:
    def test_input_state_not_mutated(self):
        cb = _RecordingCallback()
        executor = PhaseExecutor([cb])
        phase = Phase(name="prep", requires_llm=False)
        state_in = _make_state(context={"foo": 1})

        executor.execute_code_only_phase(phase, state_in)

        assert state_in["context"] == {"foo": 1}
        assert state_in["current_phase"] == ""

    def test_on_phase_start_receives_name_and_context_snapshot(self):
        cb = _RecordingCallback()
        executor = PhaseExecutor([cb])
        phase = Phase(name="prep", requires_llm=False)
        state_in = _make_state(context={"k": "v"})

        executor.execute_code_only_phase(phase, state_in)

        assert cb.starts == [("prep", {"k": "v"})]

    def test_tools_run_in_order_string_result_sets_last_output(self):
        calls: list[str] = []

        def tool_a(ctx: dict[str, Any]) -> str:
            calls.append("a")
            return "a_out"

        def tool_b(ctx: dict[str, Any]) -> str:
            calls.append("b")
            return "b_out"

        phase = Phase(name="prep", requires_llm=False, tools=[tool_a, tool_b])
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        assert calls == ["a", "b"]
        # Last string return wins.
        assert state_out["context"]["_last_output"] == "b_out"

    def test_non_string_tool_result_does_not_set_last_output(self):
        def tool_none(ctx: dict[str, Any]) -> None:
            return None

        def tool_dict(ctx: dict[str, Any]) -> dict[str, Any]:
            return {"ignored": True}

        phase = Phase(name="prep", requires_llm=False, tools=[tool_none, tool_dict])  # type: ignore[list-item]
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        assert "_last_output" not in state_out["context"]

    def test_retry_feedback_popped_after_tools_run(self):
        captured: list[dict[str, Any]] = []

        def tool(ctx: dict[str, Any]) -> None:
            captured.append(dict(ctx))

        phase = Phase(name="prep", requires_llm=False, tools=[tool])  # type: ignore[list-item]
        executor = PhaseExecutor([])
        state_in = _make_state(context={"_retry_feedback": ["fix me"]})
        state_out = executor.execute_code_only_phase(phase, state_in)

        # Tool saw the retry feedback ...
        assert captured[0].get("_retry_feedback") == ["fix me"]
        # ... but the output state has it popped.
        assert "_retry_feedback" not in state_out["context"]

    def test_current_phase_set_on_output_state(self):
        phase = Phase(name="prep", requires_llm=False)
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        assert state_out["current_phase"] == "prep"

    def test_on_phase_end_fires_after_current_phase_set(self):
        cb = _RecordingCallback()
        phase = Phase(name="prep", requires_llm=False)
        executor = PhaseExecutor([cb])
        executor.execute_code_only_phase(phase, _make_state(metrics={"tokens": 42}))

        assert len(cb.ends) == 1
        name, ctx_snap, metrics_snap = cb.ends[0]
        assert name == "prep"
        assert metrics_snap == {"tokens": 42}
