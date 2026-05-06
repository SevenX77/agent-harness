"""Run endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.exceptions import raise_not_implemented
from app.models.errors import ErrorResponse
from app.models.runs import (
    BatchRunRequest,
    BatchRunResponse,
    BatchRunStatus,
    ResumeReq,
    RunDetail,
    RunListResponse,
    RunMetadata,
    RunRequest,
)
from app.services.run_manager import run_manager

router = APIRouter(prefix="/api/skills/{skill_id}/runs", tags=["runs"])
batch_router = APIRouter(prefix="/api/batch", tags=["batch"])


@router.post("", response_model=RunMetadata, status_code=202)
async def create_run(skill_id: str, request: RunRequest) -> RunMetadata:
    return await run_manager.start_run(skill_id, request)


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
    raise_not_implemented(f"resume run {run_id} for skill {skill_id}")


@batch_router.get("/{batch_id}", response_model=BatchRunStatus)
async def get_batch_status(batch_id: str) -> BatchRunStatus:
    return run_manager.get_batch_status(batch_id)
