"""Who owns a step, and therefore how a step is reported.

A step is one unit of work a run performs and reports on: it starts, it runs,
it ends. Before this module existed the concept had no home, so each place that
happened to notice a step re-decided its properties — the middleware minted an
identity and timed the call, the agent node built the closing event again with
an identity of its own.

The reporter owns those decisions. A caller says what is happening; it does not
say how that becomes events, which callbacks hear about it, or how long the
step took.

Deliberately not owned here: writing to disk, and the shape of the transport.
The reporter hands events to the run's callbacks through the one dispatch the
package already has, and what the callbacks do with them is theirs.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import ToolCallEvent, ToolCallStartedEvent


class ToolCallStep:
    """A tool call that has been announced and is now running.

    ``finished`` is the caller's to invoke because only the caller knows what
    the tool answered — and whether it answered at all. A step nobody finishes
    reported that it started, which is true and is the most that can be said.
    """

    def __init__(
        self,
        reporter: StepReporter,
        *,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
        parent_node_id: str | None,
        node_type: str | None,
        started_at: float,
    ) -> None:
        self._reporter = reporter
        self._tool_call_id = tool_call_id
        self._tool_name = tool_name
        self._args = args
        self._parent_node_id = parent_node_id
        self._node_type = node_type
        self._started_at = started_at

    def finished(self, result: str) -> None:
        self._reporter._emit(
            ToolCallEvent(
                tool_call_id=self._tool_call_id,
                phase_name=self._reporter.phase_name,
                tool_name=self._tool_name,
                args=self._args,
                result=result,
                duration_ms=(time.perf_counter() - self._started_at) * 1000.0,
                parent_node_id=self._parent_node_id,
                node_type=self._node_type,
            )
        )


class StepReporter:
    """The one exit a phase's steps are reported through.

    Bound to a phase and its callbacks once, so no call site threads either of
    them into an event again.
    """

    def __init__(self, *, callbacks: Any, phase_name: str) -> None:
        # Kept exactly as handed over: a run's callbacks arrive as a sequence, a
        # single sink object or a plain subscriber, and the package's dispatch
        # already knows all three. Normalising here would be a second opinion
        # about what a callback is.
        self._callbacks = callbacks
        self.phase_name = phase_name

    @contextmanager
    def tool_call(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
        parent_node_id: str | None = None,
        node_type: str | None = "tool",
    ) -> Iterator[ToolCallStep]:
        """Announce a tool call, then hand back the step that is now running."""
        resolved_args = dict(args or {})
        self._emit(
            ToolCallStartedEvent(
                tool_call_id=tool_call_id,
                phase_name=self.phase_name,
                tool_name=tool_name,
                args=resolved_args,
                parent_node_id=parent_node_id,
                node_type=node_type,
            )
        )
        yield ToolCallStep(
            self,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            args=resolved_args,
            parent_node_id=parent_node_id,
            node_type=node_type,
            started_at=time.perf_counter(),
        )

    def completed_tool_call(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
        result: str,
        parent_node_id: str | None = None,
        node_type: str | None = None,
    ) -> None:
        """Report a call that was only noticed once it was already over.

        No duration and no start event: both would have to be invented, and an
        invented moment is worse than an absent one.
        """
        self._emit(
            ToolCallEvent(
                tool_call_id=tool_call_id,
                phase_name=self.phase_name,
                tool_name=tool_name,
                args=dict(args or {}),
                result=result,
                duration_ms=None,
                parent_node_id=parent_node_id,
                node_type=node_type,
            )
        )

    def _emit(self, event: ToolCallStartedEvent | ToolCallEvent) -> None:
        _safe_emit_event(self._callbacks, event)


__all__ = ["StepReporter", "ToolCallStep"]
