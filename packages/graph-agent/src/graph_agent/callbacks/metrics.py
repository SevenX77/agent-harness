"""Built-in callback that accumulates token usage and timing."""

from __future__ import annotations

import logging
import time
from typing import Any

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


class MetricsCallback(Callback):
    """Built-in callback that accumulates token usage and timing."""

    def __init__(self) -> None:
        """Initialize metric counters for one run."""
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_tool_calls: int = 0
        self.total_nudges: int = 0
        self.total_working_memory_updates: int = 0
        self.total_dead_end_prunes: int = 0
        self.total_compactions: int = 0
        self.phase_durations: dict[str, list[float]] = {}
        self._phase_start_times: dict[str, float] = {}

    def on_event(self, event: CallbackEvent) -> None:
        """Accumulate the counters this callback owns; ignore other event kinds."""
        if isinstance(event, PhaseStartEvent):
            self._phase_start_times[event.phase_name] = time.monotonic()
        elif isinstance(event, PhaseEndEvent):
            start = self._phase_start_times.pop(event.phase_name, None)
            if start is not None:
                self.phase_durations.setdefault(event.phase_name, []).append(
                    time.monotonic() - start
                )
        elif isinstance(event, LLMCallEvent):
            self.total_input_tokens += event.input_tokens
            self.total_output_tokens += event.output_tokens
        elif isinstance(event, ToolCallEvent):
            self.total_tool_calls += 1
        elif isinstance(event, NudgeEvent):
            self.total_nudges += 1
        elif isinstance(event, WorkingMemoryUpdateEvent):
            self.total_working_memory_updates += 1
        elif isinstance(event, DeadEndPrunedEvent):
            self.total_dead_end_prunes += 1
        elif isinstance(event, CompactionEvent):
            self.total_compactions += 1

    def summary(self) -> dict[str, Any]:
        """Return accumulated metrics as a dictionary."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tool_calls": self.total_tool_calls,
            "total_nudges": self.total_nudges,
            "total_working_memory_updates": self.total_working_memory_updates,
            "total_dead_end_prunes": self.total_dead_end_prunes,
            "total_compactions": self.total_compactions,
            "phase_durations": {k: list(v) for k, v in self.phase_durations.items()},
        }
