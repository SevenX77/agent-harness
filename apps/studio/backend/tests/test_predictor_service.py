from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.services import predictor as predictor_module
from app.services.predictor import (
    PredictDeadlockError,
    PredictorService,
)
from graph_agent import PathDiff, PhaseRecord, RunResult
from graph_agent.core.runner import PredictDeadlockError as SDKPredictDeadlockError


@pytest.fixture(autouse=True)
def _isolate_studio_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


def test_dispatch_predict_job_delegates_to_sdk_predict_skill_and_persists_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)
    
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
        )
    )
    
    calls = []
    
    def fake_predict_skill(skill_path: Path, **kwargs: Any) -> RunResult:
        calls.append({"skill_path": skill_path, **kwargs})
        return mock_result
        
    monkeypatch.setattr(predictor_module, "predict_skill", fake_predict_skill)
    
    service = PredictorService()
    result = service.dispatch_predict_job(
        "skill",
        mock_param={"draft": {"text": "custom"}},
        input_data={"topic": "predict"},
        current_hashes={"draft": {"prompt_hash": "abc"}},
    )
    
    # 验证返回值
    assert result == mock_result
    
    # 验证向 SDK predict_skill 的参数传递
    assert len(calls) == 1
    assert calls[0]["skill_path"] == skill_dir
    assert calls[0]["mock_llm"] == {"draft": {"text": "custom"}}
    assert calls[0]["topic"] == "predict"
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
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)
    
    def fake_predict_skill_deadlock(skill_path: Path, **kwargs: Any) -> RunResult:
        raise SDKPredictDeadlockError("draft", ["draft"] * 11)
        
    monkeypatch.setattr(predictor_module, "predict_skill", fake_predict_skill_deadlock)
    
    service = PredictorService()
    with pytest.raises(PredictDeadlockError) as exc_info:
        service.dispatch_predict_job("skill", None)
        
    assert exc_info.value.phase_name == "draft"
    assert exc_info.value.actual_path == ["draft"] * 11
