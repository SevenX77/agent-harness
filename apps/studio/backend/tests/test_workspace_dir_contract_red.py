from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.services import predictor as predictor_module
from app.services.git_local import STUDIO_GITIGNORE
from app.services.predictor import PredictorService
from fastapi.testclient import TestClient

from tests.test_api import _agent_skill_files


def _raw_predict_result() -> dict[str, object]:
    return {
        "success": True,
        "run_id": "predict-workspace-run",
        "skill_id": "skill",
        "context": {
            "predict_trace": [
                {
                    "phase_name": "draft",
                    "type": "llm",
                    "inputs": {"topic": "predict"},
                    "outputs": {"text": "<mock_text>"},
                    "mocked_source": "heuristic_stub",
                }
            ],
            "actual_path": ["draft"],
        },
        "metrics": {},
        "source": "predict",
        "phases": [
            {
                "phase_name": "draft",
                "type": "llm",
                "inputs": {"topic": "predict"},
                "outputs": {"text": "<mock_text>"},
                "mocked_source": "heuristic_stub",
            }
        ],
        "path_diff": None,
    }


def test_skill_detail_file_paths_do_not_expose_predict_dir(client: TestClient) -> None:
    response = client.get("/api/skills/text-segmentation")

    assert response.status_code == 200
    assert "predict_dir" not in response.json()["file_paths"]


def test_predictor_dispatch_writes_predict_artifacts_under_workspace_predicts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    workspace_dir = skill_dir / ".workspace"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)

    import app.core.adapters.engine as engine_adapter_module

    artifact_ref = {
        "artifact_id": "skill",
        "content_hash": f"sha256:{'c' * 64}",
        "store": "ephemeral",
        "manifest_ref": "manifests/skill.json",
    }

    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "compile",
        lambda *_args, **_kwargs: artifact_ref,
    )

    def fake_predict_artifact(_adapter: object, payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        # The engine runs under the thread_id Studio hands it and reports that id
        # back; a stub that invents its own id would file the account somewhere
        # no reader looks.
        return {**_raw_predict_result(), "run_id": payload["thread_id"]}

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact)

    service = PredictorService()

    result = service.dispatch_predict_job("skill", None, input_data={"topic": "predict"})

    assert result.status == "success"
    run_dir = workspace_dir / "predicts" / str(calls[0]["thread_id"])
    assert (run_dir / "result.json").is_file()
    assert not (run_dir / "latest_predict.json").exists()
    assert not (workspace_dir / "predict").exists()
    assert calls[0]["workspace_dir"] == str(workspace_dir)


def test_new_skill_gitignore_template_no_longer_unignores_top_level_predict(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/skills",
        json={
            "skill_id": "workspace-gitignore",
            "files": _agent_skill_files("workspace-gitignore"),
        },
    )

    assert response.status_code == 201
    assert "!/.workspace/predict/" not in STUDIO_GITIGNORE.splitlines()
    gitignore_lines = (
        (config.DEFAULT_SKILLS_ROOT / "workspace-gitignore" / ".gitignore").read_text(encoding="utf-8").splitlines()
    )
    assert "!/.workspace/predict/" not in gitignore_lines
