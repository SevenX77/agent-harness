from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.models.runs import PredictDiagnosticExport
from app.services.predictor import PredictorService


def test_predictor_service_integrates_with_sdk_predict_skill(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # We mock out ensured skill directory
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    
    import app.services.predictor as predictor_module
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)
    
    # We will mock the predict_skill call, returning a mock RunResult
    # Since predict_skill is the new public API in the SDK
    calls = []
    
    # In Pydantic/SDK, we will have a real RunResult
    # For the Red Phase, let's assume we import RunResult and construct it.
    # Since RunResult doesn't exist yet, we will mock it or let it fail!
    try:
        from graph_agent import PathDiff, PhaseRecord, RunResult
    except ImportError:
        # Expected to fail in Red Phase!
        pytest.fail("Cannot import RunResult, PhaseRecord, PathDiff in Red Phase")
        
    mock_result = RunResult(
        success=True,
        run_id="predict-run-123",
        skill_id="skill",
        context={},
        source="predict",
        phases=[
            PhaseRecord(
                phase_name="draft",
                type="llm",
                inputs={"topic": "predict"},
                outputs={"text": "hello"},
                mocked_source="heuristic_stub"
            )
        ],
        path_diff=PathDiff(
            expected_path=["draft"],
            actual_path=["draft"],
            missing=[],
            extra=[],
            order_mismatch=False
        )
    )
    
    def fake_predict_skill(skill_path: Path, **kwargs: Any) -> Any:
        calls.append({"skill_path": skill_path, **kwargs})
        return mock_result
        
    # We patch predict_skill in the predictor module
    # (or inside the predictor_service since it delegates to it)
    service = PredictorService(run_skill_fn=fake_predict_skill)
    monkeypatch.setattr(predictor_module, "predict_skill", fake_predict_skill)
    
    # Execute predictor service
    result = service.dispatch_predict_job("skill", None)
    diag_export = service.export_diagnostics(result)
    
    # Assertions
    assert isinstance(diag_export, PredictDiagnosticExport)
    assert diag_export.is_predict is True
    assert diag_export.status == "success"
    assert len(diag_export.phases) == 1
    assert diag_export.phases[0].phase_name == "draft"
