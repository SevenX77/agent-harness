"""N4 atom #30: the predict endpoint projects the in-process PredictDiagnosticExport.

The 🟡 logic-OK middle state needs the frontend to learn *which nodes ran* in the
most-recent predict. Rather than mint a second predict response model, the endpoint
returns the already-existing ``PredictDiagnosticExport`` (is_predict / status / phases
/ path_diff) so the frontend reads ran-agent-nodes from ``phases`` (a phase is recorded
only on completion). These tests pin the projected response shape, not a new DTO.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.core.adapters.engine import PathDiff, PhaseRecord, RunResult, make_error_payload
from app.services import predictor as predictor_module
from app.services.predictor import PredictArtifactError
from fastapi.testclient import TestClient


def _predict_result() -> RunResult:
    return RunResult(
        success=True,
        run_id="predict-projection",
        skill_id="text-segmentation",
        context={"prepared": True},
        source="predict",
        phases=[
            PhaseRecord(
                phase_name="setup",
                type="logic",
                inputs={"input_text": "hi"},
                outputs={"prepared": True},
            ),
            PhaseRecord(
                phase_name="draft",
                type="llm",
                inputs={"prepared": True},
                outputs={"text": "hello"},
                mocked_source="heuristic_stub",
            ),
        ],
        path_diff=PathDiff(
            expected_path=["setup", "draft"],
            actual_path=["setup", "draft"],
            missing=[],
            extra=[],
            order_mismatch=False,
        ),
    )


def _patch_predict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        predictor_module.predictor_service,
        "dispatch_predict_job",
        lambda *args, **kwargs: _predict_result(),
    )


def test_predict_endpoint_returns_diagnostic_export_phases(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /runs/predict returns the PredictDiagnosticExport shape, not a raw RunResult."""
    _patch_predict(monkeypatch)

    response = client.post(
        "/api/skills/text-segmentation/runs/predict",
        json={"input_data": {"input_text": "hi"}},
    )

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    # PredictDiagnosticExport contract: the frontend gets path and engine diagnostics.
    assert set(body.keys()) == {
        "diagnostic_counts",
        "diagnostics",
        "diagnostics_truncated",
        "error",
        "is_predict",
        "path_diff",
        "phases",
        "status",
    }
    assert body["is_predict"] is True
    assert body["status"] == "success"
    phase_names = [phase["phase_name"] for phase in body["phases"]]
    assert phase_names == ["setup", "draft"]
    # The agent node carries type 'llm' so the frontend can filter 🟡 to agent nodes.
    types_by_phase = {phase["phase_name"]: phase["type"] for phase in body["phases"]}
    assert types_by_phase == {"setup": "logic", "draft": "llm"}


def test_predict_endpoint_does_not_leak_runresult_only_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The raw RunResult-only fields (run_id, success, metrics) must NOT appear."""
    _patch_predict(monkeypatch)

    response = client.post(
        "/api/skills/text-segmentation/runs/predict",
        json={"input_data": {"input_text": "hi"}},
    )

    assert response.status_code == 200
    body = response.json()
    for run_only_field in ("run_id", "success", "metrics", "context", "skill_id"):
        assert run_only_field not in body


def test_predict_endpoint_returns_engine_diagnostics_for_failed_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine_error = make_error_payload(
        "[F-v3-agent-exit-control-failed]",
        "Phase 'segment' failed: max iterations (2) reached without a valid finish_task marker.",
        phase_id="segment",
        field_path="business_data_md",
    )
    monkeypatch.setattr(
        predictor_module.predictor_service,
        "dispatch_predict_job",
        lambda *args, **kwargs: RunResult(
            success=False,
            run_id="predict-diagnostics",
            skill_id="text-segmentation",
            context={},
            source="predict",
            phases=[],
            path_diff=None,
            error=engine_error,
        ),
    )

    response = client.post(
        "/api/skills/text-segmentation/runs/predict",
        json={"input_data": {"input_text": "hi"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "[F-v3-agent-exit-control-failed]"
    assert body["error"]["phase_id"] == "segment"
    assert body["error"]["field_path"] == "business_data_md"
    assert body["diagnostics"] == [body["error"]]
    assert body["diagnostic_counts"]["total"] == 1


def test_predict_endpoint_projects_engine_artifact_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Engine predict failures must reach the frontend as structured diagnostics."""

    def raise_engine_error(*_args: Any, **_kwargs: Any) -> RunResult:
        raise PredictArtifactError(
            "engine.schema_invalid",
            {"message": "List schema shorthand must contain exactly one item type"},
            run_id="predict-error-1",
            retryable=False,
        )

    monkeypatch.setattr(
        predictor_module.predictor_service,
        "dispatch_predict_job",
        raise_engine_error,
    )

    response = client.post(
        "/api/skills/text-segmentation/runs/predict",
        json={"input_data": {"input_text": "hi"}},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error_code": "PREDICT_FAILED",
        "http_status": 422,
        "message": "List schema shorthand must contain exactly one item type",
        "details": {
            "engine_error_code": "engine.schema_invalid",
            "engine_error_payload": {
                "message": "List schema shorthand must contain exactly one item type"
            },
            "retryable": False,
            "run_id": "predict-error-1",
        },
        "retry_strategy": "not_retryable",
    }
