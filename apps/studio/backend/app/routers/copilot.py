"""Studio Copilot V1 API endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.exceptions import error_response, raise_error_response, raise_not_implemented
from app.models.copilot import (
    BackendStatus,
    ContextUpdateRequest,
    ContextUpdateResponse,
    CopilotBackend,
    CopilotEventError,
    CredentialsReadResponse,
    CredentialsWriteRequest,
    TestCredentialsRequest,
    TestCredentialsResponse,
)
from app.models.errors import ErrorResponse
from app.services.copilot import get_view_context, reset_session, set_view_context, stream_query
from app.services.copilot_credentials import (
    BackendCredentials,
    CredentialsData,
    read_credentials,
    write_credentials,
)
from app.services.copilot_test import (
    DEFAULT_BASE_URLS,
    _NetworkError,
    _ping_provider,
    _QuotaExceeded,
    _RateLimited,
    _Unauthorized,
)

router = APIRouter(tags=["copilot"])
logger = logging.getLogger(__name__)

_ACTIVE_BACKENDS: set[CopilotBackend] = {"claude", "deepseek"}
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
    credentials = read_credentials()
    backend = credentials.active_backend
    api_key = credentials.backends[backend].api_key

    if backend not in _ACTIVE_BACKENDS:
        await websocket.send_json(
            CopilotEventError(message=f"V1.5 backend ({backend}) 暂不可用").model_dump()
        )
        await websocket.close(code=_POLICY_CLOSE_CODE)
        return

    if not api_key:
        await websocket.send_json(
            CopilotEventError(message=f"未配置 {backend} 的 API key").model_dump()
        )
        await websocket.close(code=_POLICY_CLOSE_CODE)
        return

    try:
        while True:
            payload = await websocket.receive_json()
            user_message = payload["user_message"]
            async for event in stream_query(skill_id, backend, api_key, user_message):
                await websocket.send_json(event.model_dump())
    except WebSocketDisconnect:
        await reset_session(skill_id=skill_id, backend=backend)


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


@router.get(
    "/api/copilot/credentials",
    response_model=CredentialsReadResponse,
)
async def get_copilot_credentials() -> CredentialsReadResponse:
    """Return sanitized Copilot credential state."""

    return _to_read_response(read_credentials())


@router.post(
    "/api/copilot/credentials/test",
    response_model=TestCredentialsResponse,
)
async def test_copilot_credentials(
    request: TestCredentialsRequest,
) -> TestCredentialsResponse:
    """Use candidate credentials to test provider connectivity without persisting them."""

    started = asyncio.get_running_loop().time()
    base_url = request.base_url or DEFAULT_BASE_URLS[request.backend]
    try:
        async with asyncio.timeout(8):
            result = await _ping_provider(request.backend, request.api_key, base_url)
        _log_test_credentials(request.backend, request.api_key, "ok", result.latency_ms)
        return TestCredentialsResponse(
            status="ok",
            latency_ms=result.latency_ms,
            model_seen=result.model_seen,
        )
    except TimeoutError:
        latency_ms = _elapsed_ms(started)
        _log_test_credentials(request.backend, request.api_key, "timeout", latency_ms)
        return TestCredentialsResponse(status="timeout", message="Request exceeded 8s")
    except _Unauthorized:
        latency_ms = _elapsed_ms(started)
        _log_test_credentials(request.backend, request.api_key, "invalid_key", latency_ms)
        return TestCredentialsResponse(
            status="invalid_key",
            message="Provider rejected key (401)",
        )
    except _RateLimited:
        latency_ms = _elapsed_ms(started)
        _log_test_credentials(request.backend, request.api_key, "rate_limited", latency_ms)
        return TestCredentialsResponse(status="rate_limited", message="Rate limit (429)")
    except _QuotaExceeded:
        latency_ms = _elapsed_ms(started)
        _log_test_credentials(request.backend, request.api_key, "quota_exceeded", latency_ms)
        return TestCredentialsResponse(status="quota_exceeded", message="Quota exceeded")
    except _NetworkError as exc:
        latency_ms = _elapsed_ms(started)
        _log_test_credentials(request.backend, request.api_key, "network_error", latency_ms)
        return TestCredentialsResponse(status="network_error", message=str(exc)[:200])


@router.put(
    "/api/copilot/credentials",
    response_model=CredentialsReadResponse,
    responses={400: {"model": ErrorResponse}},
)
async def put_copilot_credentials(request: CredentialsWriteRequest) -> CredentialsReadResponse:
    """Update one backend credential and optionally switch the active backend."""

    data = read_credentials()
    if request.set_active and request.backend not in _ACTIVE_BACKENDS:
        raise_error_response(
            error_response(
                error_code="COPILOT_BACKEND_DISABLED",
                http_status=400,
                message=f"Backend '{request.backend}' is reserved for V1.5",
                details={"backend": request.backend},
                retry_strategy="not_retryable",
            )
        )

    current = data.backends[request.backend]
    api_key = current.api_key if request.api_key is None else request.api_key
    base_url = current.base_url if request.base_url is None else request.base_url
    data.backends[request.backend] = BackendCredentials(
        api_key=api_key,
        base_url=base_url,
    )
    if request.set_active:
        data.active_backend = request.backend

    write_credentials(data)
    await reset_session(None, request.backend)
    return _to_read_response(data)


def _elapsed_ms(started: float) -> int:
    return max(0, round((asyncio.get_running_loop().time() - started) * 1000))


def _log_test_credentials(
    backend: CopilotBackend,
    api_key: str,
    status: str,
    latency_ms: int,
) -> None:
    last4 = api_key[-4:] if api_key else ""
    logger.info(
        "test_credentials backend=%s last4=%s status=%s latency_ms=%d",
        backend,
        last4,
        status,
        latency_ms,
    )


def _to_read_response(data: CredentialsData) -> CredentialsReadResponse:
    return CredentialsReadResponse(
        backends={
            backend: BackendStatus(
                has_key=bool(credentials.api_key),
                last4=credentials.api_key[-4:] if credentials.api_key else None,
                base_url=credentials.base_url,
            )
            for backend, credentials in data.backends.items()
        },
        active_backend=data.active_backend,
    )
