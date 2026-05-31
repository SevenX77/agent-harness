"""In-process diagnostic export contract for Predict results."""

from __future__ import annotations

from typing import Any

from graph_agent import RunResult

from app.core.exceptions import error_response, raise_error_response
from app.models.runs import PredictDiagnosticExport


def export_predict_diagnostics(result: RunResult) -> PredictDiagnosticExport:
    """Return the stable in-process payload consumed by Studio internals."""

    status = "success" if result.success else "failed"
    return PredictDiagnosticExport(
        is_predict=True,
        status=status,
        phases=result.phases or [],
        path_diff=result.path_diff,
    )


def assert_trace_can_be_promoted_to_golden(
    trace_payload: dict[str, Any],
    *,
    skill_id: str,
    run_id: str,
) -> None:
    """Reject Predict traces before they can be persisted as Golden baselines."""

    if _is_predict_trace(trace_payload):
        raise_error_response(
            error_response(
                error_code="PREDICT_TRACE_CANNOT_BE_GOLDEN",
                http_status=409,
                message="Predict traces cannot be saved as Golden baselines",
                details={"skill_id": skill_id, "run_id": run_id},
                retry_strategy="not_retryable",
            )
        )


def _is_predict_trace(trace_payload: dict[str, Any]) -> bool:
    if trace_payload.get("is_predict") is True:
        return True
    metadata = trace_payload.get("metadata")
    if isinstance(metadata, dict) and metadata.get("is_predict") is True:
        return True
    root = trace_payload.get("root")
    if isinstance(root, dict):
        root_metadata = root.get("metadata")
        return isinstance(root_metadata, dict) and root_metadata.get("is_predict") is True
    return False


__all__ = ["assert_trace_can_be_promoted_to_golden", "export_predict_diagnostics"]
