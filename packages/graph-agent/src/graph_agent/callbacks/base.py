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
        response_data: dict[str, Any],
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
        removed_message_count: int,
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
        ``prompt_captured`` / ``llm_route_decision`` events and the
        ``sub_run_id`` / ``group_key`` grouping fields).
        """
        if _dispatch_legacy_event(self, event):
            return
        if isinstance(event, _typed_only_event_types()):
            _log_typed_only_event(event)
            return
        logger.warning(
            "Callback.on_event received unrecognised event type %s",
            type(event).__name__,
        )


def _dispatch_legacy_event(callback: Callback, event: Any) -> bool:
    for event_type, dispatcher in _legacy_event_dispatchers():
        if isinstance(event, event_type):
            dispatcher(callback, event)
            return True
    return False


def _legacy_event_dispatchers() -> tuple[tuple[type[Any], Any], ...]:
    from graph_agent.callbacks.events import (
        AmbiguityReportEvent,
        CompactionEvent,
        DeadEndPrunedEvent,
        FinishTaskEvent,
        LLMCallEvent,
        NudgeEvent,
        PhaseEndEvent,
        PhaseStartEvent,
        RetryEvent,
        ToolCallEvent,
        ValidationFailEvent,
        WorkingMemoryUpdateEvent,
    )

    return (
        (PhaseStartEvent, _dispatch_phase_start),
        (PhaseEndEvent, _dispatch_phase_end),
        (LLMCallEvent, _dispatch_llm_call),
        (ToolCallEvent, _dispatch_tool_call),
        (ValidationFailEvent, _dispatch_validation_fail),
        (RetryEvent, _dispatch_retry),
        (FinishTaskEvent, _dispatch_finish_task),
        (NudgeEvent, _dispatch_nudge),
        (WorkingMemoryUpdateEvent, _dispatch_working_memory_update),
        (DeadEndPrunedEvent, _dispatch_dead_end_pruned),
        (CompactionEvent, _dispatch_compaction),
        (AmbiguityReportEvent, _dispatch_ambiguity_report),
    )


def _typed_only_event_types() -> tuple[type[Any], ...]:
    from graph_agent.callbacks.events import (
        AmbiguityLoggedEvent,
        ArtifactSavedEvent,
        BlackboardReduceEvent,
        BuiltinSubagentEnterEvent,
        BuiltinSubagentExitEvent,
        BuiltinSubagentFallbackEvent,
        HeartbeatEvent,
        InputDispatchEvent,
        InputFileInjectedEvent,
        InternalErrorEvent,
        LLMCallSettingsEvent,
        LLMRouteDecisionEvent,
        ModelResolvedEvent,
        ParallelMapGroupEndedEvent,
        ParallelMapGroupStartedEvent,
        PromptCapturedEvent,
        RetryExhaustedEvent,
        RunEndedEvent,
        RunStartedEvent,
        ToolCallStartedEvent,
        ValidationPassEvent,
    )

    return (
        PromptCapturedEvent,
        ToolCallStartedEvent,
        LLMRouteDecisionEvent,
        LLMCallSettingsEvent,
        AmbiguityLoggedEvent,
        BuiltinSubagentEnterEvent,
        BuiltinSubagentExitEvent,
        BuiltinSubagentFallbackEvent,
        RunStartedEvent,
        RunEndedEvent,
        ValidationPassEvent,
        RetryExhaustedEvent,
        InternalErrorEvent,
        ModelResolvedEvent,
        ArtifactSavedEvent,
        ParallelMapGroupStartedEvent,
        ParallelMapGroupEndedEvent,
        HeartbeatEvent,
        BlackboardReduceEvent,
        InputDispatchEvent,
        InputFileInjectedEvent,
    )


def _log_typed_only_event(event: Any) -> None:
    logger.debug(
        "Callback.on_event default dispatch: no legacy hook for %s; "
        "override on_event in subclass to consume it.",
        type(event).__name__,
    )


def _dispatch_phase_start(callback: Callback, event: Any) -> None:
    callback.on_phase_start(event.phase_name, event.context)


def _dispatch_phase_end(callback: Callback, event: Any) -> None:
    callback.on_phase_end(event.phase_name, event.context, event.metrics)


def _dispatch_llm_call(callback: Callback, event: Any) -> None:
    callback.on_llm_call(
        event.phase_name,
        event.input_tokens,
        event.output_tokens,
        response_data=event.response_data,
    )


def _dispatch_tool_call(callback: Callback, event: Any) -> None:
    callback.on_tool_call(
        event.phase_name,
        event.tool_name,
        event.args,
        event.result,
        duration_ms=event.duration_ms,
    )


def _dispatch_validation_fail(callback: Callback, event: Any) -> None:
    callback.on_validation_fail(event.phase_name, event.errors, event.retry_count)


def _dispatch_retry(callback: Callback, event: Any) -> None:
    callback.on_retry(event.phase_name, event.target_phase, event.feedback)


def _dispatch_finish_task(callback: Callback, event: Any) -> None:
    callback.on_finish_task(event.phase_name, event.reasoning, event.evidence)


def _dispatch_nudge(callback: Callback, event: Any) -> None:
    callback.on_nudge(event.phase_name, event.nudge_count, nudge_type=event.nudge_type)


def _dispatch_working_memory_update(callback: Callback, event: Any) -> None:
    callback.on_working_memory_update(event.phase_name, event.content_length)


def _dispatch_dead_end_pruned(callback: Callback, event: Any) -> None:
    callback.on_dead_end_pruned(event.phase_name, event.summary)


def _dispatch_compaction(callback: Callback, event: Any) -> None:
    callback.on_compaction(event.phase_name, event.removed_message_count)


def _dispatch_ambiguity_report(callback: Callback, event: Any) -> None:
    callback.on_ambiguity_report(
        event.phase_name, event.ambiguity_type, event.question, event.decision
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
