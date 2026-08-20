"""Built-in callback that logs all key events via Python logging."""

from __future__ import annotations

import logging

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import (
    CallbackEvent,
    CompactionEvent,
    DeadEndPrunedEvent,
    LLMCallEvent,
    NudgeEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    ToolCallEvent,
    WorkingMemoryUpdateEvent,
)

logger = logging.getLogger(__name__)

_RESULT_PREVIEW_CHARS = 200
_SUMMARY_PREVIEW_CHARS = 100


class LoggingCallback(Callback):
    """Built-in callback that logs all key events via Python logging."""

    def on_event(self, event: CallbackEvent) -> None:
        """Log the event kinds this callback narrates; ignore the rest."""
        if isinstance(event, PhaseStartEvent):
            logger.info("[Phase Start] %s", event.phase_name)
        elif isinstance(event, PhaseEndEvent):
            logger.info("[Phase End] %s | execution=%s", event.phase_name, event.phase_execution_id)
        elif isinstance(event, LLMCallEvent):
            logger.info(
                "[LLM Call] %s | in=%d out=%d",
                event.phase_name,
                event.input_tokens,
                event.output_tokens,
            )
        elif isinstance(event, ToolCallEvent):
            result = event.result
            preview = (
                result[:_RESULT_PREVIEW_CHARS] + "..."
                if len(result) > _RESULT_PREVIEW_CHARS
                else result
            )
            logger.info(
                "[Tool Call] %s.%s | result=%s", event.phase_name, event.tool_name, preview
            )
        elif isinstance(event, NudgeEvent):
            logger.warning(
                "[Nudge] %s | type=%s count=%d",
                event.phase_name,
                event.nudge_type,
                event.nudge_count,
            )
        elif isinstance(event, WorkingMemoryUpdateEvent):
            logger.info(
                "[Working Memory Update] %s | len=%d",
                event.phase_name,
                event.content_length,
            )
        elif isinstance(event, DeadEndPrunedEvent):
            logger.warning(
                "[Dead-End Pruned] %s | summary=%s",
                event.phase_name,
                event.summary[:_SUMMARY_PREVIEW_CHARS],
            )
        elif isinstance(event, CompactionEvent):
            logger.info(
                "[Compaction] %s | removed=%d message(s)",
                event.phase_name,
                event.removed_message_count,
            )
