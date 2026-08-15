"""Built-in callback that logs all key events via Python logging."""

from __future__ import annotations

import logging
from typing import Any

from graph_agent.callbacks.base import Callback

logger = logging.getLogger(__name__)


class LoggingCallback(Callback):
    """Built-in callback that logs all key events via Python logging."""

    def on_phase_start(self, phase_name: str, context: dict[str, Any]) -> None:
        """Log phase start."""
        logger.info("[Phase Start] %s", phase_name)

    def on_phase_end(
        self,
        phase_name: str,
        context: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        """Log phase end."""
        logger.info("[Phase End] %s | metrics=%s", phase_name, metrics)

    def on_llm_call(
        self,
        phase_name: str,
        input_tokens: int,
        output_tokens: int,
        *,
        messages: list[dict[str, Any]] | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        """Log one LLM call."""
        logger.info(
            "[LLM Call] %s | in=%d out=%d",
            phase_name,
            input_tokens,
            output_tokens,
        )

    def on_tool_call(
        self,
        phase_name: str,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        *,
        duration_ms: float | None = None,
    ) -> None:
        """Log one tool call."""
        preview = result[:200] + "..." if len(result) > 200 else result
        logger.info("[Tool Call] %s.%s | result=%s", phase_name, tool_name, preview)

    def on_validation_fail(
        self,
        phase_name: str,
        errors: list[str],
        retry_count: int,
    ) -> None:
        """Log validator failure."""
        logger.warning(
            "[Validation Fail] %s | retry=%d | errors=%s",
            phase_name,
            retry_count,
            errors,
        )

    def on_retry(
        self,
        phase_name: str,
        target_phase: str,
        feedback: list[str],
    ) -> None:
        """Log retry routing."""
        logger.info("[Retry] %s → %s", phase_name, target_phase)

    def on_finish_task(
        self,
        phase_name: str,
        reasoning: str,
        evidence: list[str],
    ) -> None:
        """Log finish_task completion."""
        logger.info(
            "[Finish Task] %s | evidence=%d items",
            phase_name,
            len(evidence),
        )

    def on_nudge(
        self,
        phase_name: str,
        nudge_count: int,
        nudge_type: str = "standard",
    ) -> None:
        """Log one nudge."""
        logger.warning("[Nudge] %s | type=%s count=%d", phase_name, nudge_type, nudge_count)

    def on_working_memory_update(
        self,
        phase_name: str,
        content_length: int,
    ) -> None:
        """Log working-memory update."""
        logger.info(
            "[Working Memory Update] %s | len=%d",
            phase_name,
            content_length,
        )

    def on_dead_end_pruned(
        self,
        phase_name: str,
        summary: str,
    ) -> None:
        """Log dead-end pruning."""
        logger.warning("[Dead-End Pruned] %s | summary=%s", phase_name, summary[:100])

    def on_compaction(
        self,
        phase_name: str,
        removed_message_count: int,
    ) -> None:
        """Log history compaction."""
        logger.info(
            "[Compaction] %s | removed=%d message(s)", phase_name, removed_message_count
        )

    def on_ambiguity_report(
        self,
        phase_name: str,
        ambiguity_type: str,
        question: str,
        decision: str,
    ) -> None:
        """Log one ambiguity report."""
        logger.info(
            "[Ambiguity Report] %s | type=%s | decision=%s",
            phase_name,
            ambiguity_type,
            decision,
        )
