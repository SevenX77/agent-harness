"""Studio Copilot API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.exceptions import raise_not_implemented
from app.models.copilot import (
    ContextUpdateRequest,
    ContextUpdateResponse,
    CopilotWsRequestPayload,
)
from app.models.errors import ErrorResponse
from app.services.copilot import get_view_context, reset_session, set_view_context, stream_query

router = APIRouter(tags=["copilot"])

_POLICY_CLOSE_CODE = status.WS_1008_POLICY_VIOLATION


@router.post(
    "/api/skills/{skill_id}/copilot/dispatch",
    responses={501: {"model": ErrorResponse}},
)
async def dispatch_copilot(skill_id: str, request: dict[str, Any]) -> None:
    """Preserve the existing Copilot dispatch scaffold until T2.6 wires SDK events."""

    del request
    raise_not_implemented(f"dispatch copilot for skill {skill_id}")


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
            ):
                await websocket.send_json(event.model_dump())
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


@router.post("/api/copilot/roles/{role_name}/test-sdk")
async def test_copilot_role_sdk(role_name: str) -> dict[str, Any]:
    """Execute a specialized Claude SDK tool-call verification test on the role's targets."""
    from fastapi import HTTPException

    from app.routers.llm import (
        _load_roles_or_empty,
        _materialize_role_for_response,
        _persist_copilot_sdk_probe_success,
        _probe_copilot_sdk_tool_call,
        _role_test_targets,
    )
    from app.services.llm_credentials import load_credentials

    data = _load_roles_or_empty()
    role = data.roles.get(role_name)
    if role is None:
        raise HTTPException(status_code=404, detail=f"Unknown LLM role: {role_name}")

    credentials = load_credentials()
    role = _materialize_role_for_response(role, credentials)
    targets = _role_test_targets(role, credentials)
    if not targets:
        raise HTTPException(status_code=400, detail=f"No active routes for role: {role_name}")

    results = []
    for target in targets:
        result = await _probe_copilot_sdk_tool_call(target.endpoint, target.route)
        if result.status == "ok":
            _persist_copilot_sdk_probe_success(target.route, target.endpoint, result)
        results.append({
            "route_id": target.route.route_id,
            "status": result.status,
            "message": result.message,
        })

    success = any(res["status"] == "ok" for res in results)
    return {
        "role_name": role_name,
        "status": "ok" if success else "failed",
        "results": results,
    }
