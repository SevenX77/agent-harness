from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.services import predictor as predictor_module
from app.services.predictor import (
    PredictArtifactError,
    PredictDeadlockError,
    PredictorService,
)
from graph_agent import PathDiff, PhaseRecord, RunResult


@pytest.fixture(autouse=True)
def _isolate_studio_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


def test_dispatch_predict_job_delegates_to_engine_predict_artifact_and_persists_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    import app.core.adapters.engine as engine_adapter_module

    mock_art_ref = {
        "artifact_id": "skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "compile",
        lambda *a, **k: mock_art_ref,
    )

    mock_result = RunResult(
        success=True,
        run_id="predict-run-777",
        skill_id="skill",
        context={"topic": "predict"},
        source="predict",
        phases=[
            PhaseRecord(
                phase_name="draft",
                type="llm",
                inputs={"topic": "predict"},
                outputs={"text": "hello"},
                mocked_source="heuristic_stub",
            )
        ],
        path_diff=PathDiff(
            expected_path=["draft"],
            actual_path=["draft"],
            missing=[],
            extra=[],
            order_mismatch=False,
        ),
    )

    calls = []

    def fake_predict_artifact(_adapter: object, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return mock_result.model_dump(mode="json")

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact)

    service = PredictorService()
    result = service.dispatch_predict_job(
        "skill",
        mock_param={"draft": {"text": "custom"}},
        input_data={"topic": "predict"},
        current_hashes={"draft": {"prompt_hash": "abc"}},
    )

    # 验证返回值
    assert result == mock_result

    # 验证向 Engine artifact runtime 的参数传递
    assert len(calls) == 1
    assert calls[0]["mock_llm"] == {"draft": {"text": "custom"}}
    assert calls[0]["artifact_ref"] == mock_art_ref
    assert calls[0]["inputs"] == {"topic": "predict"}
    assert calls[0]["current_hashes"] == {"draft": {"prompt_hash": "abc"}}

    # 验证是否成功持久化了 result.json 到 runs 目录
    from app.services.skills import workspace_dir_for

    expected_result_json = workspace_dir_for(skill_dir) / "runs" / "predict-run-777" / "result.json"
    assert expected_result_json.exists()
    saved_data = json.loads(expected_result_json.read_text(encoding="utf-8"))
    assert saved_data["run_id"] == "predict-run-777"
    assert saved_data["success"] is True


def test_dispatch_predict_job_translates_sdk_deadlock_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    import app.core.adapters.engine as engine_adapter_module

    mock_art_ref = {
        "artifact_id": "skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "compile",
        lambda *a, **k: mock_art_ref,
    )

    def fake_predict_artifact_deadlock(_adapter: object, _payload: dict[str, Any]) -> None:
        from app.core.adapters.http_transport import StudioAdapterError

        raise StudioAdapterError("engine.predict_deadlock", {"phase_name": "draft", "actual_path": ["draft"] * 11})

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact_deadlock)

    service = PredictorService()
    with pytest.raises(PredictDeadlockError) as exc_info:
        service.dispatch_predict_job("skill", None)

    assert exc_info.value.phase_name == "draft"
    assert exc_info.value.actual_path == ["draft"] * 11


def test_dispatch_predict_job_projects_artifact_error_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    import app.core.adapters.engine as engine_adapter_module

    mock_art_ref = {
        "artifact_id": "skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "compile",
        lambda *a, **k: mock_art_ref,
    )

    def fake_predict_artifact(_adapter: object, _payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "error_code": "llm.provider_not_configured",
            "error_payload": {"message": "LLM Provider is not configured"},
            "retryable": False,
            "run_id": "predict-error-1",
        }

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact)

    service = PredictorService()
    with pytest.raises(PredictArtifactError) as exc_info:
        service.dispatch_predict_job("skill", None)

    assert exc_info.value.error_code == "llm.provider_not_configured"
    assert exc_info.value.error_payload == {"message": "LLM Provider is not configured"}
    assert exc_info.value.run_id == "predict-error-1"
    assert exc_info.value.retryable is False
