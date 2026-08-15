"""Event callback mechanism for monitoring Agent execution.

Business layer can implement concrete callbacks to observe phase transitions,
LLM calls, tool executions, and cognitive-control events.

Subclasses may either override :meth:`Callback.on_event` to receive a typed
:class:`~graph_agent.callbacks.events.CallbackEvent` union member, or override
the individual ``on_*`` hook methods. The default ``on_event`` dispatches a
typed event back to the matching legacy ``on_*`` hook where one exists;
typed-only events are logged at debug level unless ``on_event`` is overridden.
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
EVENT_NUDGE = "nudge"
EVENT_WORKING_MEMORY_UPDATE = "working_memory_update"
EVENT_DEAD_END_PRUNED = "dead_end_pruned"
EVENT_COMPACTION = "compaction"


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

    def on_event(self, event: CallbackEvent) -> None:
        """Typed event sink — the primary entrypoint for typed emitters.

        The default implementation dispatches a :class:`CallbackEvent` member
        back to the matching legacy ``on_*`` hook so subclasses that only
        override the old hooks keep working. Override this method directly
        to receive the full typed payload (including the
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
        CompactionEvent,
        DeadEndPrunedEvent,
        LLMCallEvent,
        NudgeEvent,
        PhaseEndEvent,
        PhaseStartEvent,
        ToolCallEvent,
        WorkingMemoryUpdateEvent,
    )

    return (
        (PhaseStartEvent, _dispatch_phase_start),
        (PhaseEndEvent, _dispatch_phase_end),
        (LLMCallEvent, _dispatch_llm_call),
        (ToolCallEvent, _dispatch_tool_call),
        (NudgeEvent, _dispatch_nudge),
        (WorkingMemoryUpdateEvent, _dispatch_working_memory_update),
        (DeadEndPrunedEvent, _dispatch_dead_end_pruned),
        (CompactionEvent, _dispatch_compaction),
    )


def _typed_only_event_types() -> tuple[type[Any], ...]:
    from graph_agent.callbacks.events import (
        AmbiguityLoggedEvent,
        ArtifactSavedEvent,
        BlackboardReduceEvent,
        BuiltinSubagentEnterEvent,
        BuiltinSubagentExitEvent,
        BuiltinSubagentFallbackEvent,
        InputDispatchEvent,
        InputFileInjectedEvent,
        LLMCallSettingsEvent,
        LLMRouteDecisionEvent,
        ParallelMapGroupEndedEvent,
        ParallelMapGroupStartedEvent,
        PromptCapturedEvent,
        RunEndedEvent,
        RunStartedEvent,
        ToolCallStartedEvent,
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
        ArtifactSavedEvent,
        ParallelMapGroupStartedEvent,
        ParallelMapGroupEndedEvent,
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


def _dispatch_nudge(callback: Callback, event: Any) -> None:
    callback.on_nudge(event.phase_name, event.nudge_count, nudge_type=event.nudge_type)


def _dispatch_working_memory_update(callback: Callback, event: Any) -> None:
    callback.on_working_memory_update(event.phase_name, event.content_length)


def _dispatch_dead_end_pruned(callback: Callback, event: Any) -> None:
    callback.on_dead_end_pruned(event.phase_name, event.summary)


def _dispatch_compaction(callback: Callback, event: Any) -> None:
    callback.on_compaction(event.phase_name, event.removed_message_count)


__all__ = [
    "Callback",
    "EVENT_PHASE_START",
    "EVENT_PHASE_END",
    "EVENT_LLM_CALL",
    "EVENT_TOOL_CALL",
    "EVENT_NUDGE",
    "EVENT_WORKING_MEMORY_UPDATE",
    "EVENT_DEAD_END_PRUNED",
    "EVENT_COMPACTION",
]
