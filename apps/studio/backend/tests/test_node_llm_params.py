"""PR3 node-level LLM param overrides — per skill+node persistence.

Overrides are the three role-level generation params (thinking /
max_output_tokens / temperature). They live in the skill's
``.workspace/runtime_config.json`` keyed by node id — NOT in SKILL.md (llm
params are gateway-domain config truth, not skill source). These tests pin the
store round-trip and the GET/PUT API before the run-time resolver wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.node_llm_params import NodeLlmParams
from app.services.node_llm_params import (
    read_node_llm_params,
    write_node_llm_params,
)
from app.services.skills import resolve_skill_dir
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Unit: store round-trip
# ---------------------------------------------------------------------------


def test_read_missing_returns_empty(tmp_path: Path) -> None:
    assert read_node_llm_params(tmp_path) == {}


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    params = NodeLlmParams(enabled=True, thinking=True, max_output_tokens=2048, temperature=0.3)
    write_node_llm_params(tmp_path, "score", params)
    stored = read_node_llm_params(tmp_path)
    assert list(stored.keys()) == ["score"]
    assert stored["score"] == params


def test_partial_override_persists_only_set_fields(tmp_path: Path) -> None:
    write_node_llm_params(tmp_path, "score", NodeLlmParams(enabled=True, temperature=0.7))
    stored = read_node_llm_params(tmp_path)
    assert stored["score"].enabled is True
    assert stored["score"].temperature == 0.7
    assert stored["score"].thinking is None
    assert stored["score"].max_output_tokens is None


def test_enabled_without_field_values_persists_custom_mode(tmp_path: Path) -> None:
    write_node_llm_params(tmp_path, "score", NodeLlmParams(enabled=True))
    stored = read_node_llm_params(tmp_path)
    assert stored["score"] == NodeLlmParams(enabled=True)


def test_disabled_without_field_values_clears_node(tmp_path: Path) -> None:
    write_node_llm_params(tmp_path, "score", NodeLlmParams(enabled=True, thinking=True))
    write_node_llm_params(tmp_path, "other", NodeLlmParams(enabled=True, temperature=0.1))
    # clearing one node must not touch the other
    write_node_llm_params(tmp_path, "score", NodeLlmParams())
    stored = read_node_llm_params(tmp_path)
    assert "score" not in stored
    assert stored["other"].temperature == 0.1


def test_disabled_with_field_values_preserves_node_draft(tmp_path: Path) -> None:
    params = NodeLlmParams(enabled=False, thinking=True, max_output_tokens=2048, temperature=0.7)
    write_node_llm_params(tmp_path, "score", params)

    stored = read_node_llm_params(tmp_path)

    assert stored["score"] == params


# ---------------------------------------------------------------------------
# API: GET map + PUT one node
# ---------------------------------------------------------------------------


def test_put_and_get_node_params_api(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    put = client.put(
        "/api/skills/text-segmentation/nodes/setup/node-llm-params",
        json={"enabled": True, "thinking": True, "max_output_tokens": 4096, "temperature": 0.2},
    )
    assert put.status_code == 200, put.text
    assert put.json()["enabled"] is True
    assert put.json()["thinking"] is True
    assert put.json()["max_output_tokens"] == 4096
    assert put.json()["temperature"] == 0.2

    got = client.get("/api/skills/text-segmentation/node-llm-params")
    assert got.status_code == 200
    nodes = got.json()["nodes"]
    assert set(nodes.keys()) == {"setup"}
    assert nodes["setup"]["max_output_tokens"] == 4096

    # persisted on disk under the skill workspace
    skill_dir = resolve_skill_dir("text-segmentation")
    assert not (skill_dir / ".workspace" / "node_llm_params.json").exists()
    runtime_config = json.loads((skill_dir / ".workspace" / "runtime_config.json").read_text(encoding="utf-8"))
    assert runtime_config["llm"]["node_params"]["nodes"]["setup"]["temperature"] == 0.2
    disk = read_node_llm_params(skill_dir)
    assert disk["setup"].temperature == 0.2


def test_put_all_null_clears_node_api(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    client.put(
        "/api/skills/text-segmentation/nodes/setup/node-llm-params",
        json={"enabled": True, "thinking": True},
    )
    cleared = client.put(
        "/api/skills/text-segmentation/nodes/setup/node-llm-params",
        json={},
    )
    assert cleared.status_code == 200
    assert cleared.json() == {
        "enabled": False,
        "thinking": None,
        "max_output_tokens": None,
        "temperature": None,
    }

    got = client.get("/api/skills/text-segmentation/node-llm-params")
    assert got.json()["nodes"] == {}


def test_put_disabled_with_values_preserves_node_params_api(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    put = client.put(
        "/api/skills/text-segmentation/nodes/setup/node-llm-params",
        json={"enabled": False, "thinking": True, "max_output_tokens": 4096, "temperature": 0.2},
    )
    assert put.status_code == 200, put.text
    assert put.json() == {
        "enabled": False,
        "thinking": True,
        "max_output_tokens": 4096,
        "temperature": 0.2,
    }

    got = client.get("/api/skills/text-segmentation/node-llm-params")
    assert got.status_code == 200
    nodes = got.json()["nodes"]
    assert nodes["setup"] == {
        "enabled": False,
        "thinking": True,
        "max_output_tokens": 4096,
        "temperature": 0.2,
    }


def test_put_rejects_bad_node_id(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    resp = client.put(
        "/api/skills/text-segmentation/nodes/..%2Fescape/node-llm-params",
        json={"thinking": True},
    )
    assert resp.status_code in (400, 404, 422)


def test_put_rejects_extra_field(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    resp = client.put(
        "/api/skills/text-segmentation/nodes/setup/node-llm-params",
        json={"enabled": True, "thinking": True, "cost_priority": "low_cost"},
    )
    assert resp.status_code == 422


def test_get_unknown_skill_404(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    resp = client.get("/api/skills/no-such-skill/node-llm-params")
    assert resp.status_code == 404
