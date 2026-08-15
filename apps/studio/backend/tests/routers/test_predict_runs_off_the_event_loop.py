"""The predict endpoint must run the engine off the event loop.

`dispatch_predict_job` executes the whole graph_agent engine synchronously, and the
engine's batch-iterate path calls `asyncio.run()` internally
(`core/graph_assembler.py` `_run_batch_iterate_payload`, and the subagent batch path).
Calling it from the event loop thread therefore does two bad things at once: it
blocks every other request for the duration, and any skill using `iterate.mode=batch`
dies with `RuntimeError: asyncio.run() cannot be called from a running event loop`.

Observed live in the desktop app on 2026-08-15: clicking Predict on a skill with a
batch phase returned PREDICT_FAILED / not_retryable with that RuntimeError, mislabelled
as `llm.provider_invoke_failed`. The copilot tool path never hit it because
`services/copilot_tools.py` already wraps the same call in `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio

import pytest
from app.core.adapters.engine import PathDiff, RunResult
from app.services import predictor as predictor_module
from fastapi.testclient import TestClient


def _result() -> RunResult:
    return RunResult(
        success=True,
        run_id="predict-loop-check",
        skill_id="text-segmentation",
        context={},
        source="predict",
        phases=[],
        path_diff=PathDiff(
            expected_path=[],
            actual_path=[],
            missing=[],
            extra=[],
            order_mismatch=False,
        ),
    )


def test_predict_endpoint_calls_the_engine_without_a_running_loop(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whatever thread the engine ends up on, it must not have a running event loop —
    that is the precondition its internal `asyncio.run()` calls depend on."""
    seen: dict[str, bool] = {}

    def _record(*args: object, **kwargs: object) -> RunResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            seen["on_loop"] = False
        else:
            seen["on_loop"] = True
        return _result()

    monkeypatch.setattr(predictor_module.predictor_service, "dispatch_predict_job", _record)

    response = client.post(
        "/api/skills/text-segmentation/runs/predict",
        json={"input_data": {"input_text": "hi"}},
    )

    assert response.status_code == 200, response.text
    assert seen, "dispatch_predict_job was never called"
    assert seen["on_loop"] is False, (
        "the engine ran on the event loop thread; its internal asyncio.run() will raise "
        "for any skill with a batch phase, and the whole backend stalls meanwhile"
    )


def test_predict_endpoint_still_surfaces_engine_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Moving the call off the loop must not swallow the error paths that the
    endpoint translates into HTTP responses."""

    def _boom(*args: object, **kwargs: object) -> RunResult:
        raise predictor_module.PredictArtifactError(
            "engine.predict_failed",
            {"message": "artifact missing"},
            run_id="predict-err",
        )

    monkeypatch.setattr(predictor_module.predictor_service, "dispatch_predict_job", _boom)

    response = client.post(
        "/api/skills/text-segmentation/runs/predict",
        json={"input_data": {"input_text": "hi"}},
    )

    assert response.status_code >= 400, response.text
    assert "predict" in response.text.lower()
