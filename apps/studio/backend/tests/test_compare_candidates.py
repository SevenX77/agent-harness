"""PR2 node-level Compare LLMs — candidate persistence (per skill + node).

Candidates are model-only (model group + endpoint route). They live in the
skill's ``.workspace/runtime_config.json`` keyed by node id — NOT in
SKILL.md (compare is a run-time experiment config, not skill source). These
tests pin the store round-trip and the GET/PUT API before the run wiring.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from app.models.model_compare import CompareCandidate
from app.services.compare_candidates import (
    read_compare_candidates,
    write_node_compare_candidates,
)
from app.services.event_bus import STUDIO_EVENTS_TOPIC, event_bus
from app.services.skills import resolve_skill_dir
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Unit: store round-trip
# ---------------------------------------------------------------------------


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

    async def receive(self) -> dict[str, Any]:
        return await asyncio.wait_for(self.queue.get(), timeout=1.0)


def test_read_missing_returns_empty(tmp_path: Path) -> None:
    assert read_compare_candidates(tmp_path) == {}


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    cands = [
        CompareCandidate(candidate_id="c1", model_group_id="gpt-x", route="auto"),
        CompareCandidate(candidate_id="c2", model_group_id="claude-y", route="route-7"),
    ]
    write_node_compare_candidates(tmp_path, "score", cands)
    stored = read_compare_candidates(tmp_path)
    assert list(stored.keys()) == ["score"]
    assert stored["score"] == cands


def test_write_empty_list_clears_node(tmp_path: Path) -> None:
    write_node_compare_candidates(
        tmp_path, "score", [CompareCandidate(candidate_id="c1", model_group_id="g")]
    )
    write_node_compare_candidates(tmp_path, "other", [CompareCandidate(candidate_id="c2", model_group_id="h")])
    # clearing one node must not touch the other
    write_node_compare_candidates(tmp_path, "score", [])
    stored = read_compare_candidates(tmp_path)
    assert "score" not in stored
    assert [c.candidate_id for c in stored["other"]] == ["c2"]


def test_write_same_compare_candidates_is_side_effect_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [CompareCandidate(candidate_id="c1", model_group_id="gpt-x", route="auto")]
    write_node_compare_candidates(tmp_path, "score", candidates)

    def fail_update(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise AssertionError("unchanged compare candidates must not rewrite runtime_config")

    monkeypatch.setattr(
        "app.services.compare_candidates.update_compare_candidates_payload",
        fail_update,
    )

    result = write_node_compare_candidates(tmp_path, "score", candidates)
    assert result.value == candidates
    assert result.changed is False


# ---------------------------------------------------------------------------
# API: GET map + PUT one node
# ---------------------------------------------------------------------------


def test_put_and_get_candidates_api(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    put = client.put(
        "/api/skills/text-segmentation/nodes/setup/compare-candidates",
        json={
            "candidates": [
                {"candidate_id": "fast", "model_group_id": "deepseek-v4", "route": "auto"},
                {"candidate_id": "slow", "model_group_id": "claude-opus", "route": "anthropic-official"},
            ]
        },
    )
    assert put.status_code == 200, put.text
    assert [c["candidate_id"] for c in put.json()["candidates"]] == ["fast", "slow"]

    got = client.get("/api/skills/text-segmentation/compare-candidates")
    assert got.status_code == 200
    nodes = got.json()["nodes"]
    assert set(nodes.keys()) == {"setup"}
    assert nodes["setup"][0]["model_group_id"] == "deepseek-v4"
    assert nodes["setup"][1]["route"] == "anthropic-official"

    # persisted in runtime_config under the skill workspace
    skill_dir = resolve_skill_dir("text-segmentation")
    assert not (skill_dir / ".workspace" / "compare_candidates.json").exists()
    runtime_config = json.loads((skill_dir / ".workspace" / "runtime_config.json").read_text(encoding="utf-8"))
    assert runtime_config["llm"]["compare_candidates"]["nodes"]["setup"][0]["candidate_id"] == "fast"
    disk = read_compare_candidates(skill_dir)
    assert [c.candidate_id for c in disk["setup"]] == ["fast", "slow"]


def test_put_compare_candidates_publishes_precise_event_only_when_changed(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    payload = {
        "candidates": [
            {"candidate_id": "fast", "model_group_id": "deepseek-v4", "route": "auto"},
        ]
    }

    with _DirectSubscriber() as sub:
        put = client.put(
            "/api/skills/text-segmentation/nodes/setup/compare-candidates",
            json=payload,
        )
        event = asyncio.run(sub.receive())

    assert put.status_code == 200
    assert event["type"] == "runtime_config_changed"
    assert event["source"] == "http_api"
    assert event["skill_id"] == "text-segmentation"
    assert event["dataset"] == "compare_candidates"
    assert event["node_id"] == "setup"

    with _DirectSubscriber() as sub:
        repeat = client.put(
            "/api/skills/text-segmentation/nodes/setup/compare-candidates",
            json=payload,
        )
        assert sub.queue.empty()

    assert repeat.status_code == 200


def test_put_empty_clears_node_api(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    client.put(
        "/api/skills/text-segmentation/nodes/setup/compare-candidates",
        json={"candidates": [{"candidate_id": "x", "model_group_id": "g"}]},
    )
    cleared = client.put(
        "/api/skills/text-segmentation/nodes/setup/compare-candidates",
        json={"candidates": []},
    )
    assert cleared.status_code == 200
    assert cleared.json()["candidates"] == []

    got = client.get("/api/skills/text-segmentation/compare-candidates")
    assert got.json()["nodes"] == {}


def test_put_rejects_bad_node_id(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    resp = client.put(
        "/api/skills/text-segmentation/nodes/..%2Fescape/compare-candidates",
        json={"candidates": []},
    )
    assert resp.status_code in (400, 404, 422)


def test_get_unknown_skill_404(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    resp = client.get("/api/skills/no-such-skill/compare-candidates")
    assert resp.status_code == 404


@pytest.mark.parametrize("route", ["auto", "route-1"])
def test_candidate_route_defaults_to_auto(tmp_path: Path, route: str) -> None:
    c = CompareCandidate(candidate_id="c", model_group_id="g", route=route)
    assert c.route == route
    # route omitted -> defaults to "auto"
    d = CompareCandidate(candidate_id="c", model_group_id="g")
    assert d.route == "auto"
