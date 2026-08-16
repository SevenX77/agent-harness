"""Event callback mechanism for monitoring Agent execution.

Business layer implements a concrete callback to observe phase transitions,
LLM calls, tool executions, and cognitive-control events.

A consumer overrides :meth:`Callback.on_event` and dispatches on the member of
the :class:`~graph_agent.callbacks.events.CallbackEvent` union it receives.
That is the whole surface: one method, one typed argument. Emitters reach it
through :func:`~graph_agent.callbacks.emit._safe_emit_event`, which is the only
place that knows how to fan an event out to a sink, a subscriber callable, or a
list of callbacks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from graph_agent.callbacks.events import CallbackEvent


class Callback:
    """Base callback with a no-op default. Subclass and override ``on_event``."""

    def on_event(self, event: CallbackEvent) -> None:
        """Receive one typed event.

        The default is a no-op: a consumer that has not asked for events does
        not get told about them, and no event is silently translated into some
        other shape on its way here.
        """


__all__ = ["Callback"]
