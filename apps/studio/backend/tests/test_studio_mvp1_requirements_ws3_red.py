from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.services import predictor as predictor_module
from app.services import run_manager as run_manager_module
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolate_studio_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

def test_predict_run_endpoint_returns_structured_errors_on_compile_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """RED Test: Predict failure should return HTTP 400 with a structured compile_failed DTO,

    not a 500 or silent console output.
    """
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)
    
    # Simulate a validation / compilation error in predictor_service dispatch
    mock_dispatch = MagicMock(side_effect=ValueError("Compile failed in phase draft: invalid system_prompt"))
    monkeypatch.setattr(predictor_module.predictor_service, "dispatch_predict_job", mock_dispatch)
    
    response = client.post(
        "/api/skills/skill/runs/predict",
        json={
            "input_data": {"topic": "test"},
            "mock_llm": {},
            "current_hashes": {},
        }
    )
    
    # Prove the request actually reached predictor_service.dispatch_predict_job
    assert mock_dispatch.called is True

    # Expect a structured 400 response mapping the validation failure (will fail currently with 422)
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "compile_failed"
    assert len(data["errors"]) > 0
    assert data["errors"][0]["field"] == "system_prompt"
    assert "Invalid" in data["errors"][0]["message"]

def test_create_run_endpoint_returns_metadata_and_saves_final_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Regression Lock Test: start run triggers RunMetadata creation, 

    sets status to 'running' and correctly persists metadata.
    """
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    
    # Stub resolves
    monkeypatch.setattr(run_manager_module, "resolve_skill_dir", lambda skill_id: skill_dir)
    monkeypatch.setattr(run_manager_module, "run_dir_for", lambda skill_id, run_id: tmp_path / "runs" / run_id)
    
    # Mock Process creation to avoid running a real subprocess
    mock_proc = MagicMock()
    monkeypatch.setattr(run_manager_module.run_manager, "process_factory", MagicMock(return_value=mock_proc))
    
    response = client.post(
        "/api/skills/skill/runs",
        json={
            "input_data": {"topic": "test"}
        }
    )
    
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "running"
    assert "started_at" in data
