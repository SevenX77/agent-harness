"""Golden baseline endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import raise_not_implemented, standard_http_exception
from app.models.errors import ErrorResponse
from app.models.golden import GoldenBaseline, SetGoldenReq
from app.services.golden_diff import (
    list_golden_baselines_for_skill,
    set_golden_baseline_for_manual_node,
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
    if request.run_id is not None:
        raise standard_http_exception(
            "WHOLE_RUN_GOLDEN_PROMOTION_NOT_ALLOWED",
            "Whole-run golden promotion is not allowed in MVP1."
        )
    if request.source == "predict":
        raise standard_http_exception(
            "PREDICT_TRACE_CANNOT_BE_GOLDEN",
            "Predict source cannot be saved as Golden baselines."
        )
    return set_golden_baseline_for_manual_node(
        skill_id=skill_id,
        node_id=request.node_id,
        expected_output=request.expected_output,
        source=request.source,
        lock=request.lock,
    )


@router.delete(
    "/{golden_id}",
    response_model=ErrorResponse,
    responses={501: {"model": ErrorResponse}},
)
async def delete_golden_baseline(skill_id: str, golden_id: str) -> ErrorResponse:
    raise_not_implemented(f"delete golden baseline {golden_id} for skill {skill_id}")
