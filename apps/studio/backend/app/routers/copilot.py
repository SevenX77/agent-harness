"""Studio Copilot V1 API endpoints."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from app.core.exceptions import error_response, raise_error_response
from app.models.copilot import (
    BackendStatus,
    CopilotBackend,
    CredentialsReadResponse,
    CredentialsWriteRequest,
)
from app.models.errors import ErrorResponse
from app.services.copilot_credentials import (
    BackendCredentials,
    CredentialsData,
    read_credentials,
    write_credentials,
)

router = APIRouter(tags=["copilot"])

_ACTIVE_BACKENDS: set[CopilotBackend] = {"claude", "deepseek"}


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
    _reset_copilot_sessions(request.backend)
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


def _reset_copilot_sessions(backend: CopilotBackend) -> None:
    """Call T2.3 reset hook when it exists."""

    # TODO(T2.3): replace this optional hook with the concrete session manager API.
    try:
        copilot_service = importlib.import_module("app.services.copilot")
    except ImportError:
        return

    reset_session = getattr(copilot_service, "reset_session", None)
    if not callable(reset_session):
        return

    reset: Callable[[Any, CopilotBackend], None] = reset_session
    # T2.3 will own reset_session; None means all skills for this backend.
    reset(None, backend)
