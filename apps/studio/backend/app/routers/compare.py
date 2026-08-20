"""Comparing a finished run against a baseline.

One operation, one address. There used to be three: a ``POST /compare`` that
Starlette never reached (``routers/runs.py`` claims that address first for
node-compare side-runs) and could not take an ``against`` baseline anyway, plus
a ``GET /diff`` that was a second name for the line below it. A reader had no
way to tell which of the three was the real one, and one of them was dead.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.compare import CompareResult
from app.models.errors import ErrorResponse
from app.services.golden_diff import compare_run_to_golden

router = APIRouter(prefix="/api/skills/{skill_id}/runs/{run_id}", tags=["compare"])


@router.get(
    "/compare",
    response_model=CompareResult,
    responses={404: {"model": ErrorResponse}},
)
async def compare_run_get(skill_id: str, run_id: str, against: str | None = None) -> CompareResult:
    return compare_run_to_golden(skill_id, run_id, against=against)
