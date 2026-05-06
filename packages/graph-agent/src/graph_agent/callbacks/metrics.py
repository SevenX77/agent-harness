"""Built-in callback that accumulates token usage and timing."""
from __future__ import annotations

import logging
import time
from typing import Any

from .base import Callback

logger = logging.getLogger(__name__)


class MetricsCallback(Callback):
    """Built-in callback that accumulates token usage and timing."""

    def __init__(self) -> None:
        """Initialize metric counters for one run."""
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_tool_calls: int = 0
        self.total_validation_failures: int = 0
        self.total_retries: int = 0
        self.total_finish_tasks: int = 0
        self.total_nudges: int = 0
        self.total_working_memory_updates: int = 0
        self.total_ambiguity_reports: int = 0
        self.total_dead_end_prunes: int = 0
        self.total_compactions: int = 0
        self.phase_durations: dict[str, list[float]] = {}
        self._phase_start_times: dict[str, float] = {}

    def on_phase_start(self, phase_name: str, context: dict[str, Any]) -> None:
        """Record phase start time."""
        self._phase_start_times[phase_name] = time.monotonic()

    def on_phase_end(
        self,
        phase_name: str,
        context: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        """Record phase duration."""
        start = self._phase_start_times.pop(phase_name, None)
        if start is not None:
            self.phase_durations.setdefault(phase_name, []).append(
                time.monotonic() - start
            )

    def on_llm_call(
        self,
        phase_name: str,
        input_tokens: int,
        output_tokens: int,
        *,
        messages: list[dict[str, Any]] | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        """Accumulate token counts."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def on_tool_call(
        self,
        phase_name: str,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        *,
        duration_ms: float | None = None,
    ) -> None:
        """Count tool calls."""
        self.total_tool_calls += 1

    def on_validation_fail(
        self,
        phase_name: str,
        errors: list[str],
        retry_count: int,
    ) -> None:
        """Count validation failures."""
        self.total_validation_failures += 1

    def on_retry(
        self,
        phase_name: str,
        target_phase: str,
        feedback: list[str],
    ) -> None:
        """Count retries."""
        self.total_retries += 1

    def on_nudge(
        self,
        phase_name: str,
        nudge_count: int,
        nudge_type: str = "standard",
    ) -> None:
        """Count nudges."""
        self.total_nudges += 1

    def on_finish_task(
        self,
        phase_name: str,
        reasoning: str,
        evidence: list[str],
    ) -> None:
        """Count finish_task calls."""
        self.total_finish_tasks += 1

    def on_working_memory_update(
        self,
        phase_name: str,
        content_length: int,
    ) -> None:
        """Count working-memory updates."""
        self.total_working_memory_updates += 1

    def on_dead_end_pruned(
        self,
        phase_name: str,
        summary: str,
    ) -> None:
        """Count dead-end pruning events."""
        self.total_dead_end_prunes += 1

    def on_compaction(
        self,
        phase_name: str,
        removed_pairs: int,
    ) -> None:
        """Count history compactions."""
        self.total_compactions += 1

    def on_ambiguity_report(
        self,
        phase_name: str,
        ambiguity_type: str,
        question: str,
        decision: str,
    ) -> None:
        """Count ambiguity reports."""
        self.total_ambiguity_reports += 1

    def summary(self) -> dict[str, Any]:
        """Return accumulated metrics as a dictionary."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tool_calls": self.total_tool_calls,
            "total_validation_failures": self.total_validation_failures,
            "total_retries": self.total_retries,
            "total_finish_tasks": self.total_finish_tasks,
            "total_nudges": self.total_nudges,
            "total_working_memory_updates": self.total_working_memory_updates,
            "total_ambiguity_reports": self.total_ambiguity_reports,
            "total_dead_end_prunes": self.total_dead_end_prunes,
            "total_compactions": self.total_compactions,
            "phase_durations": {k: list(v) for k, v in self.phase_durations.items()},
        }
