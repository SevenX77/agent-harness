"""Studio LLM configuration API endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.core import config
from app.models.llm_config import LLMCredentialsFile, ProviderCredential, RoleEntry, RolesData
from app.services.copilot_test import (
    _NetworkError,
    _QuotaExceeded,
    _RateLimited,
    _Unauthorized,
)
from app.services.llm_credentials import load_credentials, redacted_for_response, save_credentials
from app.services.llm_env import patch_environment_from_credentials
from app.services.llm_provider_test import DEFAULT_BASE_URLS, ProviderType, ping_provider
from app.services.llm_roles import (
    InvalidRoleReference,
    get_role,
    load_roles_file,
    save_roles_file,
    validate_references,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])
logger = logging.getLogger(__name__)
ROLES_PATH = config.REPO_ROOT / "config" / "llm_roles.yaml"


class ProviderCredentialWrite(BaseModel):
    """Partial LLM provider credential update."""

    model_config = ConfigDict(extra="forbid")

    provider_code: str
    api_key: str = ""
    base_url: str | None = None


class CredentialsWriteRequest(BaseModel):
    """Request body for replacing the local LLM credentials file."""

    model_config = ConfigDict(extra="forbid")

    providers: list[ProviderCredentialWrite]


class ProviderTestRequest(BaseModel):
    """Request body for one-off provider connectivity checks."""

    model_config = ConfigDict(extra="forbid")

    provider_code: str
    provider_type: ProviderType
    api_key: str
    base_url: str | None = None
    model_id: str | None = None


class ProviderTestResponse(BaseModel):
    """Sanitized provider test response."""

    status: str
    latency_ms: int | None = None
    model_seen: str | None = None
    message: str | None = None


@router.get("/credentials")
async def get_llm_credentials(include_metadata: bool = False) -> dict[str, Any]:
    """Return sanitized LLM credential state."""

    return redacted_for_response(
        load_credentials(),
        _provider_metadata() if include_metadata else None,
    )


@router.put("/credentials")
async def put_llm_credentials(
    request: CredentialsWriteRequest,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """Replace local LLM credentials and patch runtime env."""

    existing = {provider.provider_code: provider for provider in load_credentials().providers}
    for provider in request.providers:
        current = existing.get(provider.provider_code)
        base_url = provider.base_url
        if base_url is None:
            base_url = current.base_url if current else ""
        existing[provider.provider_code] = ProviderCredential(
            provider_code=provider.provider_code,
            api_key=provider.api_key,
            base_url=base_url,
        )
    data = LLMCredentialsFile(providers=list(existing.values()))
    save_credentials(data)
    patch_environment_from_credentials(data)
    return redacted_for_response(data, _provider_metadata() if include_metadata else None)


@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_llm_provider(request: ProviderTestRequest) -> ProviderTestResponse:
    """Use candidate credentials to test provider connectivity without persisting them."""

    started = asyncio.get_running_loop().time()
    base_url = request.base_url or DEFAULT_BASE_URLS[request.provider_type]
    try:
        async with asyncio.timeout(8):
            result = await ping_provider(
                request.provider_code,
                request.provider_type,
                request.api_key,
                base_url,
            )
        _log_test_provider(request.provider_code, request.api_key, "ok", result.latency_ms)
        return ProviderTestResponse(
            status="ok",
            latency_ms=result.latency_ms,
            model_seen=result.model_seen,
        )
    except TimeoutError:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.provider_code, request.api_key, "timeout", latency_ms)
        return ProviderTestResponse(status="timeout", message="Request exceeded 8s")
    except _Unauthorized:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.provider_code, request.api_key, "invalid_key", latency_ms)
        return ProviderTestResponse(status="invalid_key", message="Provider rejected key (401)")
    except _RateLimited:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.provider_code, request.api_key, "rate_limited", latency_ms)
        return ProviderTestResponse(status="rate_limited", message="Rate limit (429)")
    except _QuotaExceeded:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.provider_code, request.api_key, "quota_exceeded", latency_ms)
        return ProviderTestResponse(status="quota_exceeded", message="Quota exceeded")
    except _NetworkError as exc:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.provider_code, request.api_key, "network_error", latency_ms)
        return ProviderTestResponse(status="network_error", message=str(exc)[:200])


@router.get("/roles", response_model=RolesData)
async def get_llm_roles() -> RolesData:
    """Return the full LLM roles configuration."""

    return load_roles_file(ROLES_PATH)


@router.get("/roles/{role_name}", response_model=RoleEntry)
async def get_llm_role(role_name: str) -> RoleEntry:
    """Return one LLM role configuration."""

    data = load_roles_file(ROLES_PATH)
    try:
        return get_role(data, role_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown LLM role: {role_name}") from exc


@router.put("/roles", response_model=RolesData)
async def put_llm_roles(request: RolesData) -> RolesData:
    """Replace the editable LLM roles tree after reference validation."""

    try:
        validate_references(request)
        save_roles_file(ROLES_PATH, request)
        saved = load_roles_file(ROLES_PATH)
        validate_references(saved)
        return saved
    except InvalidRoleReference as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _elapsed_ms(started: float) -> int:
    return max(0, round((asyncio.get_running_loop().time() - started) * 1000))


def _log_test_provider(
    provider_code: str,
    api_key: str,
    status: str,
    latency_ms: int,
) -> None:
    last4 = api_key[-4:] if api_key else ""
    logger.info(
        "test_llm_provider provider_code=%s last4=%s status=%s latency_ms=%d",
        provider_code,
        last4,
        status,
        latency_ms,
    )


def _provider_metadata() -> dict[str, dict[str, Any]]:
    data = load_roles_file(ROLES_PATH)
    return {
        provider_code: {
            "name": provider.name,
            "provider_type": provider.type,
            "base_url": provider.llm_base_url or provider.base_url or "",
        }
        for provider_code, provider in data.providers.items()
    }


__all__ = ["router"]
