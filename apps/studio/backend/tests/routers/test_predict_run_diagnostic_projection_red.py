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
from app.core.adapters.engine import PathDiff, PhaseRecord, RunResult
from app.services import predictor as predictor_module
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
    # PredictDiagnosticExport contract — exactly these keys (extra='forbid').
    assert set(body.keys()) == {"is_predict", "status", "phases", "path_diff"}
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
