"""The trace's list of engine event types must be the engine's own list.

The Studio trace proves it has a reading for every event the engine can emit
(`utils/trace.test.ts`: "has a reading for every event the engine can emit"),
and that proof is only worth anything if the list it iterates is the real one.
A hand-copied list drifts the moment someone adds an event class — and the
failure mode is silent, because an unread event still "renders": as
`JSON.stringify` of itself, which is the black box the D4 glass-box decision
exists to remove.

So the copy is a gate, not a convention: add an event to the engine and this
test goes red until the trace can read it.
"""

from __future__ import annotations

import re
from pathlib import Path

from graph_agent.callbacks import events as engine_events

MIRROR = (
    Path(__file__).resolve().parents[3]
    / "studio"
    / "frontend"
    / "src"
    / "utils"
    / "engine-event-types.ts"
)


def _engine_event_types() -> set[str]:
    """Every `event_type` literal declared by an engine callback event class."""
    found: set[str] = set()
    for name in dir(engine_events):
        candidate = getattr(engine_events, name)
        if not isinstance(candidate, type):
            continue
        field = getattr(candidate, "model_fields", {}).get("event_type")
        if field is None:
            continue
        if isinstance(field.default, str):
            found.add(field.default)
    return found


def _mirrored_event_types() -> set[str]:
    source = MIRROR.read_text(encoding="utf-8")
    body = source.split("ENGINE_EVENT_TYPES = [", 1)[1].split("]", 1)[0]
    return set(re.findall(r"'([a-z_]+)'", body))


def test_the_trace_mirrors_every_engine_event_type() -> None:
    engine = _engine_event_types()
    mirrored = _mirrored_event_types()

    missing = sorted(engine - mirrored)
    extra = sorted(mirrored - engine)

    assert not missing, (
        "the engine emits event types the Studio trace does not list, so they would "
        f"fall through to the raw-payload fallback unnoticed: {missing}. Give each a "
        "reading in `utils/trace.ts` (eventMessage / eventFacts) and add it to "
        "`utils/engine-event-types.ts`."
    )
    assert not extra, (
        f"the Studio trace lists event types the engine no longer emits: {extra}. "
        "Remove them — a reading for an event that cannot arrive is dead code."
    )
