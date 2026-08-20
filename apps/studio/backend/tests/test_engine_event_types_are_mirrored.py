"""The trace's list of engine event types must be the engine's own list.

The Studio trace proves it has a reading for every event the engine can emit
(`utils/trace.test.ts`: "has a reading for every event the engine can emit"),
and that proof is only worth anything if the list it iterates is the real one.
A hand-copied list drifts the moment someone adds an event class — and the
failure mode is silent, because an unread event still "renders": as
`JSON.stringify` of itself, which is the black box the D4 glass-box decision
exists to remove. The same list also answers "is this an event this build
KNOWS?", which is what keeps a name-shaped guess ("does the type contain
'error'?") a fallback for FUTURE events instead of a verdict that overrules what
a known event means — `tool_error_handled` names an error the engine recovered
from, and reading it as a failure paints a node red on a run that never failed.

So the copy is a gate, not a convention: add an event to the engine and this
test goes red until the trace can read it.

This test lives in the Studio backend because it is the only module that can see
BOTH sides first-hand: it imports `graph_agent` (so the catalog comes from the
discriminated union itself, not from a regex over Python source) and it sits in
the same repo as the frontend file. The engine must not learn about a Studio
frontend file, and the frontend has no Python to introspect — neither could host
this check without becoming a worse version of it.

Direction matters: the engine union is the truth, the TypeScript list is the
mirror. A failure here is fixed by editing the mirror, never by editing the
engine to match it.

Until 2026-08-20 this check existed TWICE, against two frontend files holding
the same list under the same exported name. The mirrors have been merged into
one; so has the gate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, get_args

from graph_agent.callbacks.events import CallbackEvent

MIRROR = (
    Path(__file__).resolve().parents[3]
    / "studio"
    / "frontend"
    / "src"
    / "utils"
    / "engine-event-types.ts"
)


def _union_members() -> tuple[Any, ...]:
    """The event models `CallbackEvent` can actually carry.

    `CallbackEvent` is `Annotated[A | B | ..., Field(discriminator=...)]`, so the
    first arg is the union. Reading the union rather than every class defined in
    the module is the difference between "what can arrive" and "what someone
    wrote down": a model that is not in the union cannot reach a reader, and
    demanding a reading for it would be demanding dead code.
    """
    members: tuple[Any, ...] = get_args(get_args(CallbackEvent)[0])
    assert members, "CallbackEvent should be a union of event models"
    return members


def _engine_event_types() -> set[str]:
    types: set[str] = set()
    for member in _union_members():
        default = member.model_fields["event_type"].default
        assert isinstance(default, str) and default, (
            f"{member.__name__} must default its event_type"
        )
        types.add(default)
    return types


def _mirrored_event_types() -> set[str]:
    assert MIRROR.is_file(), f"frontend event mirror is missing: {MIRROR}"
    source = MIRROR.read_text(encoding="utf-8")
    body = source.split("ENGINE_EVENT_TYPES = [", 1)[1].split("]", 1)[0]
    entries = set(re.findall(r"'([a-z_0-9]+)'", body))
    assert entries, f"ENGINE_EVENT_TYPES in {MIRROR.name} parsed as empty"
    return entries


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


def test_engine_event_types_are_unique() -> None:
    """A discriminated union with two members sharing a tag cannot be decoded."""
    defaults = [member.model_fields["event_type"].default for member in _union_members()]

    duplicates = sorted({value for value in defaults if defaults.count(value) > 1})
    assert not duplicates, f"event_type must identify one model: {duplicates}"
