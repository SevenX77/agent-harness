"""Golden baseline endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.models.errors import ErrorResponse
from app.models.golden import GoldenBaseline, SetGoldenReq
from app.services.golden_diff import (
    delete_golden_baseline_for_skill,
    list_golden_baselines_for_skill,
    set_golden_baseline_for_run,
)

router = APIRouter(prefix="/api/skills/{skill_id}/golden", tags=["golden"])


@router.get(
    "",
    response_model=list[GoldenBaseline],
    responses={501: {"model": ErrorResponse}},
)
async def list_golden_baselines(skill_id: str) -> list[GoldenBaseline]:
    return list_golden_baselines_for_skill(skill_id)


@router.post(
    "",
    response_model=GoldenBaseline,
    responses={501: {"model": ErrorResponse}},
)
async def set_golden_baseline(skill_id: str, request: SetGoldenReq) -> GoldenBaseline:
    return set_golden_baseline_for_run(skill_id, request.run_id, lock=request.lock)


@router.delete(
    "/{golden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def delete_golden_baseline(skill_id: str, golden_id: str) -> Response:
    delete_golden_baseline_for_skill(skill_id, golden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
