"""Shared callback event emission helpers."""

from __future__ import annotations

import contextvars
import json
import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from threading import RLock
from typing import Any

from graph_agent.callbacks.events import LLMCallSettingsEvent, LLMRouteDecisionEvent
from graph_agent.io.run_layout import TRACE_FILENAME

logger = logging.getLogger(__name__)


class _TraceJsonlSink:
    """Where one run's events are written down, for as long as the run lasts.

    The file is created on open — its presence is what says a sink was opened
    for this run — but never cleared. It used to be truncated here, which is
    the behaviour of something that believes it is starting a run; a run
    stopped at a breakpoint and continued opens a second sink over the SAME
    directory, and the first segment's record was wiped every time. Nothing
    else can be in that file to clear: it lives in ``runs/<run_id>/``, so
    whatever is already there was written by this same run.
    """

    def __init__(self, trace_dir: str | Path) -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / TRACE_FILENAME
        self.path.touch(exist_ok=True)
        self._lock = RLock()

    def emit(self, event: Any) -> None:
        # A frame that is allowed to be merged or dropped must not end up in a
        # file people read as the record of what happened: whatever survived
        # would describe a run nobody had. The frame answers this itself, so
        # this sink never keeps a list of kinds that could fall out of date.
        if not getattr(event, "persisted", True):
            return
        payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else event
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


class _RunSpendLedger:
    """What this run spent, counted as each call reports itself (OB10).

    A call is known to have happened at the moment it happens. Reconstructing
    the total afterwards — by re-reading whichever messages or graph state
    survived — can only ever describe what remained, which is why the previous
    accounting missed every parallel branch but one, and every call that never
    appends to a message list at all (``finish_task``'s md-patch repair invokes
    the model directly).

    Counting here instead makes the run total equal to the sum over the run's
    own ``llm_call`` events by construction: ``report.md`` re-aggregates those
    events and ``metrics.json`` quotes this ledger, so the two cannot disagree.

    Batch items run on their own threads and only ever add, but ``+=`` on an
    int attribute is a read and a write, so the lock is what keeps two items
    finishing at once from losing one of them.
    """

    def __init__(self) -> None:
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._lock = RLock()

    @classmethod
    def continuing(cls, trace_path: Path) -> _RunSpendLedger:
        """A ledger opened with what this run has already spent.

        A run that stopped at a breakpoint and was continued is ONE run, so its
        total is the sum over all of its ``llm_call`` events — not over the ones
        the latest segment happened to make. Its own trace is where those are
        written down, and re-reading them is the same aggregation ``report.md``
        performs, which is what keeps the two agreeing across a resume as well
        as within one segment.

        This is not the reconstruction the class docstring rejects. That one
        re-derives spend from whichever messages or graph state SURVIVED, and
        is lossy by nature; these are the run's own call records, written as
        each call happened, and nothing ever removes a line from them.

        Missing file = a run that has spent nothing yet, which is the honest
        reading: the sink creates the trace when the run opens it.
        """
        ledger = cls()
        if not trace_path.exists():
            return ledger
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("event_type") != "llm_call":
                continue
            ledger.total_input_tokens += int(event.get("input_tokens") or 0)
            ledger.total_output_tokens += int(event.get("output_tokens") or 0)
        return ledger

    def emit(self, event: Any) -> None:
        if getattr(event, "event_type", None) != "llm_call":
            return
        with self._lock:
            self.total_input_tokens += int(getattr(event, "input_tokens", 0) or 0)
            self.total_output_tokens += int(getattr(event, "output_tokens", 0) or 0)

    def totals(self) -> dict[str, int]:
        with self._lock:
            return {
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
            }


class _SubscriberSink:
    def __init__(self, subscriber: Callable[[Any], None]) -> None:
        self._subscriber = subscriber

    def emit(self, event: Any) -> None:
        self._subscriber(event)


class _CallbackSink:
    def __init__(self, callbacks: Iterable[Any]) -> None:
        self._callbacks = tuple(callbacks)

    def emit(self, event: Any) -> None:
        for callback in self._callbacks:
            on_event = getattr(callback, "on_event", None)
            if callable(on_event):
                on_event(event)


class _CompositeEventSink:
    def __init__(self, sinks: Iterable[Any]) -> None:
        self._sinks = tuple(sinks)
        self.trace_path = next(
            (sink.path for sink in self._sinks if isinstance(sink, _TraceJsonlSink)),
            None,
        )

    def emit(self, event: Any) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[Callbacks] event sink %r raised on %s; continuing",
                    type(sink).__name__,
                    type(event).__name__,
                )


#: Chain of SUBGRAPH phase ids enclosing the code that is emitting right now.
#: ``_build_subgraph_node`` pushes its phase id around the child graph invoke;
#: asyncio tasks inherit a copy, so batch items inside a subgraph stay scoped.
#: Lives here rather than in the assembler because this module is the one
#: place every emitter already routes through, and the assembler imports it.
active_subgraph_path: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "active_subgraph_path", default=()
)

#: The phase execution the code emitting right now is running inside.
#: ``wrap_edge_transition`` sets it around the whole phase body, because the
#: transition already had to mint that id to name its destination — one mint,
#: one id. Lives here beside ``active_subgraph_path`` so both ambient scopes
#: are read in one place, and because ``core.edge_transition`` already imports
#: this module (the reverse would be a cycle).
active_phase_execution: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_phase_execution", default=None
)


def _stamp_subgraph_path(event: Any) -> None:
    """Fill ``subgraph_path`` from ambient scope on events that carry the field.

    Only a still-unset (``None``) field is stamped: ``parallel_map`` propagates
    child events that were already stamped inside the child context.
    """
    if getattr(event, "subgraph_path", "") is not None:
        return
    path = active_subgraph_path.get()
    if not path:
        return
    try:
        event.subgraph_path = ".".join(path)
    except (AttributeError, TypeError, ValueError):  # frozen or exotic event objects
        pass


def _stamp_phase_execution(event: Any) -> None:
    """Fill ``phase_execution_id`` from ambient scope on events that carry it.

    Only a still-unset field is stamped: the two phase lifecycle events name
    their own execution, and ``parallel_map`` propagates child events already
    stamped inside the child context.
    """
    if getattr(event, "phase_execution_id", "") is not None:
        return
    execution_id = active_phase_execution.get()
    if not execution_id:
        return
    try:
        event.phase_execution_id = execution_id
    except (AttributeError, TypeError, ValueError):  # frozen or exotic event objects
        pass


def _safe_emit_event(callbacks: Any | None, event: Any) -> None:
    """Dispatch a typed callback event without letting callback failures abort a run."""
    if callbacks is None:
        return
    _stamp_subgraph_path(event)
    _stamp_phase_execution(event)
    emit = getattr(callbacks, "emit", None)
    if callable(emit):
        try:
            emit(event)
        except Exception:  # noqa: BLE001
            logger.exception(
                "[Callbacks] event sink %r raised on %s; continuing",
                type(callbacks).__name__,
                type(event).__name__,
            )
        return
    if callable(callbacks) and not isinstance(callbacks, (list, tuple)):
        try:
            callbacks(event)
        except Exception:  # noqa: BLE001
            logger.exception(
                "[Callbacks] subscriber %r raised on %s; continuing",
                type(callbacks).__name__,
                type(event).__name__,
            )
        return
    for callback in callbacks or []:
        try:
            callback.on_event(event)
        except Exception:  # noqa: BLE001
            logger.exception(
                "[Callbacks] callback %r raised on %s; continuing with other callbacks",
                type(callback).__name__,
                type(event).__name__,
            )


class _GatewayEventSink:
    """Restates the gateway's events as the engine's own, then emits them here.

    The gateway cannot depend on this package, so it builds its own frozen
    dataclasses and the engine hands its callback list straight through — which
    means those events are the only ones in a run that never pass
    ``_safe_emit_event``, and so the only ones that never learn which subgraph
    they happened in. Two subgraphs may each own a phase called ``review``, and
    an event that cannot say which one it belongs to makes the two
    indistinguishable to every reader downstream.

    Restating rather than stamping, because the gateway's event is frozen and
    has no ``subgraph_path`` field at all: there is nothing there to fill in.
    The engine already declares its own copy of each of these shapes in
    ``events`` (they are in the ``CallbackEvent`` union), which until now
    nothing constructed — this is what makes that declaration true.

    An event the engine has no class for is passed along untouched. It arrives
    without a scope, which is worse than the events around it and better than
    vanishing until someone notices a new gateway event type is missing from
    every trace.
    """

    def __init__(self, callbacks: Iterable[Any]) -> None:
        self._callbacks = tuple(callbacks)

    def on_event(self, event: Any) -> None:
        _safe_emit_event(self._callbacks, _as_engine_event(event))


def _as_engine_event(event: Any) -> Any:
    engine_class = _ENGINE_CLASS_BY_GATEWAY_EVENT_TYPE.get(getattr(event, "event_type", ""))
    if engine_class is None:
        return event
    dump = getattr(event, "model_dump", None)
    if not callable(dump):
        return event
    try:
        return engine_class(**dump())
    except (TypeError, ValueError):
        # The two sides of this contract are kept in step by hand, so a field
        # can drift. Delivering the gateway's own object keeps the run readable
        # while the mismatch gets fixed; dropping it would hide the drift.
        logger.exception(
            "[Callbacks] gateway %s does not fit %s; forwarding it unrestated",
            getattr(event, "event_type", type(event).__name__),
            engine_class.__name__,
        )
        return event


#: Gateway event types the engine states a contract for, and the class it
#: states it as. A gateway event type absent here is one the engine has no
#: opinion about, which is a different thing from one it rejects.
_ENGINE_CLASS_BY_GATEWAY_EVENT_TYPE: dict[str, Any] = {
    "llm_route_decision": LLMRouteDecisionEvent,
    "llm_call_settings": LLMCallSettingsEvent,
}


__all__ = [
    "_CallbackSink",
    "_CompositeEventSink",
    "_GatewayEventSink",
    "_RunSpendLedger",
    "_SubscriberSink",
    "_TraceJsonlSink",
    "_safe_emit_event",
    "active_subgraph_path",
    "active_phase_execution",
]
