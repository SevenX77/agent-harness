"""Setting and clearing a breakpoint over HTTP.

The canvas is where a breakpoint is set, so the API is addressed the way the
canvas is: one node at a time, by the node id the canvas already uses.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.services.event_bus import STUDIO_EVENTS_TOPIC, event_bus
from fastapi.testclient import TestClient

SKILL = "text-segmentation"


class _DirectSubscriber:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def __enter__(self) -> _DirectSubscriber:
        event_bus._subscribers.setdefault(STUDIO_EVENTS_TOPIC, set()).add(self.queue)
        return self

    def __exit__(self, *_exc: object) -> None:
        subscribers = event_bus._subscribers.get(STUDIO_EVENTS_TOPIC)
        if subscribers is not None:
            subscribers.discard(self.queue)
            if not subscribers:
                event_bus._subscribers.pop(STUDIO_EVENTS_TOPIC, None)


def test_a_skill_starts_with_no_breakpoints(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    """Read through ``runtime-config``, which is where they live — there is no
    second endpoint for one of that document's fields."""
    del studio_roots
    got = client.get(f"/api/skills/{SKILL}/runtime-config")

    assert got.status_code == 200, got.text
    assert got.json()["breakpoints"] == []


def test_a_breakpoint_lands_in_the_runtime_config_the_canvas_reads(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    del studio_roots
    client.put(f"/api/skills/{SKILL}/nodes/setup/breakpoint")

    got = client.get(f"/api/skills/{SKILL}/runtime-config")

    assert got.json()["breakpoints"] == ["setup"]


def test_setting_one_returns_the_whole_list(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    """The list, not the one node: a breakpoint is only meaningful against the
    others, and returning the canonical set is what lets the caller stop keeping
    its own copy (SSOT 读取原则)."""
    del studio_roots
    client.put(f"/api/skills/{SKILL}/nodes/setup/breakpoint")
    put = client.put(f"/api/skills/{SKILL}/nodes/segment/breakpoint")

    assert put.status_code == 200, put.text
    assert put.json()["node_ids"] == ["segment", "setup"]


def test_clearing_one_leaves_the_others(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    del studio_roots
    client.put(f"/api/skills/{SKILL}/nodes/setup/breakpoint")
    client.put(f"/api/skills/{SKILL}/nodes/segment/breakpoint")

    cleared = client.delete(f"/api/skills/{SKILL}/nodes/setup/breakpoint")

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["node_ids"] == ["segment"]


def test_clearing_one_that_was_never_set_is_not_an_error(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    """Asking for a state that already holds is not a failure — and the canvas
    can send the same clear twice while a click is in flight."""
    del studio_roots
    cleared = client.delete(f"/api/skills/{SKILL}/nodes/setup/breakpoint")

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["node_ids"] == []


def test_a_node_id_that_could_walk_out_of_the_skill_is_refused(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    del studio_roots
    refused = client.put(f"/api/skills/{SKILL}/nodes/..%2F..%2Fetc/breakpoint")

    assert refused.status_code in {400, 404}


def test_a_change_announces_itself_and_names_the_dataset(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    """Surfaces revalidate on a named dataset, not on a generic resync."""
    del studio_roots
    with _DirectSubscriber() as subscriber:
        client.put(f"/api/skills/{SKILL}/nodes/setup/breakpoint")
        event = asyncio.run(asyncio.wait_for(subscriber.queue.get(), timeout=1.0))

    assert event["type"] == "runtime_config_changed"
    assert event["dataset"] == "breakpoints"
    assert event["node_id"] == "setup"


def test_setting_one_that_is_already_set_announces_nothing(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    del studio_roots
    client.put(f"/api/skills/{SKILL}/nodes/setup/breakpoint")

    with _DirectSubscriber() as subscriber:
        again = client.put(f"/api/skills/{SKILL}/nodes/setup/breakpoint")

        assert again.status_code == 200
        assert subscriber.queue.empty()
