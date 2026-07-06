"""PR2 node-level Compare LLMs — orchestration endpoint (isolated side-runs).

POST /runs/{base_run_id}/compare launches one single-node side-run per persisted
candidate of a node, feeding it the base run's exact input for that node. This
test drives the endpoint end-to-end with an inline fake worker, letting the real
variant materialization + compile run, and asserting each side-run is tagged and
handed the captured slice + a per-candidate roles file + the variant artifact.
"""

from __future__ import annotations

import json
import queue
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.services import model_compare
from app.services.run_manager import run_manager
from fastapi.testclient import TestClient
from graph_agent.core.event_contracts import make_event_envelope


class _InlineProcess:
    def __init__(self, *, target: Any, args: tuple[Any, ...]) -> None:
        self._target = target
        self._args = args
        self.exitcode: int | None = None
        self._alive = False

    def start(self) -> None:
        self._alive = True
        self._target(*self._args)
        self.exitcode = 0
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float | None = None) -> None:
        del timeout
        self._alive = False

    def terminate(self) -> None:
        self._alive = False


def _fake_side_worker(
    skill_id: str,
    run_dir_raw: str,
    inputs: dict[str, Any],
    process_queue: queue.Queue[dict[str, Any]],
    art_ref: dict[str, Any],
    roles_path_override: str | None = None,
    runtime_config: dict[str, Any] | None = None,
) -> None:
    """Records what the side-run worker was handed (input slice + roles + artifact)."""
    del skill_id
    run_dir = Path(run_dir_raw)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "handed.json").write_text(
        json.dumps(
            {
                "inputs": inputs,
                "roles_path_override": roles_path_override,
                "runtime_config": runtime_config,
                "artifact_id": art_ref.get("artifact_id"),
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "final_state.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    process_queue.put({"type": "status", "status": "success", "metrics": {}})


def _dispatch_events(run_id: str, to_phase: str, snapshot: dict[str, Any]) -> list[Any]:
    return [
        make_event_envelope(
            stream_id=f"run:{run_id}",
            seq=1,
            run_id=run_id,
            event_type="input_dispatch",
            payload={
                "event_type": "input_dispatch",
                "from_phase": None,
                "to_phase": to_phase,
                "changed_keys": list(snapshot),
                "blackboard_snapshot": snapshot,
                "dispatched_keys": list(snapshot),
                "branch_index": None,
            },
            cursor=f"run:{run_id}:1",
            timestamp=datetime.now(tz=UTC),
        )
    ]


def test_node_compare_spawns_isolated_side_runs(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # persist two model candidates for node "setup"
    put = client.put(
        "/api/skills/text-segmentation/nodes/setup/compare-candidates",
        json={
            "candidates": [
                {"candidate_id": "fast", "model_group_id": "deepseek-v4", "route": "auto"},
                {"candidate_id": "slow", "model_group_id": "claude-opus", "route": "auto"},
            ]
        },
    )
    assert put.status_code == 200, put.text

    base_run_id = "2026-07-02T00-00-00_basebase"
    captured = {"input_text": "hello world"}

    # Stub the base run's events (the node's real input) and the roles-file writer
    # (roles building is covered by the candidate-test path; it needs credentials).
    monkeypatch.setattr(
        run_manager, "_reap_finished_runs", lambda: None, raising=False
    )
    import app.services.run_manager as rm

    monkeypatch.setattr(rm, "_read_run_artifact_events", lambda run_dir: _dispatch_events(base_run_id, "setup", captured))

    def _fake_roles(skill_dir: Path, node_id: str, candidate: Any, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"llm_roles__{candidate.candidate_id}.yaml"
        path.write_text("roles: {}\n", encoding="utf-8")
        return path

    monkeypatch.setattr(model_compare, "write_candidate_roles_file", _fake_roles)
    monkeypatch.setattr(run_manager, "process_factory", _InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", _fake_side_worker)

    resp = client.post(
        f"/api/skills/text-segmentation/runs/{base_run_id}/compare",
        json={"node_id": "setup"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["compare_group_id"].startswith("cmp-")
    assert body["node_id"] == "setup"
    assert body["base_run_id"] == base_run_id
    group_id = body["compare_group_id"]
    assert {r["candidate_id"] for r in body["runs"]} == {"fast", "slow"}
    for r in body["runs"]:
        assert r["metadata"]["compare_group_id"] == group_id
        assert r["metadata"]["compare_node_id"] == "setup"
        assert r["metadata"]["candidate_id"] == r["candidate_id"]
        assert r["label"] in {"deepseek-v4", "claude-opus"}

    # each side-run worker got the captured slice + a per-candidate roles file + a
    # (variant) artifact — proving isolation from the base run + model swap wiring.
    skills_dir, _ = studio_roots
    for r in body["runs"]:
        run_id = r["metadata"]["run_id"]
        handed_path = next(
            (skills_dir / "text-segmentation" / ".workspace" / "runs").glob(f"{run_id}/handed.json")
        )
        handed = json.loads(handed_path.read_text(encoding="utf-8"))
        assert handed["inputs"] == captured
        assert handed["roles_path_override"] is not None
        assert handed["artifact_id"] is not None

    got = client.get(f"/api/skills/text-segmentation/runs/compare/{group_id}")
    assert got.status_code == 200
    assert {r["candidate_id"] for r in got.json()["runs"]} == {"fast", "slow"}


def test_node_compare_requires_candidates(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.run_manager as rm

    monkeypatch.setattr(rm, "_read_run_artifact_events", lambda run_dir: _dispatch_events("base", "setup", {"input_text": "x"}))
    resp = client.post(
        "/api/skills/text-segmentation/runs/base/compare",
        json={"node_id": "setup"},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "COMPARE_REQUIRES_CANDIDATES"
