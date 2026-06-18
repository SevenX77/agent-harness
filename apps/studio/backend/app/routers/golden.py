"""Golden baseline endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Header, Response, status

from app.core.exceptions import error_response, raise_error_response
from app.models.errors import ErrorResponse
from app.models.golden import GoldenBaseline, GoldenBaselinePlan, SetGoldenReq
from app.services.golden_diff import (
    delete_golden_baseline_for_skill,
    list_golden_baselines_for_skill,
    plan_golden_baseline_for_run,
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
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
async def set_golden_baseline(
    skill_id: str,
    request: SetGoldenReq,
    write_fallback: str | None = Header(default=None, alias="X-Studio-Write-Fallback"),
) -> GoldenBaseline:
    _require_browser_write_fallback(write_fallback)
    return set_golden_baseline_for_run(skill_id, request.run_id, lock=request.lock)


@router.post(
    "/plan",
    response_model=GoldenBaselinePlan,
    responses={501: {"model": ErrorResponse}},
)
async def plan_golden_baseline(skill_id: str, request: SetGoldenReq) -> GoldenBaselinePlan:
    return plan_golden_baseline_for_run(skill_id, request.run_id, lock=request.lock)


@router.delete(
    "/{golden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def delete_golden_baseline(
    skill_id: str,
    golden_id: str,
    write_fallback: str | None = Header(default=None, alias="X-Studio-Write-Fallback"),
) -> Response:
    _require_browser_write_fallback(write_fallback)
    delete_golden_baseline_for_skill(skill_id, golden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _require_browser_write_fallback(write_fallback: str | None) -> None:
    if write_fallback is not None and write_fallback.strip().lower() == "browser":
        return
    raise_error_response(
        error_response(
            error_code="NATIVE_FS_REQUIRED",
            http_status=409,
            message="Mutating workspace writes require native-fs unless browser fallback is explicit",
            details={
                "required_header": "X-Studio-Write-Fallback",
                "required_value": "browser",
            },
            retry_strategy="not_retryable",
        )
    )
