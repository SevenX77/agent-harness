"""Shared callback event emission helpers."""

from __future__ import annotations

import contextvars
import json
import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from threading import RLock
from typing import Any

from graph_agent.io.run_layout import TRACE_FILENAME

logger = logging.getLogger(__name__)


class _TraceJsonlSink:
    def __init__(self, trace_dir: str | Path) -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / TRACE_FILENAME
        self.path.write_text("", encoding="utf-8")
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


def _safe_emit_event(callbacks: Any | None, event: Any) -> None:
    """Dispatch a typed callback event without letting callback failures abort a run."""
    if callbacks is None:
        return
    _stamp_subgraph_path(event)
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


__all__ = [
    "_CallbackSink",
    "_CompositeEventSink",
    "_SubscriberSink",
    "_TraceJsonlSink",
    "_safe_emit_event",
    "active_subgraph_path",
]
