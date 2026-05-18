"""Studio LLM configuration API endpoints."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core import config
from app.models.llm_config import (
    LLMCredentialsFile,
    ModelInfo,
    ProviderCredential,
    ProviderType,
    RoleEntry,
    RolesData,
)
from app.services.copilot_test import (
    _NetworkError,
    _QuotaExceeded,
    _RateLimited,
    _Unauthorized,
)
from app.services.llm_capability_table import (
    STATIC_FALLBACK_MODELS,
    lookup_capabilities,
)
from app.services.llm_credentials import (
    _credentials_lock,
    _persist_test_outcome,
    _save_credentials_unlocked,
    credentials_path,
    load_credentials,
    redacted_for_response,
)
from app.services.llm_provider_test import (
    DEFAULT_BASE_URLS,
    PingResultExtended,
    ping_provider_extended,
)
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
    """Editable subset of ``ProviderCredential`` accepted via PUT.

    Only user-owned provider fields below can be written by the client. The five Test
    outcome fields (``last_test_status``/``last_test_at``/``last_test_message``/
    ``last_error_code``/``available_models``) are *single-writer* — they are
    written exclusively by the POST ``/providers/test`` flow via
    ``_persist_test_outcome``. Including any of them in PUT is rejected by
    ``extra="forbid"``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    api_key: str = ""
    base_url: str = ""
    provider_type: ProviderType | None = None


class CredentialsWriteRequest(BaseModel):
    """Request body for replacing the local LLM credentials file."""

    model_config = ConfigDict(extra="forbid")

    providers: list[ProviderCredentialWrite] = Field(default_factory=list)


class ProviderTestRequest(BaseModel):
    """Request body for one-off provider connectivity checks."""

    model_config = ConfigDict(extra="forbid")

    id: str
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
    error_code: str | None = None
    available_models: list[ModelInfo] = Field(default_factory=list)


@router.get("/credentials")
async def get_llm_credentials(include_metadata: bool = False) -> dict[str, Any]:
    """Return sanitized LLM credential state."""

    del include_metadata
    return redacted_for_response(load_credentials())


@router.put("/credentials")
async def put_llm_credentials(
    request: CredentialsWriteRequest,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """Full-replace local LLM credentials and patch runtime env.

    Semantics (departing from the prior incremental upsert):

    * The provider list is replaced wholesale by the request — any provider
      whose ``id`` is absent from the body is **deleted**.
    * Existing Test outcome fields are preserved per id (single-write
      rule). The 6 editable fields come from the request body.
    * If ``api_key`` in the body is an empty string, the previously saved key
      for that ``id`` is preserved (so the UI can omit the value
      when the user is only editing other fields).
    """

    del include_metadata
    path = credentials_path()
    with _credentials_lock:
        existing_by_code = {
            provider.id: provider for provider in load_credentials(path).providers
        }
        next_providers: list[ProviderCredential] = []
        for incoming in request.providers:
            current = existing_by_code.get(incoming.id)
            api_key = incoming.api_key
            if api_key == "" and current is not None and current.api_key:
                api_key = current.api_key
            base_url = incoming.base_url
            if current is not None:
                next_providers.append(
                    current.model_copy(
                        update={
                            "api_key": api_key,
                            "base_url": base_url,
                            "name": incoming.name,
                            "provider_type": incoming.provider_type,
                        }
                    )
                )
            else:
                next_providers.append(
                    ProviderCredential(
                        id=incoming.id,
                        name=incoming.name,
                        api_key=api_key,
                        base_url=base_url,
                        provider_type=incoming.provider_type,
                    )
                )
        data = LLMCredentialsFile(providers=next_providers)
        _save_credentials_unlocked(data, path)
    return redacted_for_response(data)


@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_llm_provider(request: ProviderTestRequest) -> ProviderTestResponse:
    """Use candidate credentials to test provider connectivity.

    The 5 Test outcome fields on the matching ``ProviderCredential`` are
    atomically patched via ``_persist_test_outcome`` (which shares the
    credentials lock with the PUT path, so concurrent edits do not lose
    Test writeback). Other fields are untouched.
    """

    if not request.api_key:
        # `missing_api_key` is a synthetic short-circuit code — it's never an
        # actual test outcome, so don't persist it as `last_test_status` (which
        # is constrained to TestStatus literals and would 422 on next GET).
        # The response still surfaces it for the toast; storage keeps
        # last_test_status="untested" and only records the synthetic error_code.
        return ProviderTestResponse(
            status="missing_api_key",
            message="API key is empty.",
            error_code="missing_api_key",
        )

    started = asyncio.get_running_loop().time()
    base_url = request.base_url or DEFAULT_BASE_URLS[request.provider_type]
    try:
        async with asyncio.timeout(8):
            result = await ping_provider_extended(
                request.id,
                request.provider_type,
                request.api_key,
                base_url,
            )
    except TimeoutError:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.api_key, "timeout", latency_ms)
        return _record_and_return(
            request.id,
            ProviderTestResponse(
                status="timeout",
                latency_ms=latency_ms,
                message="Request exceeded 8s",
                error_code="timeout",
            ),
            _now_iso(),
        )
    except _Unauthorized as exc:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.api_key, "invalid_key", latency_ms)
        return _record_and_return(
            request.id,
            ProviderTestResponse(
                status="invalid_key",
                latency_ms=latency_ms,
                message="Provider rejected key (401)",
                error_code=getattr(exc, "error_code", "unauthorized") or "unauthorized",
            ),
            _now_iso(),
        )
    except _RateLimited as exc:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.api_key, "rate_limited", latency_ms)
        return _record_and_return(
            request.id,
            ProviderTestResponse(
                status="rate_limited",
                latency_ms=latency_ms,
                message="Rate limit (429)",
                error_code=getattr(exc, "error_code", "rate_limited") or "rate_limited",
            ),
            _now_iso(),
        )
    except _QuotaExceeded as exc:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.api_key, "quota_exceeded", latency_ms)
        return _record_and_return(
            request.id,
            ProviderTestResponse(
                status="quota_exceeded",
                latency_ms=latency_ms,
                message="Quota exceeded",
                error_code=getattr(exc, "error_code", "quota_exceeded") or "quota_exceeded",
            ),
            _now_iso(),
        )
    except _NetworkError as exc:
        latency_ms = _elapsed_ms(started)
        _log_test_provider(request.id, request.api_key, "network_error", latency_ms)
        return _record_and_return(
            request.id,
            ProviderTestResponse(
                status="network_error",
                latency_ms=latency_ms,
                message=str(exc)[:200],
                error_code=getattr(exc, "error_code", "network_error") or "network_error",
            ),
            _now_iso(),
        )

    _log_test_provider(request.id, request.api_key, "ok", result.latency_ms)
    available_models = _models_from_ping(result, request.provider_type)
    return _record_and_return(
        request.id,
        ProviderTestResponse(
            status="ok",
            latency_ms=result.latency_ms,
            model_seen=result.model_seen,
            available_models=available_models,
        ),
        _now_iso(),
    )


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


def _models_from_ping(
    result: PingResultExtended,
    provider_type: ProviderType,
) -> list[ModelInfo]:
    if result.model_ids:
        return [
            ModelInfo(id=model_id, capabilities=lookup_capabilities(provider_type, model_id))
            for model_id in result.model_ids
        ]
    return [
        ModelInfo(id=model_id, capabilities=lookup_capabilities(provider_type, model_id))
        for model_id in STATIC_FALLBACK_MODELS.get(provider_type, ())
    ]


def _record_and_return(
    provider_id: str,
    response: ProviderTestResponse,
    outcome_at: str,
) -> ProviderTestResponse:
    """Write the Test outcome back to credentials (best-effort) and return the response."""

    try:
        _persist_test_outcome(
            provider_id,
            last_test_status=response.status,  # type: ignore[arg-type]
            last_test_at=outcome_at,
            last_test_message=response.message or "",
            last_error_code=response.error_code or "",
            available_models=list(response.available_models),
        )
    except Exception as exc:  # noqa: BLE001 — Test writeback failure must not break the API response.
        logger.warning(
            "test_llm_provider writeback failed provider_id=%s error=%s",
            provider_id,
            exc,
        )
    return response


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _elapsed_ms(started: float) -> int:
    return max(0, round((asyncio.get_running_loop().time() - started) * 1000))


def _log_test_provider(
    provider_id: str,
    api_key: str,
    status: str,
    latency_ms: int,
) -> None:
    last4 = api_key[-4:] if api_key else ""
    logger.info(
        "test_llm_provider provider_id=%s last4=%s status=%s latency_ms=%d",
        provider_id,
        last4,
        status,
        latency_ms,
    )


__all__ = ["router"]
