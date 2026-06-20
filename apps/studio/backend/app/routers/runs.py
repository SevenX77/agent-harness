"""Run endpoint scaffold."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Response, status

from app.core.adapters.http_transport import StudioAdapterError
from app.core.exceptions import error_response, raise_error_response
from app.models.errors import ErrorResponse
from app.models.runs import (
    BatchRunRequest,
    BatchRunResponse,
    BatchRunStatus,
    PredictDiagnosticExport,
    PredictRunRequest,
    ResumeReq,
    ResumeValidityReq,
    ResumeValidityResponse,
    RunDetail,
    RunListResponse,
    RunMetadata,
    RunRequest,
    TokensMetrics,
)
from app.services.predictor import predictor_service
from app.services.run_manager import run_manager

router = APIRouter(prefix="/api/skills/{skill_id}/runs", tags=["runs"])
batch_router = APIRouter(prefix="/api/batch", tags=["batch"])


@router.post("", response_model=RunMetadata, status_code=202)
async def create_run(skill_id: str, request: RunRequest) -> RunMetadata:
    return await run_manager.start_run(skill_id, request)


@router.post("/predict", response_model=PredictDiagnosticExport)
async def predict_run(skill_id: str, request: PredictRunRequest) -> PredictDiagnosticExport:
    # N4 atom #30: project the in-process diagnostic export (is_predict / status /
    # phases / path_diff) instead of leaking the raw RunResult. The frontend reads
    # which agent nodes ran from `phases` to drive the golden 🟡 logic-OK middle state.
    result = predictor_service.dispatch_predict_job(
        skill_id,
        request.mock_llm,
        input_data=request.input_data,
        current_hashes=request.current_hashes,
    )
    return predictor_service.export_diagnostics(result)


@router.get("", response_model=RunListResponse)
async def list_runs(skill_id: str) -> RunListResponse:
    return run_manager.list_runs(skill_id)


@router.post("/batch-run", response_model=BatchRunResponse, status_code=202)
async def create_batch_run(skill_id: str, request: BatchRunRequest) -> BatchRunResponse:
    return await run_manager.start_batch_run(skill_id, request.input_ids)


@router.get(
    "/{run_id}",
    response_model=RunDetail,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def get_run(skill_id: str, run_id: str) -> RunDetail:
    try:
        return run_manager.get_run_detail(skill_id=skill_id, run_id=run_id)
    except StudioAdapterError as exc:
        if not exc.error_code.startswith("artifact."):
            raise
        _raise_artifact_error_response(exc)


_ARTIFACT_ERROR_STATUS: dict[str, int] = {
    "artifact.not_found": 404,
    "artifact.run_not_sealed": 409,
}

_STATE_ERROR_STATUS: dict[str, int] = {
    "state.lease_conflict": 409,
    "state.lease_fenced": 409,
    "state.lease_required": 409,
    "state.release_failed": 409,
    "state.not_found": 404,
}


def _raise_artifact_error_response(exc: StudioAdapterError) -> NoReturn:
    http_status = _ARTIFACT_ERROR_STATUS.get(exc.error_code, 422)
    detail = exc.error_payload.get("detail")
    message = str(detail) if detail else f"Artifact error: {exc.error_code}"
    raise_error_response(
        error_response(
            error_code=exc.error_code,
            http_status=http_status,
            message=message,
            details=exc.error_payload,
            retry_strategy="not_retryable",
        )
    )


def _raise_state_error_response(exc: StudioAdapterError) -> NoReturn:
    http_status = _STATE_ERROR_STATUS.get(exc.error_code, 422)
    detail = exc.error_payload.get("detail")
    message = str(detail) if detail else f"Runtime state error: {exc.error_code}"
    raise_error_response(
        error_response(
            error_code=exc.error_code,
            http_status=http_status,
            message=message,
            details=exc.error_payload,
            retry_strategy="backoff" if http_status == 409 else "not_retryable",
        )
    )


def _tokens_metrics_payload(raw: Any) -> TokensMetrics | None:
    if not isinstance(raw, dict):
        return None
    input_tokens = int(raw.get("total_input_tokens", raw.get("input_tokens", 0)) or 0)
    output_tokens = int(raw.get("total_output_tokens", raw.get("output_tokens", 0)) or 0)
    raw_wall_time = raw.get("wall_time_sec")
    return TokensMetrics(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=int(raw.get("total_tokens", input_tokens + output_tokens) or 0),
        cost_estimate=raw.get("cost_estimate"),
        # ⑧a: resume path mirror of run_manager — pass the engine's wall_time_sec through
        # instead of stripping it, so resumed-run history shows real 耗时.
        wall_time_sec=float(raw_wall_time) if raw_wall_time is not None else None,
    )


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(skill_id: str, run_id: str) -> Response:
    run_manager.delete_run(skill_id=skill_id, run_id=run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{run_id}/resume/validity",
    response_model=ResumeValidityResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def get_resume_validity(
    skill_id: str,
    run_id: str,
    request: ResumeValidityReq,
) -> ResumeValidityResponse:
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.transport_factory import build_engine_adapter
    from app.core.exceptions import standard_http_exception

    adapter = build_engine_adapter()
    try:
        payload = {
            "skill_id": skill_id,
            "run_id": run_id,
        }
        if request.checkpoint_id is not None:
            payload["checkpoint_id"] = request.checkpoint_id
        if request.checkpoint_ns is not None:
            payload["checkpoint_ns"] = request.checkpoint_ns
        if request.resume_from_node_id is not None:
            payload["resume_from_node_id"] = request.resume_from_node_id
        if request.resume_to_node_id is not None:
            payload["resume_to_node_id"] = request.resume_to_node_id
        result = adapter.resume_validity(payload)
    except StudioAdapterError as exc:
        if exc.error_code.startswith("state."):
            _raise_state_error_response(exc)
        raise standard_http_exception(
            "RESUME_VALIDITY_FAILED",
            f"Resume validity failed: {exc.error_payload.get('detail', str(exc))}",
            exc.error_payload,
        ) from exc
    return ResumeValidityResponse.model_validate(result)


@router.post(
    "/{run_id}/resume",
    response_model=RunMetadata,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def resume_run(skill_id: str, run_id: str, request: ResumeReq) -> RunMetadata:
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.transport_factory import build_engine_adapter
    from app.core.exceptions import standard_http_exception

    adapter = build_engine_adapter()
    try:
        payload = {
            "skill_id": skill_id,
            "run_id": run_id,
            "context_overrides": request.context_overrides,
            "human_input": request.human_input,
        }
        if request.checkpoint_id is not None:
            payload["checkpoint_id"] = request.checkpoint_id
        if request.checkpoint_ns is not None:
            payload["checkpoint_ns"] = request.checkpoint_ns
        if request.resume_from_node_id is not None:
            payload["resume_from_node_id"] = request.resume_from_node_id
        if request.resume_to_node_id is not None:
            payload["resume_to_node_id"] = request.resume_to_node_id
        if request.human_response is not None:
            payload["human_response"] = request.human_response
        result = adapter.resume(payload)
    except StudioAdapterError as exc:
        if exc.error_code.startswith("state."):
            _raise_state_error_response(exc)
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Resume failed: {exc.error_payload.get('detail', str(exc))}",
            exc.error_payload,
        ) from exc
    metadata = RunMetadata(
        run_id=result["run_id"],
        status=result["status"],
        started_at=result["started_at"],
        input_summary=result.get("input_summary"),
        metrics=_tokens_metrics_payload(result.get("metrics")),
        git_status=result.get("git_status"),
    )
    return await run_manager.record_resume_result(
        skill_id=skill_id,
        run_id=run_id,
        request=request,
        metadata=metadata,
    )


@batch_router.get("/{batch_id}", response_model=BatchRunStatus)
async def get_batch_status(batch_id: str) -> BatchRunStatus:
    return run_manager.get_batch_status(batch_id)
