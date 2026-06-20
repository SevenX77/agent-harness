"""n4-trace#23 (trace-model-compare): P8 model-compare vertical slice tests.

Covers the Studio-shell fan-out: a run request carrying candidates materializes
a per-candidate temporary roles file, spawns one worker per candidate against the
same artifact + inputs, tags each run with a shared compare_group_id, and exposes
them grouped (incl. a failed candidate) for the frontend Trace tabs. No engine or
gateway edit.
"""

from __future__ import annotations

import json
import queue
from pathlib import Path
from typing import Any

import pytest
from app.models.llm_config import RoleEntry, RoleIntent, RolesData
from app.models.runs import RunCandidate
from app.services import run_compare
from app.services.predict_gate import record_predict_pass
from app.services.run_manager import run_manager
from app.services.skills import resolve_skill_dir
from fastapi.testclient import TestClient


def _record_predict_pass(skill_id: str) -> None:
    from app.core.adapters.engine import EngineAdapter

    skill_dir = resolve_skill_dir(skill_id)
    adapter = EngineAdapter(transport="in_process")
    art_ref = adapter.compile(
        {"skill_dir": str(skill_dir), "skill_id": skill_id, "artifact_scope": "ephemeral"}
    )
    record_predict_pass(skill_dir, skill_id, "predict-fixture", content_hash=art_ref["content_hash"])


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


def _fake_compare_worker(
    skill_id: str,
    run_dir_raw: str,
    inputs: dict[str, Any],
    process_queue: "queue.Queue[dict[str, Any]]",
    art_ref: dict[str, Any],
    roles_path_override: str | None = None,
) -> None:
    """Records the roles override it was handed (proving per-candidate isolation)."""
    del inputs, art_ref, skill_id
    run_dir = Path(run_dir_raw)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "roles_seen.json").write_text(
        json.dumps({"roles_path_override": roles_path_override}), encoding="utf-8"
    )
    (run_dir / "final_state.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    process_queue.put({"type": "status", "status": "success", "metrics": {}})


# ---------------------------------------------------------------------------
# Unit: per-candidate roles materialization
# ---------------------------------------------------------------------------


def _base_roles() -> RolesData:
    main = RoleEntry(role_kind="graph_agent", intent=RoleIntent())
    cand = RoleEntry(role_kind="graph_agent", intent=RoleIntent())
    return RolesData(roles={"main": main, "cand-fast": cand})


def test_write_candidate_roles_file_overrides_graph_agent_roles(tmp_path: Path) -> None:
    base = _base_roles()
    candidate = RunCandidate(candidate_id="fast", role_name="cand-fast")
    group_dir = tmp_path / "group"

    path = run_compare.write_candidate_roles_file(
        candidate=candidate,
        group_dir=group_dir,
        base_roles=base,
    )

    assert path.exists()
    assert path.name == "llm_roles__fast.yaml"


def test_apply_candidate_role_targets_named_role_only() -> None:
    base = _base_roles()
    base.roles["other"] = RoleEntry(role_kind="graph_agent")
    candidate = RunCandidate(candidate_id="fast", role_name="cand-fast", target_role="main")

    projected = run_compare._apply_candidate_role(base, candidate=candidate)

    # only `main` is rebound; `other` is untouched.
    assert set(projected.roles) == {"main", "cand-fast", "other"}


def test_apply_candidate_role_unknown_role_raises() -> None:
    base = _base_roles()
    candidate = RunCandidate(candidate_id="x", role_name="missing")

    with pytest.raises(run_compare.CompareCandidateError):
        run_compare._apply_candidate_role(base, candidate=candidate)


# ---------------------------------------------------------------------------
# Integration: API fan-out + grouping
# ---------------------------------------------------------------------------


def _seed_active_roles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.services.llm_roles import save_roles_file

    roles_file = tmp_path / "llm_roles.yaml"
    save_roles_file(roles_file, _base_roles())
    monkeypatch.setenv("STUDIO_LLM_ROLES_PATH", str(roles_file))


def test_compare_run_fans_out_and_groups_by_candidate(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active_roles(monkeypatch, tmp_path)
    monkeypatch.setattr(run_manager, "process_factory", _InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", _fake_compare_worker)
    _record_predict_pass("text-segmentation")

    response = client.post(
        "/api/skills/text-segmentation/runs/compare",
        json={
            "input_data": {"input_text": "hello"},
            "candidates": [
                {"candidate_id": "fast", "role_name": "cand-fast"},
                {"candidate_id": "main", "role_name": "main"},
            ],
        },
    )

    assert response.status_code == 202
    body = response.json()
    group_id = body["compare_group_id"]
    assert group_id.startswith("cmp-")
    assert {run["candidate_id"] for run in body["runs"]} == {"fast", "main"}
    # each spawned run is tagged with the shared compare group
    for run in body["runs"]:
        assert run["metadata"]["compare_group_id"] == group_id
        assert run["metadata"]["candidate_id"] == run["candidate_id"]

    group_response = client.get(f"/api/skills/text-segmentation/runs/compare/{group_id}")
    assert group_response.status_code == 200
    group_body = group_response.json()
    assert group_body["compare_group_id"] == group_id
    grouped_ids = {run["candidate_id"] for run in group_body["runs"]}
    assert grouped_ids == {"fast", "main"}
    # each candidate worker received a DISTINCT per-candidate roles file.
    role_files = {
        run["candidate_id"]: run["role_name"] for run in group_body["runs"]
    }
    assert role_files == {"fast": "cand-fast", "main": "main"}


def test_compare_run_requires_candidates(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active_roles(monkeypatch, tmp_path)
    _record_predict_pass("text-segmentation")

    response = client.post(
        "/api/skills/text-segmentation/runs/compare",
        json={"input_data": {"input_text": "hi"}, "candidates": []},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "COMPARE_REQUIRES_CANDIDATES"
