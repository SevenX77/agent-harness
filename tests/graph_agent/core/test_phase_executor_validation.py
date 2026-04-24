"""Tests for PhaseExecutor.execute_validation_phase (D-7.2 step 4.2)."""

from __future__ import annotations

from typing import Any

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import (
    RetryExhaustedEvent,
    ValidationPassEvent,
)
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.state import WorkflowState
from graph_agent.core.types import Phase


class _RecordingCallback(Callback):
    def __init__(self) -> None:
        self.validation_fails: list[tuple[str, list[str], int]] = []
        self.retries: list[tuple[str, str, list[str]]] = []
        self.events: list[Any] = []

    def on_validation_fail(
        self,
        phase_name: str,
        errors: list[str],
        retry_count: int,
    ) -> None:
        self.validation_fails.append((phase_name, list(errors), retry_count))

    def on_retry(
        self,
        phase_name: str,
        retry_target: str,
        errors: list[str],
    ) -> None:
        self.retries.append((phase_name, retry_target, list(errors)))

    def on_event(self, event: Any) -> None:
        self.events.append(event)


def _make_state(
    *,
    context: dict[str, Any] | None = None,
    retry_counts: dict[str, int] | None = None,
) -> WorkflowState:
    return {
        "context": dict(context or {}),
        "messages": [],
        "current_phase": "",
        "retry_counts": dict(retry_counts or {}),
        "metrics": {},
    }


class TestExecuteValidationPhase:
    def test_no_validator_clones_and_returns_without_callbacks(self):
        cb = _RecordingCallback()
        executor = PhaseExecutor([cb])
        phase = Phase(name="analyse")  # validator is None by default

        state_in = _make_state(context={"foo": 1})
        state_out = executor.execute_validation_phase(phase, state_in)

        assert state_out["context"] == {"foo": 1}
        # Cloned: mutating out doesn't change in.
        state_out["context"]["new"] = "x"
        assert "new" not in state_in["context"]
        assert cb.events == []
        assert cb.validation_fails == []
        assert cb.retries == []

    def test_validator_passes_pops_retry_key_and_emits_pass_event(self):
        cb = _RecordingCallback()

        def validator(ctx: dict[str, Any]) -> tuple[bool, list[str]]:
            return True, []

        phase = Phase(name="analyse", validator=validator)
        executor = PhaseExecutor([cb])
        state_in = _make_state(retry_counts={"analyse": 2, "other": 1})

        state_out = executor.execute_validation_phase(phase, state_in)

        assert "analyse" not in state_out["retry_counts"]
        assert state_out["retry_counts"]["other"] == 1
        # ValidationPassEvent emitted with the pre-pop retry count.
        pass_events = [e for e in cb.events if isinstance(e, ValidationPassEvent)]
        assert len(pass_events) == 1
        assert pass_events[0].phase_name == "analyse"
        assert pass_events[0].retry_count == 2

    def test_validator_passes_pops_validation_warnings_from_context(self):
        def validator(ctx: dict[str, Any]) -> tuple[bool, list[str]]:
            return True, []

        phase = Phase(name="analyse", validator=validator)
        executor = PhaseExecutor([])
        state_in = _make_state(context={"_validation_warnings": ["stale"]})

        state_out = executor.execute_validation_phase(phase, state_in)

        assert "_validation_warnings" not in state_out["context"]

    def test_validator_passes_retry_target_shapes_retry_key(self):
        """Retry key prefers retry_target over phase.name on pass path."""
        def validator(ctx: dict[str, Any]) -> tuple[bool, list[str]]:
            return True, []

        phase = Phase(name="analyse", retry_target="precheck", validator=validator)
        executor = PhaseExecutor([])
        state_in = _make_state(retry_counts={"precheck": 1, "analyse": 99})

        state_out = executor.execute_validation_phase(phase, state_in)

        # retry_target's bucket popped; phase.name's bucket untouched.
        assert "precheck" not in state_out["retry_counts"]
        assert state_out["retry_counts"]["analyse"] == 99

    def test_validator_fails_under_retry_budget_sets_feedback_and_increments(self):
        cb = _RecordingCallback()

        def validator(ctx: dict[str, Any]) -> tuple[bool, list[str]]:
            return False, ["missing field X"]

        phase = Phase(name="analyse", validator=validator, max_retries=3)
        executor = PhaseExecutor([cb])
        state_in = _make_state(retry_counts={"analyse": 1})

        state_out = executor.execute_validation_phase(phase, state_in)

        assert state_out["context"]["_retry_feedback"] == ["missing field X"]
        assert state_out["retry_counts"]["analyse"] == 2
        assert cb.validation_fails == [("analyse", ["missing field X"], 1)]
        assert cb.retries == [("analyse", "analyse", ["missing field X"])]
        # No RetryExhaustedEvent since budget not reached.
        exhausted = [e for e in cb.events if isinstance(e, RetryExhaustedEvent)]
        assert exhausted == []

    def test_validator_fails_at_retry_budget_emits_exhausted_and_sets_warnings(self):
        cb = _RecordingCallback()

        def validator(ctx: dict[str, Any]) -> tuple[bool, list[str]]:
            return False, ["still broken"]

        phase = Phase(name="analyse", validator=validator, max_retries=3)
        executor = PhaseExecutor([cb])
        state_in = _make_state(retry_counts={"analyse": 3})

        state_out = executor.execute_validation_phase(phase, state_in)

        # No _retry_feedback injected; retry_counts not bumped.
        assert "_retry_feedback" not in state_out["context"]
        assert state_out["retry_counts"]["analyse"] == 3
        assert state_out["context"]["_validation_warnings"] == ["still broken"]
        assert cb.validation_fails == [("analyse", ["still broken"], 3)]
        # Retry callback NOT fired since we've exhausted.
        assert cb.retries == []
        exhausted = [e for e in cb.events if isinstance(e, RetryExhaustedEvent)]
        assert len(exhausted) == 1
        assert exhausted[0].phase_name == "analyse"
        assert exhausted[0].max_retries == 3
        assert exhausted[0].final_errors == ["still broken"]

    def test_validator_fails_retry_target_flows_into_on_retry_and_counter(self):
        cb = _RecordingCallback()

        def validator(ctx: dict[str, Any]) -> tuple[bool, list[str]]:
            return False, ["bad"]

        phase = Phase(
            name="analyse",
            retry_target="precheck",
            validator=validator,
            max_retries=2,
        )
        executor = PhaseExecutor([cb])
        state_in = _make_state(retry_counts={"precheck": 0})

        state_out = executor.execute_validation_phase(phase, state_in)

        # Counter increment lives in retry_target bucket.
        assert state_out["retry_counts"]["precheck"] == 1
        assert "analyse" not in state_out["retry_counts"]
        # on_retry receives retry_target as the "target" arg.
        assert cb.retries == [("analyse", "precheck", ["bad"])]

    def test_input_state_not_mutated_even_on_retry_path(self):
        def validator(ctx: dict[str, Any]) -> tuple[bool, list[str]]:
            return False, ["e1"]

        phase = Phase(name="analyse", validator=validator, max_retries=5)
        executor = PhaseExecutor([])
        state_in = _make_state(
            context={"existing": "v"}, retry_counts={"analyse": 0}
        )

        executor.execute_validation_phase(phase, state_in)

        assert state_in["context"] == {"existing": "v"}
        assert state_in["retry_counts"] == {"analyse": 0}
