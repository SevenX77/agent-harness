"""Run comparison endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.compare import CompareResult
from app.models.errors import ErrorResponse
from app.services.golden_diff import compare_run_to_golden

router = APIRouter(prefix="/api/skills/{skill_id}/runs/{run_id}", tags=["compare"])


@router.post(
    "/compare",
    response_model=CompareResult,
    responses={501: {"model": ErrorResponse}},
)
async def compare_run(skill_id: str, run_id: str) -> CompareResult:
    return compare_run_to_golden(skill_id, run_id)


@router.get(
    "/compare",
    response_model=CompareResult,
    responses={404: {"model": ErrorResponse}},
)
async def compare_run_get(skill_id: str, run_id: str, against: str | None = None) -> CompareResult:
    return compare_run_to_golden(skill_id, run_id, against=against)


@router.get(
    "/diff",
    response_model=CompareResult,
    responses={404: {"model": ErrorResponse}},
)
async def diff_run(skill_id: str, run_id: str, against: str | None = None) -> CompareResult:
    return compare_run_to_golden(skill_id, run_id, against=against)
