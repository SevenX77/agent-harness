"""PR2 node-level Compare LLMs — candidate persistence (per skill + node).

Candidates are model-only (model group + endpoint route). They live in the
skill's ``.workspace/runtime_config.json`` keyed by node id — NOT in
SKILL.md (compare is a run-time experiment config, not skill source). These
tests pin the store round-trip and the GET/PUT API before the run wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.models.model_compare import CompareCandidate
from app.services.compare_candidates import (
    read_compare_candidates,
    write_node_compare_candidates,
)
from app.services.skills import resolve_skill_dir
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Unit: store round-trip
# ---------------------------------------------------------------------------


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
