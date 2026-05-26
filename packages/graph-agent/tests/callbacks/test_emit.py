from __future__ import annotations

from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import PhaseStartEvent


class _RaisingCallback:
    def on_event(self, event: object) -> None:
        del event
        raise RuntimeError("callback failed")


class _CollectingCallback:
    def __init__(self) -> None:
        self.events: list[object] = []

    def on_event(self, event: object) -> None:
        self.events.append(event)


def test_safe_emit_event_continues_after_callback_failure() -> None:
    collector = _CollectingCallback()
    event = PhaseStartEvent(phase_name="main", context={"topic": "T"})

    _safe_emit_event([_RaisingCallback(), collector], event)

    assert collector.events == [event]
