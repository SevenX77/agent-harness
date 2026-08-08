from __future__ import annotations

import json
import queue
import subprocess
import time
from pathlib import Path
from typing import Any

from app.core import config
from app.core.backends import clear_backend_caches
from app.services.local_settings import read_local_settings, write_local_settings
from app.services.run_manager import run_manager
from fastapi.testclient import TestClient

from tests.test_api import (
    InlineProcess,
    _agent_skill_files,
    _record_predict_pass,
    fake_run_worker,
)

FALLBACK_HEADERS = {"X-Studio-Write-Fallback": "browser"}


def test_p0_skill_git_directory_index_and_workspace_flow(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: Any,
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    monkeypatch.setattr(run_manager, "process_factory", InlineProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)

    create_response = client.post(
        "/api/skills",
        json={"skill_id": "p0-skill", "files": _agent_skill_files("p0-skill")},
    )

    assert create_response.status_code == 201
    skill_dir = config.DEFAULT_SKILLS_ROOT / "p0-skill"
    workspace_dir = skill_dir / ".workspace"
    assert (skill_dir / "GRAPH.md").exists()
    assert workspace_dir.is_dir()
    assert (skill_dir / ".git").is_dir()
    assert (skill_dir / ".gitignore").read_text(encoding="utf-8").splitlines() == [
        "/.workspace/*",
        "!/.workspace/golden/",
        "/.workspace/local_settings.json",
    ]
    git_user = subprocess.run(
        ["git", "config", "--local", "user.name"],
        cwd=skill_dir,
        check=True,
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    ).stdout.strip()
    assert git_user == "studio-user"
    assert not (workspaces_dir / "default" / "skills" / "p0-skill" / "GRAPH.md").exists()

    settings_path = write_local_settings(skill_dir, {"sidebar": "collapsed"})
    assert settings_path == workspace_dir / "local_settings.json"
    assert read_local_settings(skill_dir) == {"sidebar": "collapsed"}

    index = json.loads(config.SKILL_INDEX_PATH.read_text(encoding="utf-8"))
    assert index["p0-skill"]["absolute_path"] == str(skill_dir)
    clear_backend_caches()

    detail_response = client.get("/api/skills/p0-skill")

    assert detail_response.status_code == 200
    file_paths = detail_response.json()["file_paths"]
    assert file_paths["runs_dir"] == str(workspace_dir / "runs")
    assert file_paths["golden_dir"] == str(workspace_dir / "golden")
    assert "predict_dir" not in file_paths
    assert file_paths["local_settings"] == str(workspace_dir / "local_settings.json")

    _record_predict_pass("p0-skill")
    run_response = client.post("/api/skills/p0-skill/runs", json={"input_data": {"topic": "p0"}})
    assert run_response.status_code == 202
    run_id = run_response.json()["run_id"]

    for _ in range(20):
        run_detail = client.get(f"/api/skills/p0-skill/runs/{run_id}").json()
        if run_detail.get("metadata", {}).get("status") == "success":
            break
        time.sleep(0.05)

    run_dir = workspace_dir / "runs" / run_id
    assert (run_dir / "final_state.json").exists()
    assert (workspace_dir / "runs" / "latest" / "run_metadata.json").exists()
    git_log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=skill_dir,
        check=True,
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    ).stdout
    # The run only wrote .workspace/ (git-ignored), so the skill is byte-identical
    # to "initial-skill": there is no new version to archive.
    assert git_log.splitlines() == [line for line in git_log.splitlines() if "initial-skill" in line]
    assert f"auto-run-{run_id}" not in git_log
    assert client.get(f"/api/skills/p0-skill/runs/{run_id}").json()["metadata"][
        "git_status"
    ] == "unchanged"

    golden_response = client.post(
        "/api/skills/p0-skill/golden",
        json={"run_id": run_id, "lock": False},
        headers=FALLBACK_HEADERS,
    )

    assert golden_response.status_code == 200
    assert golden_response.json()["baseline_ref"] == f".workspace/golden/{run_id}/baseline.json"
    assert golden_response.json()["source_run_results_ref"] == f"p0-skill/runs/{run_id}/result.json"
    assert (workspace_dir / "golden" / run_id / "baseline.json").exists()
    assert (workspace_dir / "golden" / run_id / "report.json").exists()
    assert (workspace_dir / "golden" / run_id / "cases" / "setup.json").exists()
    assert not (workspace_dir / "golden" / run_id / "golden_metadata.json").exists()
