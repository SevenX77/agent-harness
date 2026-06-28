"""Golden baseline endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Header, Response, status

from app.core.exceptions import error_response, raise_error_response
from app.models.errors import ErrorResponse
from app.models.golden import (
    GoldenBaseline,
    GoldenBaselineContent,
    GoldenBaselinePlan,
    GoldenTemplate,
    SetGoldenReq,
    SetManualGoldenReq,
)
from app.services.golden_diff import (
    delete_golden_baseline_for_skill,
    list_golden_baselines_for_skill,
    plan_golden_baseline_for_run,
    plan_manual_golden_for_node,
    read_golden_baseline_content,
    set_golden_baseline_for_run,
)
from app.services.golden_template import generate_golden_template

router = APIRouter(prefix="/api/skills/{skill_id}/golden", tags=["golden"])


@router.get(
    "",
    response_model=list[GoldenBaseline],
    responses={501: {"model": ErrorResponse}},
)
async def list_golden_baselines(skill_id: str) -> list[GoldenBaseline]:
    return list_golden_baselines_for_skill(skill_id)


@router.get(
    "/{golden_id}/content",
    response_model=GoldenBaselineContent,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def read_golden_content(
    skill_id: str,
    golden_id: str,
    node_id: str | None = None,
) -> GoldenBaselineContent:
    # N4 atom #29 read path (read-only, no write guard): resolve each persisted case's
    # expected_output_ref to its stored content so the I/O panel can open a golden file
    # for editing. With ?node_id= only that node's case is returned.
    return read_golden_baseline_content(skill_id, golden_id, node_id=node_id)


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
    return set_golden_baseline_for_run(
        skill_id,
        request.run_id,
        lock=request.lock,
        node_id=request.node_id,
    )


@router.post(
    "/plan",
    response_model=GoldenBaselinePlan,
    responses={501: {"model": ErrorResponse}},
)
async def plan_golden_baseline(skill_id: str, request: SetGoldenReq) -> GoldenBaselinePlan:
    return plan_golden_baseline_for_run(
        skill_id,
        request.run_id,
        lock=request.lock,
        node_id=request.node_id,
    )


@router.get(
    "/template",
    response_model=GoldenTemplate,
    responses={422: {"model": ErrorResponse}},
)
async def get_golden_template(skill_id: str, node_id: str) -> GoldenTemplate:
    # N4 atom #33 create-path B: empty schema-valid template for an agent node so the
    # author can hand-fill expected values without a copilot/run source.
    return generate_golden_template(skill_id, node_id)


@router.post(
    "/manual/plan",
    response_model=GoldenBaselinePlan,
    responses={422: {"model": ErrorResponse}},
)
async def plan_manual_golden(skill_id: str, request: SetManualGoldenReq) -> GoldenBaselinePlan:
    # N4 atom #33 manual write (D12 Rust sole writer): return the file plan
    # (baseline/report/cases) the Rust native-fs writer writes per file. Plan-only,
    # so it carries no write guard — mirrors the run-promote /golden/plan endpoint.
    # There is no Python HTTP disk-write endpoint for the manual golden: the frontend
    # always writes via Rust (web degrades to Desktop-only, no persist).
    return plan_manual_golden_for_node(skill_id, request.node_id, request.expected_output)


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
