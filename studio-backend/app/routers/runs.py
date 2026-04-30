"""Run endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import raise_not_implemented
from app.models.errors import ErrorResponse
from app.models.runs import ResumeReq, RunDetail, RunMetadata, RunRequest
from app.services.placeholders import placeholder_run_detail, placeholder_run_metadata

router = APIRouter(prefix="/api/skills/{skill_id}/runs", tags=["runs"])


@router.post("", response_model=RunMetadata, status_code=202)
async def create_run(skill_id: str, request: RunRequest) -> RunMetadata:
    return placeholder_run_metadata(skill_id)


@router.get("", response_model=list[RunMetadata])
async def list_runs(skill_id: str) -> list[RunMetadata]:
    return []


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(skill_id: str, run_id: str) -> RunDetail:
    return placeholder_run_detail(skill_id=skill_id, run_id=run_id)


@router.post(
    "/{run_id}/resume",
    response_model=RunMetadata,
    responses={501: {"model": ErrorResponse}},
)
async def resume_run(skill_id: str, run_id: str, request: ResumeReq) -> RunMetadata:
    raise_not_implemented(f"resume run {run_id} for skill {skill_id}")
