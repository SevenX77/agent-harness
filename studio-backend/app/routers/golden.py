"""Golden baseline endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import raise_not_implemented
from app.models.errors import ErrorResponse
from app.models.golden import GoldenBaseline, SetGoldenReq

router = APIRouter(prefix="/api/skills/{skill_id}/golden", tags=["golden"])


@router.get(
    "",
    response_model=list[GoldenBaseline],
    responses={501: {"model": ErrorResponse}},
)
async def list_golden_baselines(skill_id: str) -> list[GoldenBaseline]:
    raise_not_implemented(f"list golden baselines for skill {skill_id}")


@router.post(
    "",
    response_model=GoldenBaseline,
    responses={501: {"model": ErrorResponse}},
)
async def set_golden_baseline(skill_id: str, request: SetGoldenReq) -> GoldenBaseline:
    raise_not_implemented(f"set golden baseline for skill {skill_id}")


@router.delete(
    "/{golden_id}",
    response_model=ErrorResponse,
    responses={501: {"model": ErrorResponse}},
)
async def delete_golden_baseline(skill_id: str, golden_id: str) -> ErrorResponse:
    raise_not_implemented(f"delete golden baseline {golden_id} for skill {skill_id}")
