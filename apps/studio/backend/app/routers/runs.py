"""Run endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.models.errors import ErrorResponse
from app.models.runs import (
    BatchRunRequest,
    BatchRunResponse,
    BatchRunStatus,
    PredictRunRequest,
    ResumeReq,
    RunDetail,
    RunListResponse,
    RunMetadata,
    RunRequest,
)
from app.services.predictor import predictor_service
from app.services.run_manager import run_manager

router = APIRouter(prefix="/api/skills/{skill_id}/runs", tags=["runs"])
batch_router = APIRouter(prefix="/api/batch", tags=["batch"])


@router.post("", response_model=RunMetadata, status_code=202)
async def create_run(skill_id: str, request: RunRequest) -> RunMetadata:
    return await run_manager.start_run(skill_id, request)


@router.post("/predict")
async def predict_run(skill_id: str, request: PredictRunRequest) -> dict[str, object]:
    result = predictor_service.dispatch_predict_job(
        skill_id,
        request.mock_llm,
        input_data=request.input_data,
        current_hashes=request.current_hashes,
    )
    return result.model_dump(mode="json")


@router.get("", response_model=RunListResponse)
async def list_runs(skill_id: str) -> RunListResponse:
    return run_manager.list_runs(skill_id)


@router.post("/batch-run", response_model=BatchRunResponse, status_code=202)
async def create_batch_run(skill_id: str, request: BatchRunRequest) -> BatchRunResponse:
    return await run_manager.start_batch_run(skill_id, request.input_ids)


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(skill_id: str, run_id: str) -> RunDetail:
    return run_manager.get_run_detail(skill_id=skill_id, run_id=run_id)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(skill_id: str, run_id: str) -> Response:
    run_manager.delete_run(skill_id=skill_id, run_id=run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{run_id}/resume",
    response_model=RunMetadata,
    responses={501: {"model": ErrorResponse}},
)
async def resume_run(skill_id: str, run_id: str, request: ResumeReq) -> RunMetadata:
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.exceptions import standard_http_exception

    adapter = EngineAdapter(transport="in_process")
    try:
        result = adapter.resume(
            {
                "skill_id": skill_id,
                "run_id": run_id,
                "context_overrides": request.context_overrides,
                "human_input": request.human_input,
            }
        )
    except StudioAdapterError as exc:
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Resume failed: {exc.error_payload.get('detail', str(exc))}",
            exc.error_payload,
        ) from exc
    return RunMetadata(
        run_id=result["run_id"],
        status=result["status"],
        started_at=result["started_at"],
        input_summary=result.get("input_summary"),
        metrics=result.get("metrics"),
        git_status=result.get("git_status"),
    )


@batch_router.get("/{batch_id}", response_model=BatchRunStatus)
async def get_batch_status(batch_id: str) -> BatchRunStatus:
    return run_manager.get_batch_status(batch_id)
