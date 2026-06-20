"""Studio Copilot API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.exceptions import raise_not_implemented
from app.models.copilot import (
    ContextUpdateRequest,
    ContextUpdateResponse,
    CopilotBashApprovalRequest,
    CopilotBashApprovalResponse,
    CopilotWsRequestPayload,
)
from app.models.errors import ErrorResponse
from app.models.golden import CopilotJudgeRequest, CopilotJudgeResponse
from app.services.copilot import (
    get_view_context,
    reset_session,
    resolve_bash_approval,
    set_view_context,
    stream_query,
)
from app.services.copilot_judge_adapter import CopilotJudgeAdapter, raise_missing_judge_ref

router = APIRouter(tags=["copilot"])

_POLICY_CLOSE_CODE = status.WS_1008_POLICY_VIOLATION


@router.post(
    "/api/copilot/roles/{role_name}/test-sdk",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def test_copilot_sdk_role(role_name: str) -> Any:
    """HTTP shell for the Studio-only Copilot SDK test path."""

    from app.routers.llm import _start_copilot_sdk_test_job

    return await _start_copilot_sdk_test_job(role_name)


@router.post(
    "/api/skills/{skill_id}/copilot/dispatch",
    responses={501: {"model": ErrorResponse}},
)
async def dispatch_copilot(skill_id: str, request: dict[str, Any]) -> None:
    """Preserve the existing Copilot dispatch scaffold until T2.6 wires SDK events."""

    del request
    raise_not_implemented(f"dispatch copilot for skill {skill_id}")


@router.post(
    "/api/skills/{skill_id}/copilot/judge",
    response_model=CopilotJudgeResponse,
    responses={422: {"model": ErrorResponse}},
)
async def prepare_copilot_judge_context(
    skill_id: str,
    request: CopilotJudgeRequest,
) -> CopilotJudgeResponse:
    """Prepare golden compare refs for Copilot Judge without starting a stream."""

    run_results_ref = request.run_results_ref
    if not run_results_ref:
        raise_missing_judge_ref("run_results_ref", skill_id)
    if not request.baseline_ref and not request.against:
        raise_missing_judge_ref("baseline_ref", skill_id)
    return CopilotJudgeAdapter().prepare(
        skill_id,
        run_results_ref=run_results_ref,
        baseline_ref=request.baseline_ref,
        against=request.against,
    )


@router.post(
    "/api/skills/{skill_id}/copilot/bash-approval",
    response_model=CopilotBashApprovalResponse,
)
async def post_copilot_bash_approval(
    skill_id: str,
    request: CopilotBashApprovalRequest,
) -> CopilotBashApprovalResponse:
    """Resolve a Bash command held by Copilot safe-write."""

    result = await resolve_bash_approval(
        skill_id,
        request.tool_use_id,
        approve=request.approve,
    )
    return CopilotBashApprovalResponse(
        tool_use_id=result.tool_use_id,
        approved=result.approved,
        executed=result.executed,
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
        message=result.message,
    )


@router.websocket("/api/skills/{skill_id}/copilot/ws")
async def copilot_ws(websocket: WebSocket, skill_id: str) -> None:
    """Stream Copilot events for user messages over one persistent connection."""

    from app.main import _is_valid_token

    if not _is_valid_token(websocket.query_params.get("token")):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()
    try:
        while True:
            payload = CopilotWsRequestPayload.model_validate(await websocket.receive_json())
            async for event in stream_query(
                skill_id=skill_id,
                user_message=payload.user_message,
                model_override=payload.model_override,
                role=payload.role,
                workspace_root=payload.workspace_root,
                judge_context=payload.judge_context,
            ):
                await websocket.send_json(event.model_dump(exclude_none=True))
    except WebSocketDisconnect:
        await reset_session(skill_id=skill_id, model_code=None)


@router.post(
    "/api/skills/{skill_id}/copilot/context",
    response_model=ContextUpdateResponse,
)
async def post_copilot_context(
    skill_id: str,
    request: ContextUpdateRequest,
) -> ContextUpdateResponse:
    """Update the cached Studio view context without starting an LLM query."""

    accepted = await set_view_context(
        skill_id=skill_id,
        view=request.view,
        context=request.context,
        timestamp_ms=request.timestamp,
    )
    if accepted:
        return ContextUpdateResponse(
            accepted=True,
            summary=f"{request.view} at {request.timestamp}",
        )

    cached = get_view_context(skill_id)
    summary = f"{cached.view} at {cached.timestamp_ms}" if cached is not None else None
    return ContextUpdateResponse(
        accepted=False,
        reason="out_of_order",
        summary=summary,
    )
