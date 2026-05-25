"""Studio LLM configuration API endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from services.llm_provider_meta import DOCS_DIR, load_provider_meta

from app.core import config
from app.models.llm_config import (
    TEST_OUTCOME_FIELDS,
    LLMCredentialsFile,
    ModelInfo,
    ProviderCredential,
    ProviderType,
    RoleEntry,
    RolesData,
)
from app.services.llm_credentials import (
    _credentials_lock,
    _persist_test_outcome,
    _save_credentials_unlocked,
    credentials_path,
    find_provider_test_result,
    load_credentials,
    provider_current_test_result,
    serialize_for_response,
    test_outcome_values_from_result,
    upsert_provider_test_result,
)
from app.services.llm_provider_test import (
    DEFAULT_BASE_URLS,
    _extract_model_ids_from_section,
    _extract_section_4,
    canonical_model_id_for_vendor,
    normalize_model_info_for_vendor,
    probe_available_models,
    probe_compatible_sdks,
    probe_model_id,
)
from app.services.llm_roles import (
    InvalidRoleReference,
    get_role,
    load_roles_file,
    normalize_role_drafts,
    save_roles_file,
    validate_references,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])
logger = logging.getLogger(__name__)
ROLES_PATH = config.REPO_ROOT / "config" / "llm_roles.yaml"


class ProviderCredentialWrite(BaseModel):
    """Editable subset of ``ProviderCredential`` accepted via PUT.

    Only user-owned provider fields below can be written by the client. The Test
    outcome fields (``last_test_status``/``last_test_at``/``last_test_message``/
    ``last_error_code``/``available_sdks``/``available_models``) are
    *single-writer* — they are written exclusively by the POST ``/providers/test`` flow via
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


TEST_OUTCOME_RESET_FIELD_NAMES = {
    "last_test_status",
    "last_test_at",
    "last_test_message",
    "last_error_code",
    "available_sdks",
    "available_models",
}
assert TEST_OUTCOME_RESET_FIELD_NAMES == set(TEST_OUTCOME_FIELDS)


def _provider_test_params_changed(
    current: ProviderCredential,
    incoming: ProviderCredentialWrite,
    resolved_api_key: str,
) -> bool:
    """Return true when saved Test results no longer describe incoming params."""

    return (
        current.api_key != resolved_api_key
        or current.base_url != incoming.base_url
        or (current.provider_type or None) != (incoming.provider_type or None)
    )


def _test_outcome_reset_values() -> dict[str, Any]:
    return {
        "last_test_status": "untested",
        "last_test_at": "",
        "last_test_message": "",
        "last_error_code": "",
        "available_sdks": [],
        "available_models": [],
    }


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
    available_sdks: list[str] = Field(default_factory=list)


class NotableModelsResponse(BaseModel):
    """Notable model ids parsed from provider metadata docs."""

    notable_models: list[str] = Field(default_factory=list)


class ProviderModelTestRequest(BaseModel):
    """Manual model probing request body.

    ``provider_id`` is the UUID of the credential record (``provider.id``),
    NOT the metadata file key (``provider_key`` like ``openrouter``). See
    ``.kiro/specs/studio-api-keys-redesign/round3-design.md`` §概念定义
    for the distinction.
    """

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(
        description=(
            "Credential record UUID (provider.id), distinguishes multiple "
            "credentials sharing the same provider_key."
        )
    )
    model_ids: list[str] = Field(
        default_factory=list,
        description="List of model ids to probe against the provider's API.",
    )


class ProviderModelTestResult(BaseModel):
    """One manual model probe result."""

    model_id: str
    status: str
    latency_ms: int | None = None
    message: str | None = None


class ProviderModelTestResponse(BaseModel):
    """Manual model probing response."""

    results: list[ProviderModelTestResult] = Field(default_factory=list)
    available_models: list[ModelInfo] = Field(default_factory=list)


@router.get("/credentials")
async def get_llm_credentials(include_metadata: bool = False) -> dict[str, Any]:
    """Return sanitized LLM credential state."""

    del include_metadata
    return serialize_for_response(load_credentials())


@router.put("/credentials")
async def put_llm_credentials(
    request: CredentialsWriteRequest,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """Full-replace local LLM credentials and patch runtime env.

    Semantics (departing from the prior incremental upsert):

    * The provider list is replaced wholesale by the request — any provider
      whose ``id`` is absent from the body is **deleted**.
    * Existing Test outcome fields are preserved per id only while test
      parameters still match. Editable fields come from the request body.
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
                test_results = upsert_provider_test_result(
                    list(current.test_results),
                    provider_current_test_result(current),
                )
                update: dict[str, Any] = {
                    "api_key": api_key,
                    "base_url": base_url,
                    "name": incoming.name,
                    "provider_type": incoming.provider_type,
                    "test_results": test_results,
                }
                if _provider_test_params_changed(current, incoming, api_key):
                    cached = find_provider_test_result(
                        test_results,
                        api_key=api_key,
                        base_url=base_url,
                        provider_type=incoming.provider_type,
                    )
                    update.update(
                        test_outcome_values_from_result(cached)
                        if cached is not None
                        else _test_outcome_reset_values()
                    )
                next_providers.append(current.model_copy(update=update))
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
    return serialize_for_response(data)


@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_llm_provider(request: ProviderTestRequest) -> ProviderTestResponse:
    """Use candidate credentials to test provider connectivity.

    The Test outcome fields on the matching ``ProviderCredential`` are
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

    vendor = _infer_vendor(request)
    base_url = request.base_url or _default_base_url(request.provider_type)
    started = datetime.now(tz=UTC)

    available_models: list[ModelInfo] = []
    available_sdks: list[str] = []
    model_list_ok = False
    model_error_status = "error"
    model_error_code = "model_list_unavailable"
    model_error_message = "Model listing failed."
    if _provider_has_models_endpoint(vendor):
        try:
            available_models = await probe_available_models(vendor, request.api_key, base_url)
            model_list_ok = True
        except Exception as exc:  # noqa: BLE001 - convert vendor failures to clean API results.
            logger.warning("Model list probe failed for vendor=%s: %s", vendor, exc)
            model_error_status, model_error_code, model_error_message = (
                _provider_test_error_from_exception(exc)
            )
    else:
        model_error_message = "Provider metadata does not define a model-list endpoint."

    if model_list_ok:
        available_sdks = [request.provider_type]
    else:
        try:
            available_sdks = await probe_compatible_sdks(vendor, request.api_key, base_url)
        except Exception as exc:  # noqa: BLE001 - SDK probing is non-blocking diagnostics.
            logger.warning("SDK probe failed for vendor=%s: %s", vendor, exc)
            available_sdks = []
        if available_sdks:
            try:
                available_models = await probe_available_models(vendor, request.api_key, base_url)
            except Exception as exc:  # noqa: BLE001 - auth passed; model listing remains optional.
                logger.warning("Model list fallback failed for vendor=%s: %s", vendor, exc)

    latency_ms = _elapsed_ms(started)
    status = "ok" if (model_list_ok or available_sdks) else model_error_status
    error_code = None if status == "ok" else model_error_code
    message = None if status == "ok" else model_error_message
    _log_test_provider(request.id, request.api_key, status, latency_ms)
    return _record_and_return(
        request.id,
        ProviderTestResponse(
            status=status,
            latency_ms=latency_ms,
            message=message,
            error_code=error_code,
            available_sdks=available_sdks,
            available_models=available_models,
        ),
        _now_iso(),
        expected_api_key=request.api_key,
        expected_base_url=request.base_url or "",
        expected_provider_type=request.provider_type,
    )


@router.get("/providers/notable-models", response_model=NotableModelsResponse)
async def get_provider_notable_models(provider_key: str) -> NotableModelsResponse:
    """Return notable model ids from provider metadata §4."""

    if not provider_key or not provider_key.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid provider_key")
    doc_path = DOCS_DIR / f"{provider_key}.md"
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_key}")
    content = doc_path.read_text(encoding="utf-8")
    return NotableModelsResponse(
        notable_models=_extract_model_ids_from_section(_extract_section_4(content))
    )


@router.post("/providers/test-models", response_model=ProviderModelTestResponse)
async def test_provider_models(request: ProviderModelTestRequest) -> ProviderModelTestResponse:
    """Probe user-supplied model ids and append passing models to credentials."""

    data = load_credentials()
    provider = next((item for item in data.providers if item.id == request.provider_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {request.provider_id}")
    if not provider.api_key:
        raise HTTPException(status_code=400, detail="Provider API key is empty")
    provider_type = provider.provider_type or "openai_compatible"
    base_url = provider.base_url or _default_base_url(provider_type)
    model_ids = _dedupe_model_ids(request.model_ids)
    if not model_ids:
        return ProviderModelTestResponse(
            results=[],
            available_models=list(provider.available_models),
        )

    vendor = _infer_vendor_from_provider(provider)
    auth_header_template = None
    try:
        from services.llm_provider_meta import load_provider_meta

        auth_header_template = load_provider_meta(vendor).auth_header_format
    except Exception:  # noqa: BLE001 - third-party providers may not have metadata docs.
        auth_header_template = None

    results: list[ProviderModelTestResult] = []
    for model_id in model_ids:
        result = await probe_model_id(
            provider_type,
            provider.api_key,
            base_url,
            model_id,
            auth_header_template,
        )
        results.append(ProviderModelTestResult(**result.__dict__))

    merged_models = _merge_available_models(
        list(provider.available_models),
        [result.model_id for result in results if result.status == "ok"],
        vendor=vendor,
    )
    _persist_test_outcome(
        provider.id,
        last_test_status=provider.last_test_status,
        last_test_at=provider.last_test_at,
        last_test_message=provider.last_test_message,
        last_error_code=provider.last_error_code,
        available_sdks=list(provider.available_sdks),
        available_models=merged_models,
        expected_api_key=provider.api_key,
        expected_base_url=provider.base_url or "",
        expected_provider_type=provider.provider_type,
    )
    return ProviderModelTestResponse(results=results, available_models=merged_models)


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
        normalize_role_drafts(request)
        validate_references(request)
        save_roles_file(ROLES_PATH, request)
        saved = load_roles_file(ROLES_PATH)
        validate_references(saved)
        return saved
    except InvalidRoleReference as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _record_and_return(
    provider_id: str,
    response: ProviderTestResponse,
    outcome_at: str,
    *,
    expected_api_key: str,
    expected_base_url: str,
    expected_provider_type: ProviderType,
) -> ProviderTestResponse:
    """Write the Test outcome back to credentials (best-effort) and return the response."""

    try:
        _persist_test_outcome(
            provider_id,
            last_test_status=response.status,  # type: ignore[arg-type]
            last_test_at=outcome_at,
            last_test_message=response.message or "",
            last_error_code=response.error_code or "",
            available_sdks=list(response.available_sdks),
            available_models=list(response.available_models),
            expected_api_key=expected_api_key,
            expected_base_url=expected_base_url,
            expected_provider_type=expected_provider_type,
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


def _elapsed_ms(started: datetime) -> int:
    return max(0, round((datetime.now(tz=UTC) - started).total_seconds() * 1000))


def _infer_vendor(request: ProviderTestRequest) -> str:
    if request.id and "-" in request.id:
        candidate = request.id.split("-", 1)[0].lower()
        if (DOCS_DIR / f"{candidate}.md").exists():
            return candidate
    mapping = {
        "anthropic_compatible": "anthropic",
        "openai_compatible": "openai",
        "google_genai": "gemini",
    }
    return mapping.get(request.provider_type, "openai")


def _infer_vendor_from_provider(provider: ProviderCredential) -> str:
    if provider.id and "-" in provider.id:
        candidate = provider.id.split("-", 1)[0].lower()
        if (DOCS_DIR / f"{candidate}.md").exists():
            return candidate
    if provider.id and "_" in provider.id:
        candidate = provider.id.split("_", 1)[0].lower()
        if (DOCS_DIR / f"{candidate}.md").exists():
            return candidate
    mapping = {
        "anthropic_compatible": "anthropic",
        "openai_compatible": "openai",
        "google_genai": "gemini",
    }
    return mapping.get(provider.provider_type or "openai_compatible", "openai")


def _provider_has_models_endpoint(vendor: str) -> bool:
    try:
        return load_provider_meta(vendor).models_endpoint_path is not None
    except Exception as exc:  # noqa: BLE001 - unknown metadata falls back to SDK probing.
        logger.warning("Provider metadata unavailable vendor=%s error=%s", vendor, exc)
        return False


def _provider_test_error_from_exception(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, TimeoutError | httpx.TimeoutException):
        return "timeout", "timeout", "Provider request timed out."
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code in (401, 403):
            return "invalid_key", "invalid_api_key", "Provider rejected the API key."
        if status_code == 402:
            return "quota_exceeded", "quota_exceeded", "Provider quota is exhausted."
        if status_code == 429:
            return "rate_limited", "rate_limited", "Provider rate limit was reached."
        if status_code == 404:
            return "error", "model_list_unavailable", "Provider model-list endpoint was not found."
        if status_code >= 500:
            return "error", "http_error", "Provider or upstream service failed."
        return "error", "http_error", f"Provider returned HTTP {status_code}."
    if isinstance(exc, httpx.HTTPError):
        return "network_error", "network_error", "Provider could not be reached."
    return "error", "model_list_unavailable", "Provider model list could not be loaded."


def _dedupe_model_ids(model_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for model_id in model_ids:
        normalized = model_id.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _merge_available_models(
    existing: list[ModelInfo],
    passed_model_ids: list[str],
    *,
    vendor: str = "",
) -> list[ModelInfo]:
    by_id = {
        normalized.id: normalized
        for normalized in (
            normalize_model_info_for_vendor(model, vendor)
            for model in existing
        )
    }
    for model_id in passed_model_ids:
        canonical_model_id = canonical_model_id_for_vendor(model_id, vendor)
        if canonical_model_id not in by_id:
            by_id[canonical_model_id] = normalize_model_info_for_vendor(
                ModelInfo(id=model_id),
                vendor,
            )
    return list(by_id.values())


def _default_base_url(provider_type: ProviderType) -> str:
    return DEFAULT_BASE_URLS[provider_type]


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
