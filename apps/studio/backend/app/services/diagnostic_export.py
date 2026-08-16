"""In-process diagnostic export contracts for Compile and Predict results."""

from __future__ import annotations

from typing import Any

from app.core.adapters.engine import RunResult
from app.core.exceptions import error_response, raise_error_response
from app.models.runs import PredictDiagnosticExport
from app.models.skills import CompileDiagnosticExport, CompileSuccess


def export_compile_diagnostics(result: CompileSuccess) -> CompileDiagnosticExport:
    """Project a compile result down to what an agent asked for: verdict + issues.

    Same shape of move as ``export_predict_diagnostics``: one pure function owns
    the projection, so the agent-facing surface cannot drift from the payload it
    is derived from. ``issues`` carries the engine's full aggregated set (see
    ``CompileDiagnosticExport``); the frontend keeps consuming ``CompileSuccess``
    whole and is untouched by this.
    """

    lint = result.detail.lint_result
    issues = list(lint.errors) if lint else []
    return CompileDiagnosticExport(
        skill_id=result.skill_id,
        status=result.status,
        phase_count=result.phase_count,
        manifest_name=result.manifest_name,
        execution_fingerprint=result.execution_fingerprint,
        lint_status=lint.status if lint else None,
        issue_count=len(issues),
        issues=issues,
        file_paths=result.detail.file_paths,
    )


def export_predict_diagnostics(result: RunResult) -> PredictDiagnosticExport:
    """Return the stable in-process payload consumed by Studio internals."""

    return PredictDiagnosticExport(
        is_predict=True,
        status=result.status,
        phases=result.phases or [],
        path_diff=result.path_diff,
        error=result.error,
        diagnostics=result.diagnostics,
        diagnostics_truncated=result.diagnostics_truncated,
        diagnostic_counts=result.diagnostic_counts,
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


__all__ = [
    "assert_trace_can_be_promoted_to_golden",
    "export_compile_diagnostics",
    "export_predict_diagnostics",
]
