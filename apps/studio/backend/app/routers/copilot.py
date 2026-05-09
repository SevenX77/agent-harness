"""Studio Copilot V1 API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.exceptions import error_response, raise_error_response, raise_not_implemented
from app.models.copilot import (
    BackendStatus,
    ContextUpdateRequest,
    ContextUpdateResponse,
    CopilotBackend,
    CredentialsReadResponse,
    CredentialsWriteRequest,
)
from app.models.errors import ErrorResponse
from app.services.copilot import get_view_context, reset_session, set_view_context
from app.services.copilot_credentials import (
    BackendCredentials,
    CredentialsData,
    read_credentials,
    write_credentials,
)

router = APIRouter(tags=["copilot"])

_ACTIVE_BACKENDS: set[CopilotBackend] = {"claude", "deepseek"}


@router.post(
    "/api/skills/{skill_id}/copilot/dispatch",
    responses={501: {"model": ErrorResponse}},
)
async def dispatch_copilot(skill_id: str, request: dict[str, Any]) -> None:
    """Preserve the existing Copilot dispatch scaffold until T2.6 wires SDK events."""

    del request
    raise_not_implemented(f"dispatch copilot for skill {skill_id}")


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
    data.backends[request.backend] = BackendCredentials(
        api_key=api_key,
        v1_5_placeholder=current.v1_5_placeholder,
    )
    if request.set_active:
        data.active_backend = request.backend

    write_credentials(data)
    await reset_session(None, request.backend)
    return _to_read_response(data)


def _to_read_response(data: CredentialsData) -> CredentialsReadResponse:
    return CredentialsReadResponse(
        backends={
            backend: BackendStatus(
                has_key=bool(credentials.api_key),
                v1_5_placeholder=credentials.v1_5_placeholder,
            )
            for backend, credentials in data.backends.items()
        },
        active_backend=data.active_backend,
    )
