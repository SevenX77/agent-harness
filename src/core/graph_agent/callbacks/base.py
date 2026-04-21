"""Event callback mechanism for monitoring Agent execution.

Business layer can implement concrete callbacks to observe phase transitions,
LLM calls, tool executions, validation failures, and retries.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

EVENT_PHASE_START = "phase_start"
EVENT_PHASE_END = "phase_end"
EVENT_LLM_CALL = "llm_call"
EVENT_TOOL_CALL = "tool_call"
EVENT_VALIDATION_FAIL = "validation_fail"
EVENT_RETRY = "retry"
EVENT_FINISH_TASK = "finish_task"
EVENT_NUDGE = "nudge"
EVENT_WORKING_MEMORY_UPDATE = "working_memory_update"
EVENT_DEAD_END_PRUNED = "dead_end_pruned"
EVENT_COMPACTION = "compaction"
EVENT_AMBIGUITY_REPORT = "ambiguity_report"


class Callback:
    """Base callback with no-op default implementations.

    Subclass and override the methods you care about.
    """

    def on_phase_start(self, phase_name: str, context: dict[str, Any]) -> None:
        """Handle phase start."""

    def on_phase_end(
        self,
        phase_name: str,
        context: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        """Handle phase end."""

    def on_llm_call(
        self,
        phase_name: str,
        input_tokens: int,
        output_tokens: int,
        *,
        messages: list[dict[str, Any]] | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        """Handle one LLM call."""

    def on_tool_call(
        self,
        phase_name: str,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        *,
        duration_ms: float | None = None,
    ) -> None:
        """Handle one tool call."""

    def on_validation_fail(
        self,
        phase_name: str,
        errors: list[str],
        retry_count: int,
    ) -> None:
        """Handle validator failure."""

    def on_retry(
        self,
        phase_name: str,
        target_phase: str,
        feedback: list[str],
    ) -> None:
        """Handle retry routing."""

    def on_finish_task(
        self,
        phase_name: str,
        reasoning: str,
        evidence: list[str],
    ) -> None:
        """Handle explicit finish_task completion."""

    def on_nudge(
        self,
        phase_name: str,
        nudge_count: int,
        nudge_type: str = "standard",
    ) -> None:
        """Handle a cognitive nudge."""

    def on_working_memory_update(
        self,
        phase_name: str,
        content_length: int,
    ) -> None:
        """Handle working-memory update."""

    def on_dead_end_pruned(
        self,
        phase_name: str,
        summary: str,
    ) -> None:
        """Handle dead-end pruning."""

    def on_compaction(
        self,
        phase_name: str,
        removed_pairs: int,
    ) -> None:
        """Handle history compaction."""

    def on_ambiguity_report(
        self,
        phase_name: str,
        ambiguity_type: str,
        question: str,
        decision: str,
    ) -> None:
        """Handle one ambiguity report."""


__all__ = [
    "Callback",
    "EVENT_PHASE_START",
    "EVENT_PHASE_END",
    "EVENT_LLM_CALL",
    "EVENT_TOOL_CALL",
    "EVENT_VALIDATION_FAIL",
    "EVENT_RETRY",
    "EVENT_FINISH_TASK",
    "EVENT_NUDGE",
    "EVENT_WORKING_MEMORY_UPDATE",
    "EVENT_DEAD_END_PRUNED",
    "EVENT_COMPACTION",
    "EVENT_AMBIGUITY_REPORT",
]
