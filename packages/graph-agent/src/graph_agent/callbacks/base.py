"""Event callback mechanism for monitoring Agent execution.

Business layer can implement concrete callbacks to observe phase transitions,
LLM calls, tool executions, validation failures, and retries.

As of Task 3.5, subclasses may also override :meth:`Callback.on_event` to
receive a typed :class:`~graph_agent.callbacks.events.CallbackEvent` union
member instead of individual string-typed hook methods. The default
``on_event`` dispatches back to the legacy ``on_*`` methods so existing
callbacks keep working unchanged — emitters can gradually migrate to
calling ``on_event(event)`` with a Pydantic payload.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from graph_agent.callbacks.events import CallbackEvent

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

    def on_event(self, event: CallbackEvent) -> None:
        """Typed event sink — new-style entrypoint introduced by Task 3.5.

        The default implementation dispatches a :class:`CallbackEvent` member
        back to the matching legacy ``on_*`` hook so subclasses that only
        override the old hooks keep working. Override this method directly
        to receive the full typed payload (including the new
        ``prompt_captured`` / ``llm_fallback`` events and the
        ``sub_run_id`` / ``group_key`` grouping fields).
        """
        # Import here to avoid pulling Pydantic at module load for callbacks
        # that never process typed events.
        from graph_agent.callbacks.events import (
            AmbiguityLoggedEvent,
            AmbiguityReportEvent,
            ArtifactSavedEvent,
            BuiltinSubagentEnterEvent,
            BuiltinSubagentExitEvent,
            BuiltinSubagentFallbackEvent,
            CompactionEvent,
            DeadEndPrunedEvent,
            FinishTaskEvent,
            HeartbeatEvent,
            InternalErrorEvent,
            LLMCallEvent,
            LLMFallbackEvent,
            ModelResolvedEvent,
            NudgeEvent,
            ParallelMapGroupEndedEvent,
            ParallelMapGroupStartedEvent,
            PhaseEndEvent,
            PhaseStartEvent,
            PromptCapturedEvent,
            RetryEvent,
            RetryExhaustedEvent,
            RunEndedEvent,
            RunStartedEvent,
            ToolCallEvent,
            ValidationFailEvent,
            ValidationPassEvent,
            WorkingMemoryUpdateEvent,
        )

        if isinstance(event, PhaseStartEvent):
            self.on_phase_start(event.phase_name, event.context)
        elif isinstance(event, PhaseEndEvent):
            self.on_phase_end(event.phase_name, event.context, event.metrics)
        elif isinstance(event, LLMCallEvent):
            self.on_llm_call(
                event.phase_name,
                event.input_tokens,
                event.output_tokens,
                messages=event.messages,
                response_data=event.response_data,
            )
        elif isinstance(event, ToolCallEvent):
            self.on_tool_call(
                event.phase_name,
                event.tool_name,
                event.args,
                event.result,
                duration_ms=event.duration_ms,
            )
        elif isinstance(event, ValidationFailEvent):
            self.on_validation_fail(event.phase_name, event.errors, event.retry_count)
        elif isinstance(event, RetryEvent):
            self.on_retry(event.phase_name, event.target_phase, event.feedback)
        elif isinstance(event, FinishTaskEvent):
            self.on_finish_task(event.phase_name, event.reasoning, event.evidence)
        elif isinstance(event, NudgeEvent):
            self.on_nudge(event.phase_name, event.nudge_count, nudge_type=event.nudge_type)
        elif isinstance(event, WorkingMemoryUpdateEvent):
            self.on_working_memory_update(event.phase_name, event.content_length)
        elif isinstance(event, DeadEndPrunedEvent):
            self.on_dead_end_pruned(event.phase_name, event.summary)
        elif isinstance(event, CompactionEvent):
            self.on_compaction(event.phase_name, event.removed_pairs)
        elif isinstance(event, AmbiguityReportEvent):
            self.on_ambiguity_report(
                event.phase_name, event.ambiguity_type, event.question, event.decision
            )
        elif isinstance(
            event,
            (
                # Existing typed-only events (Task 3.4)
                PromptCapturedEvent,
                LLMFallbackEvent,
                # PR E — tracing-only business / assembly events
                AmbiguityLoggedEvent,
                BuiltinSubagentEnterEvent,
                BuiltinSubagentExitEvent,
                BuiltinSubagentFallbackEvent,
                # Tier 1 Commit A — core lifecycle
                RunStartedEvent,
                RunEndedEvent,
                ValidationPassEvent,
                RetryExhaustedEvent,
                InternalErrorEvent,
                # Tier 1 Commit B — data + proxy enhancement
                ModelResolvedEvent,
                ArtifactSavedEvent,
                # Tier 1 Commit C — concurrency boundary (subgraph events
                # removed in MVP-0 B1)
                ParallelMapGroupStartedEvent,
                ParallelMapGroupEndedEvent,
                # Tier 1 Commit D — heartbeat
                HeartbeatEvent,
            ),
        ):
            # No legacy hook exists for these new event types. Subclasses that
            # need to consume them must override `on_event` directly. The
            # default TracingCallback.on_event implementation already writes
            # these events to tracing.jsonl, so the warning path below should
            # never fire for framework-emitted events.
            logger.debug(
                "Callback.on_event default dispatch: no legacy hook for %s; "
                "override on_event in subclass to consume it.",
                type(event).__name__,
            )
        else:
            logger.warning(
                "Callback.on_event received unrecognised event type %s",
                type(event).__name__,
            )


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
