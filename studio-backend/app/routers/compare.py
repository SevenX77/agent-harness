"""Run comparison endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import raise_not_implemented
from app.models.compare import CompareResult
from app.models.errors import ErrorResponse

router = APIRouter(prefix="/api/skills/{skill_id}/runs/{run_id}", tags=["compare"])


@router.post(
    "/compare",
    response_model=CompareResult,
    responses={501: {"model": ErrorResponse}},
)
async def compare_run(skill_id: str, run_id: str) -> CompareResult:
    raise_not_implemented(f"compare run {run_id} for skill {skill_id}")
