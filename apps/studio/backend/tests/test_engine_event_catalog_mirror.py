"""The frontend's known-event set must name every engine event, and only those.

`apps/studio/frontend/src/utils/engine-events.ts` holds a hand-written copy of
the engine's `event_type` catalog. A copy with nothing enforcing it drifts the
moment someone adds an event: the new type silently becomes "unknown", and an
unknown type falls back to a name-shaped guess ("does it contain 'error'?") —
which is the very failure the set was introduced to stop (`tool_error_handled`
names an error the engine recovered from, and reading it as a failure paints a
node red on a run that never failed).

The test lives in the Studio backend because this is the only module that can
see BOTH sides first-hand: it imports `graph_agent` (so the catalog comes from
the discriminated union itself, not from a regex over Python source) and it
sits in the same repo as the frontend file. The engine must not learn about a
Studio frontend file, and the frontend has no Python to introspect with — so
neither of them can host this check without becoming a worse version of it.

Direction matters: the engine union is the truth, the TypeScript set is the
mirror. A failure here is fixed by editing the mirror, never by editing the
engine to match it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, get_args

from graph_agent.callbacks.events import CallbackEvent

REPO_ROOT = Path(__file__).resolve().parents[4]
MIRROR_PATH = REPO_ROOT / "apps" / "studio" / "frontend" / "src" / "utils" / "engine-events.ts"

_SET_LITERAL = re.compile(r"ENGINE_EVENT_TYPES[^=]*=\s*new Set\(\[(?P<body>[^\]]*)\]\)", re.DOTALL)
_ENTRY = re.compile(r"'([a-z_0-9]+)'")


def _engine_event_types() -> set[str]:
    """Every `event_type` the engine's `CallbackEvent` union can carry.

    `CallbackEvent` is `Annotated[A | B | ..., Field(discriminator=...)]`, so the
    first arg is the union and each member's `event_type` field default is its
    discriminator value.
    """
    union = get_args(CallbackEvent)[0]
    members: tuple[Any, ...] = get_args(union)
    assert members, "CallbackEvent should be a union of event models"

    types: set[str] = set()
    for member in members:
        default = member.model_fields["event_type"].default
        assert isinstance(default, str) and default, f"{member.__name__} must default its event_type"
        types.add(default)
    return types


def _mirrored_event_types() -> set[str]:
    assert MIRROR_PATH.is_file(), f"frontend event mirror is missing: {MIRROR_PATH}"

    match = _SET_LITERAL.search(MIRROR_PATH.read_text(encoding="utf-8"))
    assert match is not None, (
        f"could not find the ENGINE_EVENT_TYPES set literal in {MIRROR_PATH.name} -- "
        "if it was renamed or restructured, update this test with it"
    )
    entries = _ENTRY.findall(match.group("body"))
    assert entries, f"ENGINE_EVENT_TYPES in {MIRROR_PATH.name} parsed as empty"
    return set(entries)


def test_frontend_event_mirror_names_every_engine_event() -> None:
    engine_types = _engine_event_types()
    mirrored = _mirrored_event_types()

    missing = sorted(engine_types - mirrored)
    ghosts = sorted(mirrored - engine_types)

    assert not missing, (
        f"the engine emits event types the frontend has never heard of: {missing} -- "
        f"add them to {MIRROR_PATH.name} (the engine union is the truth; the set mirrors it)"
    )
    assert not ghosts, (
        f"the frontend claims event types the engine no longer emits: {ghosts} -- "
        f"delete them from {MIRROR_PATH.name}"
    )


def test_engine_event_types_are_unique() -> None:
    """A discriminated union with two members sharing a tag cannot be decoded."""
    union = get_args(CallbackEvent)[0]
    members: tuple[Any, ...] = get_args(union)
    defaults = [member.model_fields["event_type"].default for member in members]

    duplicates = sorted({value for value in defaults if defaults.count(value) > 1})
    assert not duplicates, f"event_type must identify one model: {duplicates}"
