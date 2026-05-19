from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core import config
from app.services.diagnostic_export import (
    assert_trace_can_be_promoted_to_golden,
    export_predict_diagnostics,
)
from app.services.golden_diff import set_golden_baseline_for_run
from fastapi import HTTPException
from graph_agent.core._predict_internal.models import PathDiff, PhaseRecord, PredictResult


def _predict_result() -> PredictResult:
    return PredictResult(
        status="failed",
        phases=[
            PhaseRecord(
                phase_name="draft",
                type="llm",
                inputs={"topic": "predict"},
                outputs={"text": "manual"},
                mocked_source="manual",
            ),
            PhaseRecord(
                phase_name="validate",
                type="logic",
                inputs={"text": "manual"},
                outputs={"passed": True},
            ),
        ],
        path_diff=PathDiff(
            expected_path=["draft", "finish"],
            actual_path=["draft", "validate"],
            missing=["finish"],
            extra=["validate"],
        ),
    )


def test_export_predict_diagnostics_preserves_predict_result_contract() -> None:
    exported = export_predict_diagnostics(_predict_result())
    payload = exported.model_dump(mode="json")

    assert payload == {
        "is_predict": True,
        "status": "failed",
        "phases": [
            {
                "phase_name": "draft",
                "type": "llm",
                "inputs": {"topic": "predict"},
                "outputs": {"text": "manual"},
                "mocked_source": "manual",
            },
            {
                "phase_name": "validate",
                "type": "logic",
                "inputs": {"text": "manual"},
                "outputs": {"passed": True},
                "mocked_source": None,
            },
        ],
        "path_diff": {
            "expected_path": ["draft", "finish"],
            "actual_path": ["draft", "validate"],
            "missing": ["finish"],
            "extra": ["validate"],
            "order_mismatch": False,
        },
    }


def test_export_predict_diagnostics_does_not_pin_trace_to_golden_case() -> None:
    exported = export_predict_diagnostics(_predict_result())

    assert [phase.mocked_source for phase in exported.phases] == ["manual", None]


def test_predict_trace_is_rejected_before_golden_promotion() -> None:
    with pytest.raises(HTTPException) as exc_info:
        assert_trace_can_be_promoted_to_golden(
            {"metadata": {"is_predict": True}, "phases": []},
            skill_id="demo",
            run_id="predict-run",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_code"] == "PREDICT_TRACE_CANNOT_BE_GOLDEN"


def test_non_predict_trace_can_be_promoted_to_golden() -> None:
    assert_trace_can_be_promoted_to_golden({"answer": "real"}, skill_id="demo", run_id="real-run")


def test_set_golden_baseline_rejects_predict_final_state(
    studio_roots: tuple[Path, Path],
) -> None:
    _skills_dir, _workspaces_dir = studio_roots
    run_dir = config.SKILLS_DIR / "text-segmentation" / ".workspace" / "runs" / "predict-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "final_state.json").write_text(
        json.dumps({"metadata": {"is_predict": True}, "phases": []}),
        encoding="utf-8",
    )

    with pytest.raises(HTTPException):
        set_golden_baseline_for_run("text-segmentation", "predict-run", lock=False)
