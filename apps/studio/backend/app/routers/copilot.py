"""Studio Copilot V1 API endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.exceptions import raise_not_implemented
from app.models.copilot import (
    ContextUpdateRequest,
    ContextUpdateResponse,
    CopilotCredentials,
    CopilotBackend,
    CopilotEventError,
    ProviderConfig,
    TestProviderRequest,
    TestProviderResponse,
)
from app.models.errors import ErrorResponse
from app.services.copilot import get_view_context, reset_session, set_view_context, stream_query
from app.services.copilot_credentials import (
    read_credentials,
    write_credentials,
)
from app.services.copilot_test import (
    _NetworkError,
    _QuotaExceeded,
    _RateLimited,
    _Unauthorized,
    make_client,
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
    provider = _active_provider(credentials)
    if provider is None:
        await websocket.send_json(
            CopilotEventError(message=f"未找到 active provider: {credentials.active_provider_id}").model_dump()
        )
        await websocket.close(code=_POLICY_CLOSE_CODE)
        return

    backend = _provider_runtime_backend(provider)
    api_key = provider.api_key

    if backend is None or backend not in _ACTIVE_BACKENDS:
        await websocket.send_json(
            CopilotEventError(message=f"Provider ({provider.name}) 暂不可用").model_dump()
        )
        await websocket.close(code=_POLICY_CLOSE_CODE)
        return

    if not api_key:
        await websocket.send_json(
            CopilotEventError(message=f"未配置 {provider.name} 的 API key").model_dump()
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
    response_model=CopilotCredentials,
)
async def get_copilot_credentials() -> CopilotCredentials:
    """Return Copilot provider credentials, including plaintext API keys."""

    return read_credentials()


@router.post(
    "/api/copilot/providers/test",
    response_model=TestProviderResponse,
)
async def test_copilot_provider(
    request: TestProviderRequest,
) -> TestProviderResponse:
    """Use candidate credentials to test provider connectivity without persisting them."""

    started = asyncio.get_running_loop().time()
    client = make_client(request.kind, request.api_key, request.base_url)
    try:
        async with asyncio.timeout(8):
            await client.ping()
            models = await client.get_models()
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.kind, "ok", latency_ms)
        return TestProviderResponse(
            status="ok",
            latency_ms=latency_ms,
            models=models,
        )
    except TimeoutError:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.kind, "timeout", latency_ms)
        return TestProviderResponse(status="timeout", message="Request exceeded 8s")
    except _Unauthorized:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.kind, "invalid_key", latency_ms)
        return TestProviderResponse(
            status="invalid_key",
            message="Provider rejected key (401)",
        )
    except _RateLimited:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.kind, "rate_limited", latency_ms)
        return TestProviderResponse(status="rate_limited", message="Rate limit (429)")
    except _QuotaExceeded:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.kind, "quota_exceeded", latency_ms)
        return TestProviderResponse(status="quota_exceeded", message="Quota exceeded")
    except _NetworkError as exc:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.kind, "network_error", latency_ms)
        return TestProviderResponse(status="network_error", message=str(exc)[:200])


@router.put(
    "/api/copilot/credentials",
    response_model=CopilotCredentials,
)
async def put_copilot_credentials(request: CopilotCredentials) -> CopilotCredentials:
    """Replace the complete Copilot provider credential config."""

    write_credentials(request)
    await reset_session(None, None)
    return request


def _elapsed_ms(started: float) -> int:
    return max(0, round((asyncio.get_running_loop().time() - started) * 1000))


def _log_test_provider(
    provider_id: str,
    kind: str,
    status: str,
    latency_ms: int,
) -> None:
    logger.info(
        "test_provider provider_id=%s kind=%s status=%s latency_ms=%d",
        provider_id,
        kind,
        status,
        latency_ms,
    )


def _active_provider(data: CopilotCredentials) -> ProviderConfig | None:
    for provider in data.providers:
        if provider.id == data.active_provider_id:
            return provider
    return None


def _provider_runtime_backend(provider: ProviderConfig) -> CopilotBackend | None:
    if provider.id == "default-deepseek":
        return "deepseek"
    if provider.kind == "anthropic":
        return "claude"
    return None
