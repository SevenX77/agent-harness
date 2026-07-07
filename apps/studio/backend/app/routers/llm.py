"""Studio LLM registry API endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, NoReturn, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.adapters.gateway import (
    CredentialProviderProtocol,
    EndpointProbeResult,
    GatewayAdapter,
    GatewayProviderRoute,
    GatewayRoleEntry,
    OfficialCallMethod,
    ProfileSelectionError,
    ProviderModelStateProjection,
    ProviderProbeBackend,
    RegistryResolutionError,
    ResolvedRoute,
    ResourceTerminalError,
    RouteProbeResult,
    RuntimeSettings,
    VerifiedProfile,
    build_runtime_setting_descriptors,
    call_method_client_compatibility,
    call_method_ids_for_endpoint,
    canonicalize_model,
    lint_role_routes,
    normalize_route_capabilities,
    select_verified_profile,
)
from app.core.adapters.gateway import (
    endpoint_probe_backend as _gateway_endpoint_probe_backend,
)
from app.core.adapters.gateway import (
    endpoint_probe_base_url as _gateway_endpoint_probe_base_url,
)
from app.core.adapters.gateway import (
    probe_official_call_method as _gateway_probe_official_call_method_request,
)
from app.core.adapters.gateway import (
    test_provider_endpoint as _gateway_test_provider_endpoint_request,
)
from app.core.adapters.gateway import (
    test_provider_route as _gateway_test_provider_route_request,
)
from app.core.adapters.transport_factory import build_gateway_adapter
from app.core.backends import get_backend_config, get_metadata
from app.models.llm_config import (
    CapabilityValue,
    CommunityCatalogSummary,
    EvidenceRecord,
    LLMCredentialsFile,
    ModelBundle,
    ModelProfile,
    ProbeCatalogSummary,
    ProviderEndpoint,
    ProviderRoute,
    RegistryResponse,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
    RoleRouteEntry,
    RolesData,
    overlay_bundle_reference_chain,
)
from app.services import copilot
from app.services.community_catalog import COMMUNITY_PROVENANCE
from app.services.community_catalog_runtime import sync_verified_community_catalog_into_credentials
from app.services.community_catalog_sync import (
    VerifiedSyncError,
)
from app.services.community_catalog_upload import (
    CommunityUploadClient,
    CommunityUploadError,
    batch_idempotency_key,
    community_upload_configured,
)
from app.services.event_bus import STUDIO_EVENTS_TOPIC, event_bus
from app.services.gateway_resolver import build_gateway_route_runtime
from app.services.llm_credentials import (
    EndpointInvariantViolation,
    _route_slug,
    credentials_path,
    delete_endpoint,
    delete_route,
    load_credentials,
    save_credentials,
    upsert_endpoints,
    upsert_routes,
)
from app.services.llm_credentials_evidence import (
    collect_uploadable,
    endpoint_listed_model_ids,
    endpoint_probe_priority,
    merge_route_evidence,
    probe_evidence_counts,
    route_is_probe_verified,
)
from app.services.llm_evidence_ids import new_evidence_id
from app.services.llm_health_store import (
    ActiveCircuitsIndex,
    RuntimeCircuit,
    SqliteLlmHealthStore,
)
from app.services.llm_model_groups import (
    normalize_model_group_key,
    project_model_group_identity,
)
from app.services.llm_model_identity import project_model_identity
from app.services.llm_notable_models import notable_model_ids
from app.services.llm_provider_identity import registrable_provider_name
from app.services.llm_role_test_results import (
    load_all as load_role_test_results,
)
from app.services.llm_role_test_results import (
    save_result as save_role_test_result,
)
from app.services.llm_roles import (
    InvalidRoleReference,
    get_role,
    load_roles_file,
    roles_path,
    save_roles_file,
    validate_references,
)
from app.services.llm_route_capabilities import (
    route_effective_capabilities,
    verified_profile_route_capabilities,
)
from app.services.model_probe import ModelProbeResult
from app.services.official_capability_sources import (
    OfficialCapabilityRule,
    official_api_list_source_urls,
    official_doc_source_urls,
    provider_doc_limit_rules,
)
from app.services.provider_config import (
    language_model_classification,
    notable_provider_key_for,
    official_provider_key_for_host,
    static_probe_candidate_specs,
)
from app.services.provider_probe_rules import dynamic_probe_candidate_specs
from app.services.runtime_activity import record_runtime_activity

router = APIRouter(prefix="/api/llm", tags=["llm"])
logger = logging.getLogger(__name__)

DISABLED_ENDPOINT_PROBE_MESSAGE = "Endpoint is disabled; skipping live provider probe."
_ENDPOINT_DISABLED_ERROR_CODE = "endpoint_disabled"


async def _autoshare_after_probe_best_effort() -> None:
    """Best-effort community auto-share to the gate after a successful probe.

    Silently uploads newly probe-verified evidence to the community catalog gate
    through a clean open API (no token, no credentials — the gate rate-limits
    server-side). NEVER raises: a probe must not fail because background sharing
    did. On by default; stays dormant only if an operator hard-disables the write
    path OR the single community model-catalog toggle
    (``remote_model_catalog_enabled``, which gates both read and contribute) is off.
    """
    uploads: list[Any] = []
    try:
        cfg = get_backend_config()
        if not community_upload_configured(
            gate_url=cfg.community_gate_url,
            enabled=cfg.community_upload_enabled,
        ):
            return
        # The single community model-catalog toggle gates both reading the
        # catalog and contributing to it; honour the user's opt-out before upload.
        settings = await get_metadata().read_app_settings()
        if not settings.remote_model_catalog_enabled:
            return
        uploads = collect_uploadable(load_credentials())
        if not uploads:
            return
        client = CommunityUploadClient(
            gate_url=cfg.community_gate_url,
            protocol_major=cfg.community_protocol_major,
        )
        # Phase 6: no offline queue. If the upload fails it just raises (swallowed
        # below); the next probe re-derives candidates from credentials and retries.
        await client.upload_batch(uploads, idempotency_key=batch_idempotency_key(uploads))
        # W2-E.1c / R-F4: record the post-probe upload outcome so General settings
        # shows how many evidence records were contributed and that it succeeded.
        record_runtime_activity(
            source_id="llm_credentials",
            action="autoshare_uploaded",
            message="Auto-shared probe-verified evidence to the community catalog gate.",
            changes={"uploaded_count": len(uploads)},
        )
    except Exception as exc:  # noqa: BLE001 — best-effort: sharing must never fail a probe
        logger.warning("post-probe community auto-share failed", exc_info=True)
        try:
            record_runtime_activity(
                source_id="llm_credentials",
                action="autoshare_failed",
                message="Post-probe community auto-share failed (best-effort; retried on next probe).",
                changes={"attempted_count": len(uploads), "error": str(exc)},
            )
        except Exception:  # noqa: BLE001 — recording the failure must also never raise
            logger.warning("failed to record auto-share failure", exc_info=True)


OFFICIAL_PROVIDER_TEST_CONCURRENCY = 4
OFFICIAL_PROVIDER_TEST_BATCH_SIZE = 8
NO_VERIFIED_ROUTE_PROFILE_MESSAGE = "No verified language route profile."
NO_WORKING_OFFICIAL_LANGUAGE_METHOD_MESSAGE = "No official language call method passed for this model."
ROLE_TEST_NO_VERIFIED_PROFILE_MESSAGE = "Route has no verified invocation profile."
_THINKING_CAPABILITY_KEYS = (
    "thinking_protocol",
    "thinking",
    "reasoning",
    "supports_thinking",
)


@dataclass(frozen=True)
class OfficialLanguageProbeCandidate:
    profile_id: str
    capability: str
    method_id: OfficialCallMethod
    request_mapper_id: str
    runtime_settings: dict[str, Any] = field(default_factory=dict)
    default_rank: int = 100
    fallback_rank: int = 100
    input_modalities: tuple[str, ...] = ("text",)
    output_modalities: tuple[str, ...] = ("text",)
    retry_group: str | None = None


@dataclass(frozen=True)
class OfficialModelProfileProbeResult:
    model_id: str
    profiles: list[VerifiedProfile] = field(default_factory=list)
    last_probe_message: str | None = None
    probe_attempts: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RoleTestTarget:
    report_entry: dict[str, Any]
    route: ProviderRoute
    endpoint: ProviderEndpoint
    entry: RoleRouteEntry | None = None


class EndpointTestCompactModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    route_id: str | None = None
    status: Literal["verified", "unverified_manual", "disabled", "failed", "testing", "probe-verified"] | None = None
    verified_profile_count: int | None = None
    last_probe_message: str | None = None
    capabilities: dict[str, object] = Field(default_factory=dict)


class ProviderNotableModelsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notable_models: list[str]


class RoleTestProviderProgressInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    route_id: str
    # R-F11: 6-state light alignment with ProviderUiState. The SDK probe path
    # emits "cooling_down" when the upstream surface (e.g. anthropic 429) signals
    # rate limiting, so the FE can render a gray light + retry countdown instead
    # of a generic "failed".
    status: Literal["queued", "testing", "ok", "failed", "blocked", "untested", "cooling_down"]
    message: str | None = None
    # R-F21: when status == "cooling_down", carry the suggested cooldown so the
    # FE Test Button can render a countdown and stay disabled until it elapses.
    retry_after_seconds: int | None = None


class RoleTestJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    role_name: str
    status: Literal["queued", "running", "completed", "failed"]
    message: str | None = None
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None
    provider_statuses: list[RoleTestProviderProgressInfo] = Field(default_factory=list)
    result: dict[str, Any] | None = None


class PersistedRoleTestResult(BaseModel):
    """R20: one durably stored LAST completed role/copilot test result."""

    model_config = ConfigDict(extra="forbid")

    role_name: str
    status: str
    message: str | None = None
    result: dict[str, Any]
    updated_at: str


class RoleTestResultsResponse(BaseModel):
    """R20: persisted last test results keyed by role name for mount re-seed."""

    model_config = ConfigDict(extra="forbid")

    results: dict[str, PersistedRoleTestResult] = Field(default_factory=dict)


def _copilot_diagnostic_text(message: str | None) -> str | None:
    if not isinstance(message, str):
        return None
    text = message.strip()
    if not text:
        return None
    return text


def _persisted_role_test_result_from_storage(entry: object) -> PersistedRoleTestResult:
    return PersistedRoleTestResult.model_validate(entry)


class CompareCandidateTestRequest(BaseModel):
    """Transient node compare-candidate test request."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str = Field(min_length=1)
    route_id: str | None = None


_role_test_jobs: dict[str, RoleTestJobResponse] = {}
_role_test_jobs_lock = asyncio.Lock()
# Keep strong references to fire-and-forget background tasks so the event loop
# cannot garbage-collect them mid-flight (Sonar S7502).
_background_tasks: set[asyncio.Task[None]] = set()


def _spawn_background_task(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class EndpointUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_endpoints: dict[str, ProviderEndpoint] = Field(default_factory=dict)


class EndpointSecretResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    api_key: str


class RouteEditableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    canonical_id: str
    status: Literal["verified", "unverified_manual", "disabled", "failed"]
    capabilities: dict[str, CapabilityValue] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[str] = Field(default_factory=list)
    runtime_settings: dict[str, Any] = Field(default_factory=dict)


class RoleApplyProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_profile_id: str
    mode: Literal["replace"] | None = None


class EndpointTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry: RegistryResponse
    tested_endpoint_id: str
    discovered_model_count: int
    # True when the half-life gate skipped the live probe (design §1.2 matrix
    # revision point 4): the endpoint's protocol_unsupported observation is
    # still fresh, so no provider call was made and no state changed.
    skipped: bool = False


class EndpointModelTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_ids: list[str] = Field(default_factory=list)


class EndpointModelTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    status: Literal[
        "ok",
        "invalid_model",
        "invalid_key",
        "protocol_unsupported",
        "rate_limited",
        "quota_exceeded",
        "network_error",
        "timeout",
        "error",
    ]
    route_id: str | None = None
    message: str | None = None


class EndpointModelTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry: RegistryResponse
    results: list[EndpointModelTestResult]


class RolesProjectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles_data: RolesData
    registry: RegistryResponse


@router.get("/registry", response_model=RegistryResponse)
async def get_llm_registry() -> RegistryResponse:
    """Return the joined redacted endpoint/route/role registry."""
    setup_required = not credentials_path().exists()
    credentials = load_credentials()
    roles = _load_roles_or_empty()
    # The registry projection is a synchronous, CPU-bound join (route-state
    # projection + model-group grouping over every route). Run it off the event
    # loop so a slow build never starves other requests / the WS on the single
    # asyncio thread.
    return await asyncio.to_thread(
        _registry_response, credentials, roles, setup_required=setup_required
    )


async def _write_registry_response(credentials: LLMCredentialsFile) -> RegistryResponse:
    """Return the canonical registry projection after a registry write."""
    return await asyncio.to_thread(
        _registry_response,
        credentials,
        _load_roles_or_empty(),
        setup_required=False,
    )


async def _roles_projection_response(
    roles: RolesData,
    credentials: LLMCredentialsFile | None = None,
    *,
    setup_required: bool = False,
) -> RolesProjectionResponse:
    """Return roles plus the registry projection built from the same snapshot."""
    active_credentials = credentials or load_credentials()
    roles_data = _materialize_roles_for_response(roles, active_credentials)
    registry = await asyncio.to_thread(
        _registry_response,
        active_credentials,
        roles_data,
        setup_required=setup_required,
    )
    return RolesProjectionResponse(roles_data=roles_data, registry=registry)


@router.get("/registry/endpoints/{endpoint_id}/secret", response_model=EndpointSecretResponse)
async def get_registry_endpoint_secret(endpoint_id: str) -> EndpointSecretResponse:
    """Return one endpoint secret for the local settings UI."""
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint_id}")
    return EndpointSecretResponse(
        endpoint_id=endpoint_id,
        api_key=endpoint.api_key.get_secret_value() if endpoint.api_key else "",
    )


@router.put("/registry/endpoints", response_model=RegistryResponse)
async def put_registry_endpoints(request: EndpointUpsertRequest) -> RegistryResponse:
    """Upsert endpoints; absent endpoint IDs are retained."""
    try:
        data = upsert_endpoints({endpoint_id: endpoint for endpoint_id, endpoint in request.provider_endpoints.items()})
    except EndpointInvariantViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_runtime_activity(
        source_id="llm_credentials",
        action="upsert_endpoints",
        message="Saved provider endpoint settings.",
        changes={
            "endpoint_ids": sorted(request.provider_endpoints),
            "endpoint_count": len(data.provider_endpoints),
            "route_count": len(data.provider_routes),
        },
    )
    _reconcile_fixed_roles_after_credential_change()
    return await _write_registry_response(data)


@router.delete("/registry/endpoints/{endpoint_id}", response_model=RegistryResponse)
async def delete_registry_endpoint(endpoint_id: str) -> RegistryResponse:
    """Delete an endpoint and cascade its owned provider route references."""
    credentials = load_credentials()
    roles = _load_roles_or_empty()
    refs = _endpoint_references(endpoint_id, credentials, roles)
    route_ids = set(refs["routes"])
    if route_ids and roles_path().exists():
        save_roles_file(
            roles_path(),
            _remove_route_references_from_roles(roles, route_ids),
            known_route_ids=set(credentials.provider_routes) - route_ids,
        )
        record_runtime_activity(
            source_id="llm_roles",
            action="remove_endpoint_route_references",
            message="Removed role references to routes owned by a deleted endpoint.",
            changes={"endpoint_id": endpoint_id, "route_ids": sorted(route_ids)},
        )
    data = delete_endpoint(endpoint_id)
    record_runtime_activity(
        source_id="llm_credentials",
        action="delete_endpoint",
        message="Deleted a provider endpoint and its owned routes.",
        changes={
            "endpoint_id": endpoint_id,
            "removed_route_ids": sorted(route_ids),
            "remaining_endpoint_count": len(data.provider_endpoints),
            "remaining_route_count": len(data.provider_routes),
        },
    )
    return await _write_registry_response(data)


@router.post("/catalog/sync")
async def sync_catalog() -> dict[str, Any]:
    """Retired (R9.6): the legacy remote probe-catalog sync is no longer a runtime path.

    Evidence is owned by ``credentials.provider_routes[*].evidence`` (SSOT); community
    evidence arrives via the verified sync (``/catalog/sync-verified`` → route.evidence,
    Phase 5). This endpoint is a no-op kept only so the existing UI button does not 404;
    it neither reads nor writes ``llm_probe_catalog.json``.
    """
    return {
        "status": "disabled",
        "message": "The legacy remote probe-catalog sync is retired. Evidence lives in "
        "credentials route.evidence; community evidence arrives via verified sync.",
        "route_candidates_count": 0,
        "evidence_records_count": 0,
        "new_records_count": 0,
        "catalog_source": None,
    }


@router.post("/catalog/repository/ensure")
async def ensure_catalog_repository_endpoint() -> dict[str, Any]:
    """Retired (Phase 9): the GitHub-repo probe-catalog concept no longer exists.

    Evidence lives in credentials ``route.evidence`` and community evidence arrives via
    verified sync; there is no remote ``llm_probe_catalog.json`` repository to create.
    Kept as a disabled no-op so any older client that still calls it gets a clean,
    networkless reply instead of a 404.
    """
    return {
        "status": "disabled",
        "message": (
            "The GitHub-backed remote catalog repository is retired. Evidence lives in "
            "credentials route.evidence; community evidence arrives via verified sync."
        ),
    }


@router.post("/catalog/share")
async def share_catalog() -> dict[str, Any]:
    """Export and return all local successful evidence records ready to be shared with the community."""
    try:
        credentials = load_credentials()
        # Shareable evidence is derived from credentials route.evidence (SSOT) — local
        # probe-verified, excluding community-provenance (no remote→local→remote loop).
        probed_records = [
            rec.model_dump(mode="json")
            for route in credentials.provider_routes.values()
            for rec in route.evidence
            if rec.evidence_type == "probe"
            and rec.trust_state == "probe-verified"
            and rec.metadata.get("provenance") != COMMUNITY_PROVENANCE
        ]
        verified_routes_count = sum(1 for r in credentials.provider_routes.values() if r.status == "verified")

        return {
            "status": "success",
            "message": "Local verified catalog evidence exported successfully.",
            "sharing_mode": "local_export_only",
            "auto_upload_enabled": False,
            "verified_routes_in_credentials": verified_routes_count,
            "evidence_records_to_share": probed_records,
            "export_instructions": (
                "MVP1 exports local verified evidence only; it does not upload community catalog "
                "evidence automatically. Keep these records local or pass them to a maintainer "
                "until a dedicated catalog ingestion service exists."
            ),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to share catalog evidence: {exc}",
        ) from exc


@router.post("/catalog/contribute")
async def contribute_catalog() -> dict[str, Any]:
    """Upload sanitized probe evidence to the community catalog gate.

    Active by default through a clean open API (no token). Dormant only if an
    operator hard-disables the write path or no gate URL is set (Phase 2a). When
    dormant this is a no-op that never reaches the network; the local export path
    stays unchanged.
    """
    cfg = get_backend_config()
    if not community_upload_configured(
        gate_url=cfg.community_gate_url,
        enabled=cfg.community_upload_enabled,
    ):
        record_runtime_activity(
            source_id="llm_credentials",
            action="contribute_catalog_skipped",
            message="Skipped community catalog contribution because upload is disabled or unconfigured.",
            changes={"auto_upload_enabled": False},
        )
        return {
            "status": "disabled",
            "sharing_mode": "local_export_only",
            "auto_upload_enabled": False,
            "message": (
                "Community upload is disabled. It is on by default; it is off only when an "
                "operator hard-disables the write path or no gate URL is set."
            ),
        }

    try:
        uploads = collect_uploadable(load_credentials())
        if not uploads:
            record_runtime_activity(
                source_id="llm_credentials",
                action="contribute_catalog_noop",
                message="Checked community catalog contribution; no probe-verified evidence was available.",
                changes={"records_submitted": 0},
            )
            return {
                "status": "success",
                "auto_upload_enabled": True,
                "accepted": 0,
                "message": "No probe-verified evidence is available to contribute.",
            }
        client = CommunityUploadClient(
            gate_url=cfg.community_gate_url,
            protocol_major=cfg.community_protocol_major,
        )
        key = batch_idempotency_key(uploads)
        try:
            ack = await client.upload_batch(uploads, idempotency_key=key)
        except CommunityUploadError:
            # Phase 6: no local queue. The evidence stays in credentials; the next
            # probe / contribute re-derives the SAME batch (content-derived key) and
            # retries at the gate — so a failure is "not yet", not data loss.
            record_runtime_activity(
                source_id="llm_credentials",
                action="contribute_catalog_failed",
                message=(
                    "Community catalog upload failed; the evidence stays in credentials and "
                    "will be re-derived and retried on the next probe or contribute."
                ),
                changes={"records_pending": len(uploads)},
            )
            return {
                "status": "failed",
                "auto_upload_enabled": True,
                "queued": False,
                "records_pending": len(uploads),
                "message": (
                    "Upload failed (the gate was unreachable). The evidence stays in your "
                    "credentials and will be re-derived and retried automatically on the next "
                    "probe or contribute."
                ),
            }
        record_runtime_activity(
            source_id="llm_credentials",
            action="contribute_catalog_uploaded",
            message="Uploaded sanitized local evidence to the community catalog gate.",
            changes={
                "records_submitted": len(uploads),
                "accepted": ack.accepted,
                "rejected": ack.rejected,
            },
        )
        return {
            "status": "success",
            "auto_upload_enabled": True,
            "accepted": ack.accepted,
            "rejected": ack.rejected,
            "receipt_token": ack.receipt_token,
            "records_submitted": len(uploads),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to contribute catalog evidence: {exc}",
        ) from exc


@router.post("/catalog/sync-verified")
async def sync_verified_community_catalog() -> dict[str, Any]:
    """Pull the signed community catalog and merge verified evidence into credentials (R4).

    Dormant unless a manifest URL and a signing public key are configured. The
    sync is fail-closed: a bad signature, shard digest, or incompatible protocol
    surfaces as an error and credentials are left untouched.

    Phase 5: no disposable cache. Verified records are merged straight onto matching
    ``route.evidence`` (SSOT) and only a tiny last-sync marker is persisted; routes
    that do not exist yet simply pick the evidence up on a later sync.
    """
    try:
        return await sync_verified_community_catalog_into_credentials(trigger="api")
    except VerifiedSyncError as exc:
        raise HTTPException(status_code=502, detail=f"Verified catalog sync failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Verified catalog sync error: {exc}") from exc


@router.post("/endpoints/{endpoint_id}/test", response_model=EndpointTestResponse)
async def test_endpoint(endpoint_id: str, force: bool = False) -> EndpointTestResponse:
    """Verify an endpoint by making the provider's minimal models-list call."""
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint_id}")
    if not force:
        recheck_at = _protocol_unsupported_recheck_at(endpoint)
        if recheck_at is not None and datetime.now(UTC) < recheck_at:
            # Half-life gate (design §1.2 matrix revision point 4): the cell was
            # observed protocol_unsupported recently — an architectural fact that
            # will not flip day-to-day. Skip the provider call and KEEP the old
            # observation (refreshing last_test_at here would keep the half-life
            # from ever expiring). `force=true` re-probes immediately.
            record_runtime_activity(
                source_id="llm_credentials",
                action="endpoint_test_skipped",
                message=(
                    "Skipped endpoint test: the protocol_unsupported observation "
                    "is within its re-check window."
                ),
                changes={
                    "endpoint_id": endpoint_id,
                    "observed_at": endpoint.last_test_at,
                    "recheck_at": recheck_at.isoformat(),
                },
            )
            return EndpointTestResponse(
                registry=_registry_response(credentials, _load_roles_or_empty()),
                tested_endpoint_id=endpoint_id,
                discovered_model_count=0,
                skipped=True,
            )
    starting_fingerprint = credentials.endpoint_fingerprint(endpoint_id)
    status: Literal["verified", "unverified_manual", "failed", "disabled"] = "failed"
    message = "API key is empty."
    auth_failed = False
    last_error_code: str | None = None
    probe_attempts_log: list[dict[str, Any]] = []
    model_list_reached = False
    discovered_model_ids: tuple[str, ...] = ()
    raw_capabilities_by_model: dict[str, dict[str, Any]] = {}
    probe_backend = _endpoint_probe_backend(endpoint)
    logger.warning(
        "testing LLM endpoint protocol=%s backend=%s",
        endpoint.protocol,
        probe_backend,
    )
    result = await _probe_endpoint_model_list_atom(endpoint, allow_disabled=force)
    if result.error_code == _ENDPOINT_DISABLED_ERROR_CODE:
        record_runtime_activity(
            source_id="llm_credentials",
            action="endpoint_test_skipped",
            message=DISABLED_ENDPOINT_PROBE_MESSAGE,
            changes={"endpoint_id": endpoint_id, "reason": _ENDPOINT_DISABLED_ERROR_CODE},
        )
        return EndpointTestResponse(
            registry=_registry_response(credentials, _load_roles_or_empty()),
            tested_endpoint_id=endpoint_id,
            discovered_model_count=0,
            skipped=True,
        )
    if result.status == "ok":
        status = "unverified_manual"
        model_list_reached = True
        if not result.model_ids:
            message = "Endpoint reachable but returned no models."
        else:
            message = _endpoint_success_message(result)
            discovered_model_ids = result.model_ids
            raw_capabilities_by_model = result.model_capabilities
    else:
        message = _endpoint_probe_failure_message(result)
        # R-E2: an invalid API key means the endpoint is unusable until the key is
        # fixed — record it so we can disable (not just "fail") the endpoint below.
        auth_failed = result.status == "invalid_key"
        # W2-B.3: persist the STRUCTURED error code so the frontend reads it directly
        # instead of parsing the human last_test_message. For protocol_unsupported
        # the classification wins over any vendor error code — the half-life gate
        # and the UI's unsupported state key off this exact value.
        last_error_code = (
            "protocol_unsupported"
            if result.status == "protocol_unsupported"
            else result.error_code
        )
    latest_credentials = load_credentials()
    latest_endpoint = latest_credentials.provider_endpoints.get(endpoint_id)
    if latest_endpoint is None:
        raise HTTPException(
            status_code=409,
            detail=f"Endpoint changed while endpoint test was running: {endpoint_id}",
        )
    if latest_credentials.endpoint_fingerprint(endpoint_id) != starting_fingerprint:
        updated = latest_endpoint.model_copy(
            update={
                "status": "unverified_manual",
                "last_test_at": _now_iso(),
                "last_test_message": ("Endpoint changed while endpoint test was running. Test result discarded."),
            }
        )
        latest_credentials.provider_endpoints[endpoint_id] = updated
        save_credentials(latest_credentials)
        record_runtime_activity(
            source_id="llm_credentials",
            action="endpoint_test_discarded",
            message="Endpoint test result was discarded because credentials changed during the run.",
            changes={"endpoint_id": endpoint_id, "status": "unverified_manual"},
        )
        return EndpointTestResponse(
            registry=_registry_response(latest_credentials, _load_roles_or_empty()),
            tested_endpoint_id=endpoint_id,
            discovered_model_count=0,
        )
    endpoint_update: dict[str, Any] = {}
    if model_list_reached:
        # R-E2 auto-revive: get-models succeeded, so the key works again. Clear any
        # routes this endpoint had disabled by a prior invalid key BEFORE upsert/verify
        # so they participate normally (and can be re-promoted to verified).
        for revive_route_id, revive_route in list(latest_credentials.provider_routes.items()):
            if revive_route.endpoint_id == endpoint_id and revive_route.status == "disabled":
                latest_credentials.provider_routes[revive_route_id] = revive_route.model_copy(
                    update={"status": "unverified_manual"}
                )
        # model-list truth = routes (R3.4): capture the previously-listed models
        # from credentials BEFORE upserting, so the added/removed diff is real.
        previous_model_ids = set(endpoint_listed_model_ids(latest_credentials, endpoint_id))
        route_ids_by_model: dict[str, str] = {}
        latest_credentials, route_ids_by_model = _upsert_discovered_routes(
            latest_credentials,
            endpoint=latest_endpoint,
            model_ids=discovered_model_ids,
            verified=False,
            raw_capabilities_by_model=raw_capabilities_by_model,
        )
        observed_set = set(discovered_model_ids)
        # model-list dissolves into routes: no provider-list-observed evidence is
        # produced; only the diff is recorded as runtime-activity diagnostics.
        record_runtime_activity(
            source_id="llm_credentials",
            action="model_list_observed",
            message="Recorded model-list diff from an endpoint test.",
            changes={
                "endpoint_id": endpoint_id,
                "model_count": len(discovered_model_ids),
                "added_model_ids": sorted(observed_set - previous_model_ids),
                "removed_model_ids": sorted(previous_model_ids - observed_set),
                "unchanged_model_ids": sorted(observed_set & previous_model_ids),
            },
        )
        # Every endpoint kind must prove it can actually GENERATE before reaching
        # verified (apikeys#24/#25, revised 2026-07-01): get-models only proves
        # key+URL reachability, and a reachable endpoint can still reject every
        # generation call (e.g. an exhausted credit balance). The probe leads with
        # this endpoint's already-verified models so the Test confirms the
        # *endpoint* in as few attempts as possible; third-party matrix cells
        # use their own immutable protocol.
        verified_model_ids = frozenset(
            route.provider_model_id
            for route in latest_credentials.provider_routes.values()
            if route.endpoint_id == endpoint_id and route.status == "verified"
        )
        verification = await _verify_endpoint_by_generation_probe(
            latest_endpoint,
            discovered_model_ids,
            raw_capabilities_by_model,
            allow_disabled=force,
        )
        probe_attempts_log = verification.probe_attempts
        # "no_model" => reachable-but-untested (W2-D / R-E1): map to the
        # endpoint's untested physical status, never "failed".
        if verification.status == "no_model":
            status = "unverified_manual"
            # W2-D.4: structured reason so the UI can warn "no model to test,
            # add a model id and run a single-model test" without parsing text.
            last_error_code = "no_model_available"
        elif verification.status == "skipped_disabled":
            status = "disabled"
            last_error_code = latest_endpoint.last_error_code
        else:
            status = verification.status
        message = verification.message
        if (
            verification.failed_probe is not None
            and verification.failed_probe.status == "protocol_unsupported"
        ):
            # get-models may pass on a URL that cannot generate via this protocol
            # (live: qiniu lists models on both hosts regardless of protocol) —
            # the generation probe is where the mismatch surfaces. Record the
            # structured classification so the gate / UI see it.
            last_error_code = "protocol_unsupported"
        if verification.status == "verified" and verification.verified_model_id is not None:
            if latest_endpoint.provider_kind == "official":
                # Official route truth (status / capabilities / profiles) is owned
                # by the official per-model profile probes — the endpoint test only
                # records its generation evidence on the already-listed route.
                _merge_probe_evidence_into_route(
                    latest_credentials,
                    latest_endpoint,
                    ModelProbeResult(
                        model_id=verification.verified_model_id,
                        status="ok",
                    ),
                    route_id=route_ids_by_model.get(verification.verified_model_id),
                )
            else:
                latest_credentials, verified_route_ids = _upsert_discovered_routes(
                    latest_credentials,
                    endpoint=latest_endpoint,
                    model_ids=(verification.verified_model_id,),
                    verified=True,
                    raw_capabilities_by_model=verification.probe_capabilities,
                )
                _merge_probe_evidence_into_route(
                    latest_credentials,
                    latest_endpoint,
                    ModelProbeResult(
                        model_id=verification.verified_model_id,
                        status="ok",
                    ),
                    route_id=verified_route_ids.get(verification.verified_model_id),
                )
        elif (
            verification.status != "verified"
            and verified_model_ids
            and not verification.failure_is_structural
        ):
            # An endpoint Test only proves the *endpoint* connects. get-models
            # just proved the key+URL are live and this endpoint already has a
            # verified route, so a round where every catalog model probe fails
            # for model-level reasons (flaky / phantom upstream models the
            # provider lists but cannot serve) must NOT regress the endpoint to
            # failed — keep it verified by reusing the previously verified
            # model. Structural failures (invalid_key / quota / billing) are NOT
            # reused: those mean the endpoint itself is broken and must fail.
            retained_model_id = sorted(verified_model_ids)[0]
            status = "verified"
            message = (
                "Endpoint reachable; reusing previously verified model "
                f"{retained_model_id}. No new model verified this run."
            )
        if verification.status != "verified" and verification.failed_probe is not None:
            # Persist the REAL failed model's outcome as probe-failed evidence
            # (R3.1-AC3 / codex-3): upsert its route, then merge the record.
            # This holds even when the endpoint stays verified via reuse above —
            # the model genuinely failed, so its route records that diagnostically.
            failed_result = _model_probe_result_from_route_probe(verification.failed_probe)
            if latest_endpoint.provider_kind == "official":
                # The failed model's route already exists from the model-list
                # upsert above; only the diagnostic evidence is merged onto it.
                _merge_probe_evidence_into_route(
                    latest_credentials,
                    latest_endpoint,
                    failed_result,
                    route_id=route_ids_by_model.get(failed_result.model_id),
                )
            else:
                latest_credentials, failed_route_ids = _upsert_third_party_model_probe_routes(
                    latest_credentials,
                    endpoint=latest_endpoint,
                    probe_results=(failed_result,),
                    raw_capabilities_by_model={},
                )
                _merge_probe_evidence_into_route(
                    latest_credentials,
                    latest_endpoint,
                    failed_result,
                    route_id=failed_route_ids.get(failed_result.model_id),
                )
    elif endpoint.provider_kind != "official" and result.status not in _STRUCTURAL_PROBE_STATUSES:
        probe_results = await _probe_third_party_models_for_endpoint(endpoint, ())
        if probe_results:
            latest_credentials, probed_route_ids = _upsert_third_party_model_probe_routes(
                latest_credentials,
                endpoint=latest_endpoint,
                probe_results=tuple(probe_results),
                raw_capabilities_by_model={},
            )
            for probe_result in probe_results:
                _merge_probe_evidence_into_route(
                    latest_credentials,
                    latest_endpoint,
                    probe_result,
                    route_id=probed_route_ids.get(probe_result.model_id),
                )
            status = _endpoint_status_from_model_probe_results(probe_results)
            message = _endpoint_message_from_model_probe_results(probe_results)
    if auth_failed:
        # R-E2: an invalid API key makes the whole endpoint unusable until the key
        # is fixed => disable the endpoint AND all its routes (not a transient
        # "failed"). A later successful Test revives them (see the revive sweep).
        status = "disabled"
        for route_id, route in list(latest_credentials.provider_routes.items()):
            if route.endpoint_id == endpoint_id and route.status != "disabled":
                latest_credentials.provider_routes[route_id] = route.model_copy(
                    update={"status": "disabled"}
                )
    if last_error_code == "protocol_unsupported":
        # Design §1.2 matrix revision point 6: routes only live on cells that
        # speak their protocol. Clear this cell's routes (phantom model lists on
        # a dead transport are pure red noise) and strip role references to them.
        unsupported_route_ids = {
            route_id
            for route_id, route in latest_credentials.provider_routes.items()
            if route.endpoint_id == endpoint_id
        }
        if unsupported_route_ids:
            roles = _load_roles_or_empty()
            if roles_path().exists():
                save_roles_file(
                    roles_path(),
                    _remove_route_references_from_roles(roles, unsupported_route_ids),
                    known_route_ids=set(latest_credentials.provider_routes) - unsupported_route_ids,
                )
                record_runtime_activity(
                    source_id="llm_roles",
                    action="remove_endpoint_route_references",
                    message="Removed role references to routes on a protocol-unsupported endpoint.",
                    changes={
                        "endpoint_id": endpoint_id,
                        "route_ids": sorted(unsupported_route_ids),
                    },
                )
            for route_id in unsupported_route_ids:
                del latest_credentials.provider_routes[route_id]
    endpoint_update.update(
        {
            "status": status,
            "last_test_at": _now_iso(),
            "last_test_message": message,
            "last_error_code": last_error_code,
        }
    )
    updated = latest_endpoint.model_copy(update=endpoint_update)
    latest_credentials.provider_endpoints[endpoint_id] = updated
    save_credentials(latest_credentials)
    record_runtime_activity(
        source_id="llm_credentials",
        action="endpoint_test",
        message="Saved endpoint test result with probe evidence on credentials routes.",
        changes={
            "endpoint_id": endpoint_id,
            "status": status,
            "message": message,
            # W2-E diagnostics: record what the Test actually saw — whether get-models
            # reached the provider and the exact model ids it returned (not just a count).
            "reachable": model_list_reached,
            "discovered_model_count": len(discovered_model_ids),
            "discovered_model_ids": list(discovered_model_ids),
            # W2-E.1b: which protocol×model combos were generation-probed and how each fared.
            "probe_attempts": probe_attempts_log,
        },
    )
    # 新发现的 route 可能正是某个固定角色缺的推荐模型 → 立刻补齐,再回传含新角色的 registry。
    _reconcile_fixed_roles_after_credential_change()
    return EndpointTestResponse(
        registry=_registry_response(latest_credentials, _load_roles_or_empty()),
        tested_endpoint_id=endpoint_id,
        discovered_model_count=len(discovered_model_ids),
    )


@router.get("/providers/notable-models", response_model=ProviderNotableModelsResponse)
def get_provider_notable_models(provider_key: str) -> ProviderNotableModelsResponse:
    """Return doc-maintained model ID suggestions for manual provider probing."""
    return ProviderNotableModelsResponse(notable_models=notable_model_ids(provider_key))


@router.post("/endpoints/{endpoint_id}/models/test", response_model=EndpointModelTestResponse)
async def test_endpoint_models(
    endpoint_id: str,
    request: EndpointModelTestRequest,
) -> EndpointModelTestResponse:
    """Probe requested model IDs against one stored endpoint and upsert route results."""
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint_id}")
    starting_fingerprint = credentials.endpoint_fingerprint(endpoint_id)

    requested_model_ids = _requested_model_ids(request.model_ids)
    results: list[EndpointModelTestResult] = []
    if _endpoint_probe_is_disabled(endpoint):
        return EndpointModelTestResponse(
            registry=_registry_response(credentials, _load_roles_or_empty()),
            results=[
                EndpointModelTestResult(
                    model_id=model_id,
                    status="error",
                    message=DISABLED_ENDPOINT_PROBE_MESSAGE,
                )
                for model_id in requested_model_ids
            ],
        )
    if not endpoint.api_key or not endpoint.api_key.get_secret_value():
        results = [
            EndpointModelTestResult(
                model_id=model_id,
                status="invalid_key",
                message="API key is empty.",
            )
            for model_id in requested_model_ids
        ]
        return EndpointModelTestResponse(
            registry=_registry_response(credentials, _load_roles_or_empty()),
            results=results,
        )

    if endpoint.provider_kind == "official":
        official_results: list[OfficialModelProfileProbeResult] = []
        for model_id in requested_model_ids:
            official_results.append(await _probe_official_model_profile_atom(endpoint, model_id))
        successful_model_ids = [result.model_id for result in official_results if result.profiles]
        failed_profile_results = [result for result in official_results if not result.profiles]
        route_ids_by_model: dict[str, str] = {}
        latest_credentials = credentials
        if official_results:
            latest_credentials = load_credentials()
            latest_endpoint = latest_credentials.provider_endpoints.get(endpoint_id)
            if latest_endpoint is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Endpoint changed while model test was running: {endpoint_id}",
                )
            if latest_credentials.endpoint_fingerprint(endpoint_id) != starting_fingerprint:
                results = [
                    EndpointModelTestResult(
                        model_id=result.model_id,
                        status="error",
                        message="Endpoint changed while model test was running.",
                    )
                    for result in official_results
                ]
                return EndpointModelTestResponse(
                    registry=_registry_response(latest_credentials, _load_roles_or_empty()),
                    results=results,
                )
            if successful_model_ids:
                latest_credentials, route_ids_by_model = _upsert_discovered_routes(
                    latest_credentials,
                    endpoint=latest_endpoint,
                    model_ids=tuple(successful_model_ids),
                    verified=True,
                    verified_profiles_by_model={
                        result.model_id: result.profiles for result in official_results if result.profiles
                    },
                    probe_attempts_by_model={
                        result.model_id: result.probe_attempts for result in official_results if result.probe_attempts
                    },
                )
                latest_endpoint = latest_endpoint.model_copy(
                    update={
                        "status": "verified",
                        "last_test_at": _now_iso(),
                        "last_test_message": f"Connected. Model seen: {successful_model_ids[0]}.",
                    }
                )
                latest_credentials.provider_endpoints[endpoint_id] = latest_endpoint
            if failed_profile_results:
                latest_credentials, failed_route_ids = _upsert_failed_official_model_routes(
                    latest_credentials,
                    endpoint=latest_endpoint,
                    profile_results=tuple(failed_profile_results),
                )
                route_ids_by_model.update(failed_route_ids)
            # Return-and-merge BEFORE the single save (R3.3): official profile probe
            # evidence (verified + failed) lands on its route, not the probe catalog.
            for result in official_results:
                _merge_official_profile_evidence_into_route(
                    latest_credentials,
                    latest_endpoint,
                    result,
                    route_id=route_ids_by_model.get(result.model_id),
                )
            save_credentials(latest_credentials)
            record_runtime_activity(
                source_id="llm_credentials",
                action="manual_model_probe",
                message="Saved official manual model probe results.",
                changes={
                    "endpoint_id": endpoint_id,
                    "requested_model_count": len(requested_model_ids),
                    "verified_model_count": len(successful_model_ids),
                    "failed_model_count": len(failed_profile_results),
                },
            )
        results = [
            EndpointModelTestResult(
                model_id=result.model_id,
                status="ok" if result.profiles else "error",
                route_id=route_ids_by_model.get(result.model_id),
                message=None if result.profiles else result.last_probe_message,
            )
            for result in official_results
        ]
        if official_results:
            record_runtime_activity(
                source_id="llm_credentials",
                action="manual_model_probe_evidence",
                message="Recorded official manual model probe evidence on credentials routes.",
                changes={
                    "endpoint_id": endpoint_id,
                    "model_ids": sorted(requested_model_ids),
                },
            )
        await _autoshare_after_probe_best_effort()
        return EndpointModelTestResponse(
            registry=_registry_response(latest_credentials, _load_roles_or_empty()),
            results=results,
        )

    probe_results: list[ModelProbeResult] = []
    for model_id in requested_model_ids:
        probe_results.append(
            _model_probe_result_from_route_probe(
                await _probe_model_generation_atom(endpoint, model_id)
            )
        )
    successful_model_ids = [result.model_id for result in probe_results if result.status == "ok"]
    if probe_results:
        latest_credentials = load_credentials()
        latest_endpoint = latest_credentials.provider_endpoints.get(endpoint_id)
        if latest_endpoint is None:
            raise HTTPException(
                status_code=409,
                detail=f"Endpoint changed while model test was running: {endpoint_id}",
            )
        if latest_credentials.endpoint_fingerprint(endpoint_id) != starting_fingerprint:
            results = [
                EndpointModelTestResult(
                    model_id=result.model_id,
                    status="error",
                    message="Endpoint changed while model test was running.",
                )
                for result in probe_results
            ]
            return EndpointModelTestResponse(
                registry=_registry_response(latest_credentials, _load_roles_or_empty()),
                results=results,
            )
        list_model_capabilities = await _list_model_capabilities_for_endpoint(latest_endpoint)
        latest_credentials, route_ids_by_model = _upsert_third_party_model_probe_routes(
            latest_credentials,
            endpoint=latest_endpoint,
            probe_results=tuple(probe_results),
            raw_capabilities_by_model={
                model_id: _third_party_probe_capabilities(
                    model_id,
                    list_model_capabilities.get(model_id),
                )
                for model_id in successful_model_ids
            },
        )
        # Return-and-merge BEFORE the single save (R3.3): build each probe result's
        # evidence and assign it back onto its route (verified or failed).
        for probe_result in probe_results:
            _merge_probe_evidence_into_route(
                latest_credentials,
                latest_endpoint,
                probe_result,
                route_id=route_ids_by_model.get(probe_result.model_id),
            )
        status = _endpoint_status_from_model_probe_results(probe_results)
        message = _endpoint_message_from_model_probe_results(probe_results)
        latest_endpoint = latest_endpoint.model_copy(
            update={
                "status": status,
                "last_test_at": _now_iso(),
                "last_test_message": message,
            }
        )
        latest_credentials.provider_endpoints[endpoint_id] = latest_endpoint
        save_credentials(latest_credentials)
        record_runtime_activity(
            source_id="llm_credentials",
            action="manual_model_probe",
            message="Saved manual model probe results.",
            changes={
                "endpoint_id": endpoint_id,
                "status": status,
                "requested_model_count": len(requested_model_ids),
                "successful_model_count": len(successful_model_ids),
                "failed_model_count": len(probe_results) - len(successful_model_ids),
            },
        )
    else:
        latest_credentials = load_credentials()
        latest_endpoint = latest_credentials.provider_endpoints.get(endpoint_id)
        if latest_endpoint is not None and probe_results:
            if latest_credentials.endpoint_fingerprint(endpoint_id) != starting_fingerprint:
                results = [
                    EndpointModelTestResult(
                        model_id=result.model_id,
                        status="error",
                        message="Endpoint changed while model test was running.",
                    )
                    for result in probe_results
                ]
                return EndpointModelTestResponse(
                    registry=_registry_response(latest_credentials, _load_roles_or_empty()),
                    results=results,
                )
            latest_credentials.provider_endpoints[endpoint_id] = latest_endpoint.model_copy(
                update={
                    "status": "failed",
                    "last_test_at": _now_iso(),
                    "last_test_message": _model_probe_failure_message(probe_results[0]),
                }
            )
            save_credentials(latest_credentials)
        route_ids_by_model = {}
    results = [
        EndpointModelTestResult(
            model_id=probe_result.model_id,
            status=probe_result.status,
            route_id=route_ids_by_model.get(probe_result.model_id),
            message=probe_result.message,
        )
        for probe_result in probe_results
    ]
    if probe_results:
        record_runtime_activity(
            source_id="llm_credentials",
            action="manual_model_probe_evidence",
            message="Recorded manual model probe evidence on credentials routes.",
            changes={
                "endpoint_id": endpoint_id,
                "model_ids": sorted(result.model_id for result in probe_results),
            },
        )
    await _autoshare_after_probe_best_effort()
    # 手动探测出的新 route 也可能补齐固定角色缺的推荐模型 → reconcile 后回传含新角色的 registry。
    _reconcile_fixed_roles_after_credential_change()
    return EndpointModelTestResponse(
        registry=_registry_response(latest_credentials, _load_roles_or_empty()),
        results=results,
    )


@router.post("/routes/{route_id}/probe", response_model=RegistryResponse)
async def probe_route(
    route_id: str,
    request: RouteProbeRequest,
    force: bool = False,
) -> RegistryResponse:
    """Probe one route and update normalized capability metadata."""
    credentials = load_credentials()
    route = credentials.provider_routes.get(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"Unknown route: {route_id}")
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {route.endpoint_id}")
    if force:
        await _force_probe_route(credentials, route, endpoint)
        return await _write_registry_response(load_credentials())
    capabilities = dict(route.capabilities)
    for capability in request.capabilities:
        key = _capability_key(capability)
        capabilities[key] = CapabilityValue(
            value=True,
            source="probed_verified",
            observed_at=_now_iso(),
        )
    if request.runtime_settings:
        capabilities.update(
            normalize_route_capabilities(
                protocol=endpoint.protocol,
                provider_model_id=route.provider_model_id,
                raw_capabilities=request.runtime_settings,
                source="probed_verified",
            )
        )
    updated = route.model_copy(update={"status": "verified", "capabilities": capabilities})
    credentials.provider_routes[route_id] = updated
    save_credentials(credentials)
    return await _write_registry_response(credentials)


def _multimodal_probe_candidate(
    endpoint: ProviderEndpoint,
    model_id: str,
) -> OfficialLanguageProbeCandidate | None:
    """挑一条能带图探测的调用方式:取默认候选,跳过纯文本的 openai_completions
    (gateway 对它 multimodal=True 会 ValueError)。无可用候选时返回 None。"""
    candidates = [
        candidate
        for candidate in _official_language_probe_candidates(endpoint, model_id)
        if candidate.method_id != "openai_completions"
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: (candidate.default_rank, candidate.profile_id))


@router.post("/routes/{route_id}/probe-multimodal", response_model=RegistryResponse)
async def probe_route_multimodal(route_id: str) -> RegistryResponse:
    """真塞一张测试图探测该 route 的模型是否**接受**图像输入(#11)。

    provider 接受(2xx)= 该模型 input_modalities 含 image → 把 input_modalities/
    vision 记为 probed_verified 证据;不支持 vision 的模型 4xx 拒绝 → probe-failed。
    catalog 声称(provider_doc)只是"可能带多模态"的提示,这里给出实测判据。
    """
    credentials = load_credentials()
    route = credentials.provider_routes.get(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"Unknown route: {route_id}")
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {route.endpoint_id}")
    if _endpoint_probe_is_disabled(endpoint):
        updated = route.model_copy(
            update={
                "status": "disabled",
                "metadata": {
                    **route.metadata,
                    "reason_code": _ENDPOINT_DISABLED_ERROR_CODE,
                    "last_probe_message": DISABLED_ENDPOINT_PROBE_MESSAGE,
                },
            }
        )
        credentials.provider_routes[route_id] = updated
        save_credentials(credentials)
        return await _write_registry_response(credentials)
    candidate = _multimodal_probe_candidate(endpoint, route.provider_model_id)
    if candidate is None:
        raise HTTPException(
            status_code=422,
            detail="This endpoint/model has no available call method for multimodal probing.",
        )
    result = await _probe_official_call_method(
        endpoint, route.provider_model_id, candidate, multimodal=True
    )
    _merge_probe_evidence_into_route(
        credentials, endpoint, result, route_id=route_id, multimodal=True
    )
    save_credentials(credentials)
    return await _write_registry_response(credentials)


@router.put("/routes/{route_id}", response_model=RegistryResponse)
async def put_route_metadata(route_id: str, request: RouteEditableUpdate) -> RegistryResponse:
    """Replace editable route metadata without changing identity."""
    credentials = load_credentials()
    route = credentials.provider_routes.get(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"Unknown route: {route_id}")
    updated = route.model_copy(
        update={
            "display_name": request.display_name,
            "canonical_id": request.canonical_id,
            "status": request.status,
            "capabilities": request.capabilities,
            "metadata": request.metadata,
        }
    )
    upsert_routes({route_id: updated})
    record_runtime_activity(
        source_id="llm_credentials",
        action="update_route_metadata",
        message="Updated editable route metadata.",
        changes={"route_id": route_id, "status": request.status},
    )
    return await _write_registry_response(load_credentials())


@router.delete("/routes/{route_id}", response_model=RegistryResponse)
async def delete_registry_route(route_id: str) -> RegistryResponse:
    """Delete a route unless roles/profiles still reference it."""
    roles = _load_roles_or_empty()
    refs = _route_references(route_id, roles)
    if refs["roles"] or refs["model_profiles"] or refs["model_bundles"]:
        _raise_conflict(
            "route_in_use",
            f"Route is still referenced: {route_id}",
            {"route_id": route_id, **refs},
        )
    data = delete_route(route_id)
    record_runtime_activity(
        source_id="llm_credentials",
        action="delete_route",
        message="Deleted a provider route.",
        changes={
            "route_id": route_id,
            "remaining_route_count": len(data.provider_routes),
        },
    )
    return await _write_registry_response(data)


@router.get("/roles", response_model=RolesProjectionResponse)
async def get_llm_roles() -> RolesProjectionResponse:
    """Return all route-backed roles."""
    return await _roles_projection_response(
        _load_roles_or_empty(),
        setup_required=not credentials_path().exists(),
    )


@router.put("/roles", response_model=RolesProjectionResponse)
async def put_llm_roles(request: RolesData) -> RolesProjectionResponse:
    """Upsert submitted roles; absent roles are retained."""
    current = _load_roles_or_empty()
    merged = current.model_copy(
        update={
            "roles": {**current.roles, **request.roles},
            "model_profiles": {**current.model_profiles, **request.model_profiles},
            "model_bundles": {**current.model_bundles, **request.model_bundles},
        }
    )
    credentials = load_credentials()
    materialized = _materialize_roles_for_response(merged, credentials)
    saved = _save_roles_with_active_routes(materialized)
    await _publish_roles_changed()
    record_runtime_activity(
        source_id="llm_roles",
        action="upsert_roles",
        message="Saved LLM roles, model profiles, and model bundles.",
        changes={
            "role_count": len(saved.roles),
            "model_profile_count": len(saved.model_profiles),
            "model_bundle_count": len(saved.model_bundles),
        },
    )
    return await _roles_projection_response(saved, credentials)


@router.get("/roles/test-results", response_model=RoleTestResultsResponse)
async def get_role_test_results() -> RoleTestResultsResponse:
    """R20: return the durably persisted LAST test result per role.

    The settings UI seeds role/copilot badges from this on mount so the
    last-known status survives a server restart or a tab remount; live tests
    still update + re-persist through the existing test-job endpoints. This is
    declared before ``/roles/{role_name}`` so FastAPI does not capture the
    literal ``test-results`` path segment as a role name.
    """
    persisted = load_role_test_results()
    return RoleTestResultsResponse(
        results={
            role_name: _persisted_role_test_result_from_storage(entry)
            for role_name, entry in persisted.items()
        }
    )


@router.get("/roles/{role_name}", response_model=RoleEntry)
async def get_llm_role(role_name: str) -> RoleEntry:
    """Return one role."""
    data = _load_roles_or_empty()
    try:
        return _materialize_role_for_response(get_role(data, role_name))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown LLM role: {role_name}") from exc


@router.put("/roles/{role_name}", response_model=RoleEntry)
async def put_llm_role(role_name: str, request: RoleEntry) -> RoleEntry:
    """Full replace one role."""
    data = _load_roles_or_empty()
    credentials = load_credentials()
    adapter = build_gateway_adapter()
    role = (
        adapter.materialize_role(
            {
                "role": request,
                "credentials": credentials,
            }
        )
        if request.model_groups
        else request
    )
    roles = dict(data.roles)
    roles[role_name] = role
    schema_version = 3 if role.model_groups else data.schema_version
    saved = _save_roles_with_active_routes(data.model_copy(update={"schema_version": schema_version, "roles": roles}))
    await _publish_roles_changed()
    record_runtime_activity(
        source_id="llm_roles",
        action="upsert_role",
        message="Saved one LLM role.",
        changes={"role_name": role_name, "schema_version": schema_version},
    )
    return _materialize_role_for_response(saved.roles[role_name], credentials)


@router.get("/fixed-roles")
async def get_fixed_role_names() -> dict[str, list[str]]:
    """固定角色名(不可删除、不可改名)。前端据此隐藏删除/改名入口。"""
    from app.services.llm_fixed_roles import fixed_role_names

    return {"fixed_role_names": sorted(fixed_role_names())}


@router.get("/fixed-roles/{role_name}")
async def get_fixed_role_status(role_name: str) -> dict[str, Any]:
    """固定角色的推荐模型清单(canonical_id + 展示名)。说明文案归前端 i18n;缺哪个
    推荐模型由前端拿当前内存里的角色状态实时算(不走后端读盘,避免防抖存盘前的竞态)。"""
    from app.services.llm_fixed_roles import (
        is_fixed_role,
        recommended_model_display_name,
        recommended_models_for_role,
    )

    if not is_fixed_role(role_name):
        raise HTTPException(status_code=404, detail=f"Not a fixed role: {role_name}")
    return {
        "recommended_models": [
            {"canonical_id": canonical_id, "display_name": recommended_model_display_name(role_name, canonical_id)}
            for canonical_id in recommended_models_for_role(role_name)
        ],
    }


@router.delete("/roles/{role_name}", response_model=RolesProjectionResponse)
async def delete_llm_role(role_name: str) -> RolesProjectionResponse:
    """Delete one persisted role."""
    from app.services.llm_fixed_roles import is_fixed_role

    data = _load_roles_or_empty()
    if role_name not in data.roles:
        raise HTTPException(status_code=404, detail=f"Unknown LLM role: {role_name}")
    if is_fixed_role(role_name):
        # 固定角色(引擎 builtin 硬依赖 / 内置 copilot)删了就跑不起来。
        raise HTTPException(
            status_code=409,
            detail=f"Fixed roles cannot be deleted: {role_name}",
        )
    roles = dict(data.roles)
    del roles[role_name]
    credentials = load_credentials()
    saved = _save_roles_with_active_routes(data.model_copy(update={"roles": roles}))
    await _publish_roles_changed()
    record_runtime_activity(
        source_id="llm_roles",
        action="delete_role",
        message="Deleted one LLM role.",
        changes={"role_name": role_name, "remaining_role_count": len(saved.roles)},
    )
    return await _roles_projection_response(saved, credentials)


@router.post("/roles/{role_name}/test")
async def test_llm_role(role_name: str, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a minimal persisted-role fallback test; request payload is ignored."""
    del _payload
    data = _load_roles_or_empty()
    role = data.roles.get(role_name)
    if role is None:
        raise HTTPException(status_code=404, detail=f"Unknown LLM role: {role_name}")
    credentials = load_credentials()
    role = _materialize_role_for_response(role, credentials)
    return await _run_role_test_targets(role_name, _role_test_targets(role, credentials))


@router.post("/roles/{role_name}/test-jobs", response_model=RoleTestJobResponse)
async def start_role_test_job(role_name: str) -> RoleTestJobResponse:
    """Start a persisted-role fallback test job with per-route progress."""
    data = _load_roles_or_empty()
    role = data.roles.get(role_name)
    if role is None:
        raise HTTPException(status_code=404, detail=f"Unknown LLM role: {role_name}")
    credentials = load_credentials()
    role = _materialize_role_for_response(role, credentials)
    # COPILOT_ASSIST-4: copilot's test走 copilot 自己的真实 ClaudeSDKClient 调用
    # (发真工具调用、验 spawn/env/tool loop), not the httpx connectivity probe.
    if role.role_kind == "copilot":
        return await _start_copilot_sdk_test_job(role_name)
    targets = _role_test_targets(role, credentials)
    job_id = str(uuid.uuid4())
    job = RoleTestJobResponse(
        job_id=job_id,
        role_name=role_name,
        status="queued",
        message="Queued role test.",
        provider_statuses=[_role_test_provider_progress(target, "queued") for target in targets],
    )
    async with _role_test_jobs_lock:
        _role_test_jobs[job_id] = job
    _spawn_background_task(_run_role_test_job_impl(job_id, role_name, targets))
    return job


@router.post("/model-bundles/{bundle_id}/test-jobs", response_model=RoleTestJobResponse)
async def start_bundle_test_job(bundle_id: str) -> RoleTestJobResponse:
    """Start a bundle fallback test job, mirroring the role test (#50b).

    The bundle is resolved through ``materialize_model_bundle`` which wraps it into
    a TRANSIENT, never-persisted role-like entry — so the persisted roles store is
    not polluted. The job is keyed under ``__bundle__{id}`` so its result lands in
    the bundle namespace of the role-test results store, away from real roles.
    """
    data = _load_roles_or_empty()
    bundle = data.model_bundles.get(bundle_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"Unknown model bundle: {bundle_id}")
    credentials = load_credentials()
    materialized = _materialize_bundle_for_response(bundle, credentials)
    job_role_name = bundle_role_name(bundle_id)
    targets = _build_role_test_targets(materialized, credentials)
    job_id = str(uuid.uuid4())
    job = RoleTestJobResponse(
        job_id=job_id,
        role_name=job_role_name,
        status="queued",
        message="Queued bundle test.",
        provider_statuses=[_role_test_provider_progress(target, "queued") for target in targets],
    )
    async with _role_test_jobs_lock:
        _role_test_jobs[job_id] = job
    _spawn_background_task(_run_role_test_job_impl(job_id, job_role_name, targets))
    return job


@router.post("/model-groups/test-jobs", response_model=RoleTestJobResponse)
async def start_compare_candidate_test_job(request: CompareCandidateTestRequest) -> RoleTestJobResponse:
    """Start a transient node compare-candidate test job without persisting a role."""
    credentials = load_credentials()
    role = _compare_candidate_role(request, credentials)
    materialized = _materialize_role_for_response(role, credentials)
    targets = _build_role_test_targets(materialized, credentials)
    if not targets:
        raise HTTPException(
            status_code=404,
            detail=f"No testable route found for compare candidate: {request.canonical_id}",
        )
    job_id = str(uuid.uuid4())
    job_role_name = compare_candidate_role_name(request)
    job = RoleTestJobResponse(
        job_id=job_id,
        role_name=job_role_name,
        status="queued",
        message="Queued compare candidate test.",
        provider_statuses=[_role_test_provider_progress(target, "queued") for target in targets],
    )
    async with _role_test_jobs_lock:
        _role_test_jobs[job_id] = job
    _spawn_background_task(
        _run_role_test_job_impl(job_id, job_role_name, targets, persist_result=False)
    )
    return job


@router.get("/role-test-jobs/{job_id}", response_model=RoleTestJobResponse)
async def get_role_test_job(job_id: str) -> RoleTestJobResponse:
    """Return compact status for a role test job."""
    async with _role_test_jobs_lock:
        job = _role_test_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown role test job: {job_id}")
    return job


def _role_test_targets(
    role: RoleEntry,
    credentials: LLMCredentialsFile,
) -> list[RoleTestTarget]:
    return _build_role_test_targets(role, credentials)


def _build_role_test_targets(
    materialized: RoleEntry | ModelBundle,
    credentials: LLMCredentialsFile,
) -> list[RoleTestTarget]:
    """Build per-route probe targets from a materialized role OR model bundle.

    #50b: a materialized ModelBundle carries the same fallback_chain +
    materialization_report shape a materialized role does, so the bundle Test path
    (start_bundle_test_job) reuses this exact builder — one source of truth for the
    role and bundle test orchestration.
    """
    targets: list[RoleTestTarget] = []
    for report_entry, fallback_entry in _role_test_entries(materialized):
        route_id = report_entry["route_id"]
        route = credentials.provider_routes.get(route_id)
        if route is None:
            continue
        endpoint = credentials.provider_endpoints.get(route.endpoint_id)
        if endpoint is None:
            continue
        targets.append(
            RoleTestTarget(
                report_entry=report_entry,
                route=route,
                endpoint=endpoint,
                entry=fallback_entry,
            )
        )
    return targets


async def _run_role_test_targets(
    role_name: str,
    targets: list[RoleTestTarget],
    on_provider_status: Callable[
        [
            RoleTestTarget,
            Literal["testing", "ok", "failed", "blocked", "untested"],
            str | None,
        ],
        Awaitable[None],
    ]
    | None = None,
) -> dict[str, Any]:
    model_groups: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []
    aggregate_status = "ok"

    async def run_target(target: RoleTestTarget) -> dict[str, Any]:
        if on_provider_status is not None:
            await on_provider_status(target, "testing", None)
        provider_result = await _role_test_provider_result(
            target.entry,
            target.report_entry,
            target.route,
            target.endpoint,
        )
        if on_provider_status is not None:
            await on_provider_status(
                target,
                cast(
                    Literal["testing", "ok", "failed", "blocked", "untested"],
                    provider_result["status"],
                ),
                provider_result.get("message"),
            )
        return provider_result

    provider_results = await asyncio.gather(*(run_target(target) for target in targets))
    for target, provider_result in zip(
        targets,
        provider_results,
        strict=True,
    ):
        if provider_result["warnings"]:
            warnings.extend(provider_result["warnings"])
        aggregate_status = _merge_role_test_status(aggregate_status, provider_result)
        canonical_id = str(target.report_entry.get("canonical_id") or target.route.canonical_id)
        identity = project_model_identity(route=target.route, endpoint=target.endpoint)
        group = model_groups.setdefault(
            canonical_id,
            {
                "canonical_id": canonical_id,
                "display_name": identity.display_name,
                "provider_results": [],
            },
        )
        group["provider_results"].append(provider_result)
    return {
        "role_name": role_name,
        "status": aggregate_status,
        "warnings": warnings,
        "model_groups": list(model_groups.values()),
    }


async def _run_role_test_job_impl(
    job_id: str,
    role_name: str,
    targets: list[RoleTestTarget],
    *,
    persist_result: bool = True,
) -> None:
    await _update_role_test_job(
        job_id,
        status="running",
        message="Testing role routes.",
    )

    async def on_provider_status(
        target: RoleTestTarget,
        status: Literal["testing", "ok", "failed", "blocked", "untested"],
        message: str | None,
    ) -> None:
        await _update_role_test_job_provider(job_id, target, status, message)

    try:
        result = await _run_role_test_targets(
            role_name,
            targets,
            on_provider_status=on_provider_status,
        )
    except Exception as exc:  # pragma: no cover - defensive job boundary
        logger.exception("Role test job failed: %s", job_id)
        await _update_role_test_job(
            job_id,
            status="failed",
            message=str(exc),
        )
        return

    if persist_result:
        _persist_completed_role_test_result(role_name, result)
    await _update_role_test_job(
        job_id,
        status="completed",
        message="Role test completed.",
        result=result,
    )


def _role_test_provider_progress(
    target: RoleTestTarget,
    status: Literal["queued", "testing", "ok", "failed", "blocked", "untested"],
    message: str | None = None,
) -> RoleTestProviderProgressInfo:
    return RoleTestProviderProgressInfo(
        canonical_id=str(target.report_entry.get("canonical_id") or target.route.canonical_id),
        route_id=target.route.route_id,
        status=status,
        message=message,
    )


async def _update_role_test_job(
    job_id: str,
    **updates: Any,
) -> None:
    async with _role_test_jobs_lock:
        current = _role_test_jobs.get(job_id)
        if current is None:
            return
        _role_test_jobs[job_id] = current.model_copy(update=updates)


async def _update_role_test_job_provider(
    job_id: str,
    target: RoleTestTarget,
    status: Literal["testing", "ok", "failed", "blocked", "untested"],
    message: str | None,
) -> None:
    async with _role_test_jobs_lock:
        current = _role_test_jobs.get(job_id)
        if current is None:
            return
        provider_statuses = [
            _role_test_provider_progress(target, status, message)
            if provider.route_id == target.route.route_id
            else provider
            for provider in current.provider_statuses
        ]
        _role_test_jobs[job_id] = current.model_copy(update={"provider_statuses": provider_statuses})


# COPILOT_ASSIST-4: copilot test orchestration — resolve the role's routes via the
# gateway role→routes API, run the real ClaudeSDKClient tool-call test per route
# (full fallback chain, bounded concurrency), and project per-route lights +
# structured sdk_evidence into the same job contract the LLM-Roles UI consumes.
_COPILOT_SDK_TEST_CONCURRENCY = 2
_COPILOT_SDK_SUPPORTED_METHOD_IDS = copilot.COPILOT_SDK_SUPPORTED_METHOD_IDS
_NO_COPILOT_COMPATIBLE_OFFICIAL_PROFILE_MESSAGE = (
    "No verified Anthropic Messages profile is available for this official route. "
    "Run the route profile test in API Keys, then retry Copilot Test."
)


def _human_message_for_error_code(error_code: str | None, role_name: str) -> str:
    """R-F9: map gateway error codes to human-readable English copilot test
    toast messages. Raw `ResourceTerminalError: resource.no_available_route`
    leaks an internal exception class name + dict payload to the user; this
    helper returns a sentence the operator can act on.

    Front-end `ERROR_CODE_MAP` in `copilot-role-test.ts` mirrors this table
    for the cases where the FE chooses the fallback message (e.g. transport
    error before the BE could attach `error_code`).
    """
    if error_code == "resource.no_available_route":
        return (
            f"{role_name} has no available model route. Configure and test an "
            "Anthropic-compatible credential in API Keys first."
        )
    if error_code == "resource.role_unknown":
        return f"{role_name} does not exist or was deleted. Refresh the page and try again."
    if error_code == "resource.role_invalid_kind":
        return f"{role_name} is not a copilot role, so it cannot be tested with Claude SDK."
    if error_code == "resource.credential_missing":
        return f"{role_name} is missing a required API key. Fill it in API Keys and retry."
    if error_code:
        return f"{role_name} test failed ({error_code})"
    return f"{role_name} test failed: could not resolve model routes."


async def _start_copilot_sdk_test_job(role_name: str) -> RoleTestJobResponse:
    job_id = str(uuid.uuid4())
    try:
        routes, credential_provider = _resolve_copilot_test_routes(role_name)
    except Exception as exc:  # noqa: BLE001 — surfaced as a failed job, not swallowed
        logger.warning("copilot SDK test: cannot resolve routes for %s: %s", role_name, exc)
        error_code = getattr(exc, "error_code", None)
        error_payload = getattr(exc, "error_payload", None)
        if not isinstance(error_payload, dict):
            error_payload = None
        # R-F9: replace the raw `f'无法解析 copilot 路线: {exc}'` (which leaks
        # the exception class name and a Python-repr payload) with the human
        # message derived from the gateway error code. `error_code` +
        # `error_payload` stay on the job for FE debugging.
        message = _human_message_for_error_code(error_code, role_name)
        job = RoleTestJobResponse(
            job_id=job_id,
            role_name=role_name,
            status="failed",
            message=message,
            error_code=error_code,
            error_payload=error_payload,
            provider_statuses=[],
            result=_build_copilot_sdk_result(role_name, [], []),
        )
        async with _role_test_jobs_lock:
            _role_test_jobs[job_id] = job
        return job
    job = RoleTestJobResponse(
        job_id=job_id,
        role_name=role_name,
        status="queued",
        message="Queued copilot SDK test.",
        provider_statuses=[_copilot_route_progress(route, "queued") for route in routes],
    )
    async with _role_test_jobs_lock:
        _role_test_jobs[job_id] = job
    _spawn_background_task(
        _run_copilot_sdk_test_job(job_id, role_name, routes, credential_provider)
    )
    return job


def _resolve_copilot_test_routes(
    role_name: str,
) -> tuple[list[ResolvedRoute], CredentialProviderProtocol]:
    runtime = build_gateway_route_runtime(role_name)
    if not runtime.routes:
        raise ResourceTerminalError(
            runtime.error_code or "resource.no_available_route",
            runtime.error_payload or {"role": role_name},
        )
    return runtime.routes, runtime.credential_provider


def _copilot_route_progress(
    route: ResolvedRoute,
    status: Literal[
        "queued", "testing", "ok", "failed", "blocked", "untested", "cooling_down"
    ],
    message: str | None = None,
    retry_after_seconds: int | None = None,
) -> RoleTestProviderProgressInfo:
    return RoleTestProviderProgressInfo(
        canonical_id=route.canonical_id,
        route_id=route.route_id,
        status=status,
        message=_copilot_diagnostic_text(message),
        retry_after_seconds=retry_after_seconds,
    )


async def _run_copilot_sdk_test_job(
    job_id: str,
    role_name: str,
    routes: list[ResolvedRoute],
    credential_provider: CredentialProviderProtocol,
) -> None:
    await _update_role_test_job(job_id, status="running", message="Testing copilot SDK routes.")
    semaphore = asyncio.Semaphore(_COPILOT_SDK_TEST_CONCURRENCY)

    async def test_route(route: ResolvedRoute) -> copilot.RouteSdkTestResult:
        async with semaphore:
            await _update_copilot_route(job_id, route, "testing", None)
            route_provider = credential_provider
            try:
                route, route_provider, prepare_error = await _prepare_copilot_sdk_test_route(
                    role_name,
                    route,
                    credential_provider,
                )
            except Exception as exc:  # noqa: BLE001 — surfaced on this route light
                prepare_error = str(exc)
            if prepare_error:
                result = copilot.RouteSdkTestResult(route.route_id, "failed", prepare_error)
            else:
                result = await copilot.run_route_sdk_test(route, route_provider)
            # R-F21: surface cooling_down + retry_after_seconds so the FE Test
            # Button can show "Cooling down {n}s" and stay disabled.
            await _update_copilot_route(
                job_id,
                route,
                result.status,
                result.message,
                retry_after_seconds=result.retry_after_seconds,
            )
            return result

    try:
        results = await asyncio.gather(*(test_route(route) for route in routes))
    except Exception as exc:  # pragma: no cover - defensive job boundary
        logger.exception("Copilot SDK test job failed: %s", job_id)
        await _update_role_test_job(
            job_id,
            status="failed",
            message=_copilot_diagnostic_text(str(exc)) or "Copilot SDK test failed.",
        )
        return

    results_list = list(results)
    try:
        _persist_copilot_sdk_evidence(results_list)
    except Exception as exc:  # noqa: BLE001 — evidence persistence is best-effort
        logger.warning("copilot SDK evidence persist failed (non-fatal): %s", exc)

    copilot_result = _build_copilot_sdk_result(role_name, routes, results_list)
    _persist_completed_role_test_result(role_name, copilot_result)
    await _update_role_test_job(
        job_id,
        status="completed",
        message="Copilot SDK test completed.",
        result=copilot_result,
    )


async def _update_copilot_route(
    job_id: str,
    route: ResolvedRoute,
    status: Literal["testing", "ok", "failed", "blocked", "untested", "cooling_down"],
    message: str | None,
    retry_after_seconds: int | None = None,
) -> None:
    async with _role_test_jobs_lock:
        current = _role_test_jobs.get(job_id)
        if current is None:
            return
        provider_statuses = [
            _copilot_route_progress(route, status, message, retry_after_seconds)
            if provider.route_id == route.route_id
            else provider
            for provider in current.provider_statuses
        ]
        _role_test_jobs[job_id] = current.model_copy(
            update={"provider_statuses": provider_statuses}
        )


async def _prepare_copilot_sdk_test_route(
    role_name: str,
    route: ResolvedRoute,
    credential_provider: CredentialProviderProtocol,
) -> tuple[ResolvedRoute, CredentialProviderProtocol, str | None]:
    if copilot.resolved_route_has_copilot_sdk_method(route):
        return route, credential_provider, None
    candidate_route = copilot.resolved_route_with_copilot_sdk_candidate_method(route)
    if copilot.resolved_route_has_copilot_sdk_method(candidate_route):
        return candidate_route, credential_provider, None
    endpoint_id = getattr(route, "endpoint_id", None)
    route_id = getattr(route, "route_id", None)
    if not isinstance(endpoint_id, str) or not isinstance(route_id, str):
        return route, credential_provider, None
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    stored_route = credentials.provider_routes.get(route_id)
    if endpoint is None or stored_route is None or endpoint.provider_kind != "official":
        return route, credential_provider, None

    updated_route, profile_result = await _ensure_official_role_test_verified_profile(
        stored_route,
        endpoint,
        required_method_ids=_COPILOT_SDK_SUPPORTED_METHOD_IDS,
    )
    if profile_result is not None and not profile_result.profiles:
        return route, credential_provider, _official_role_test_profile_probe_failure_message(profile_result)
    selected_profile = copilot.select_copilot_sdk_verified_profile(updated_route)
    if selected_profile is None:
        return route, credential_provider, _NO_COPILOT_COMPATIBLE_OFFICIAL_PROFILE_MESSAGE

    runtime = build_gateway_route_runtime(role_name, route_override=route_id)
    if not runtime.routes:
        return route, credential_provider, "Route could not be resolved after profile probing."
    return (
        copilot.resolved_route_with_verified_profile(runtime.routes[0], selected_profile),
        runtime.credential_provider,
        None,
    )


def _build_copilot_sdk_result(
    role_name: str,
    routes: list[ResolvedRoute],
    results: list[copilot.RouteSdkTestResult],
) -> dict[str, Any]:
    passed = sum(1 for result in results if result.status == "ok")
    # Copilot only needs one working route at runtime (fallback chain), so any
    # passing route makes the role usable.
    overall = "ok" if passed > 0 else "failed"
    # R-F21: persist retry_after_seconds alongside cooling_down so a remount
    # can re-hydrate the gray light + countdown (R20 seed path).
    routes_evidence = {
        result.route_id: {
            "status": result.status,
            "message": _copilot_diagnostic_text(result.message),
            "retry_after_seconds": result.retry_after_seconds,
        }
        for result in results
    }
    return {
        "role_name": role_name,
        "status": overall,
        "warnings": [],
        "model_groups": _copilot_sdk_model_groups(routes, results),
        "sdk_evidence": {
            "tested": bool(results),
            "passed": passed,
            "total": len(results),
            "routes": routes_evidence,
        },
    }


def _copilot_sdk_model_groups(
    routes: list[ResolvedRoute],
    results: list[copilot.RouteSdkTestResult],
) -> list[dict[str, Any]]:
    by_route = {result.route_id: result for result in results}
    groups: dict[str, list[dict[str, Any]]] = {}
    for route in routes:
        result = by_route.get(route.route_id)
        groups.setdefault(route.canonical_id, []).append(
            {
                "route_id": route.route_id,
                "status": result.status if result else "untested",
                "message": _copilot_diagnostic_text(result.message) if result else None,
            }
        )
    return [
        {"canonical_id": canonical_id, "provider_results": provider_results}
        for canonical_id, provider_results in groups.items()
    ]


def _persist_copilot_sdk_evidence(results: list[copilot.RouteSdkTestResult]) -> None:
    # COPILOT_ASSIST-4: write the high-order SDK tool-call evidence back to
    # credentials so the route's verified state survives reload and isn't
    # re-derived from a transient run (§3.4 "成功写高阶证据回 credentials").
    credentials = load_credentials()
    verified_at = datetime.now(UTC).isoformat()
    changed = False
    for result in results:
        route = credentials.provider_routes.get(result.route_id)
        if route is None:
            continue
        metadata = dict(route.metadata)
        metadata["sdk_tool_call_verified"] = {
            "verified": result.status == "ok",
            "status": result.status,
            "verified_at": verified_at,
        }
        credentials.provider_routes[result.route_id] = route.model_copy(
            update={"metadata": metadata}
        )
        changed = True
    if changed:
        save_credentials(credentials)
        logger.info("copilot SDK evidence persisted for %d route(s)", len(results))


def _role_test_route_results(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a role/copilot test result into per-route facts for the runtime log."""
    route_results: list[dict[str, Any]] = []
    model_groups = result.get("model_groups")
    if not isinstance(model_groups, list):
        return route_results
    for group in model_groups:
        if not isinstance(group, dict):
            continue
        provider_results = group.get("provider_results")
        if not isinstance(provider_results, list):
            continue
        for provider_result in provider_results:
            if not isinstance(provider_result, dict):
                continue
            route_results.append(
                {
                    "canonical_id": group.get("canonical_id"),
                    "route_id": provider_result.get("route_id"),
                    "provider": provider_result.get("provider_label"),
                    "status": provider_result.get("status"),
                    "message": provider_result.get("message"),
                }
            )
    return route_results


def _persist_completed_role_test_result(role_name: str, result: dict[str, Any]) -> None:
    """R20: durably persist the LAST completed role/copilot test result per role.

    Role-test jobs live in transient in-memory dicts; persisting the finished
    result keyed by role name lets the settings UI re-seed badges after a
    server restart or a tab remount instead of resetting to untested.
    """
    status = str(result.get("status") or "")
    message = result.get("message")
    try:
        save_role_test_result(
            role_name,
            result,
            status=status,
            message=message if isinstance(message, str) else None,
        )
        record_runtime_activity(
            source_id="llm_role_test_results",
            action="role_test_result_saved",
            message="Saved the latest role or copilot test result.",
            # The Runtime log is the diagnostic trail: it must carry the same
            # per-route facts as the persisted truth file, not just "failed".
            changes={
                "role_name": role_name,
                "status": status,
                "route_results": _role_test_route_results(result),
            },
        )
    except Exception as exc:  # noqa: BLE001 — persistence is best-effort, never fail the job
        logger.warning(
            "role test result persist failed (non-fatal) role=%s: %s", role_name, exc
        )


@router.get("/model-profiles")
async def get_model_profiles() -> dict[str, ModelProfile]:
    """Return model profiles."""
    return _load_roles_or_empty().model_profiles


@router.put("/model-profiles", response_model=RolesProjectionResponse)
async def put_model_profiles(profiles: dict[str, ModelProfile]) -> RolesProjectionResponse:
    """Replace model profile set."""
    data = _load_roles_or_empty().model_copy(update={"model_profiles": profiles})
    credentials = load_credentials()
    saved = _save_roles_with_active_routes(data)
    await _publish_roles_changed()
    record_runtime_activity(
        source_id="llm_roles",
        action="replace_model_profiles",
        message="Replaced LLM model profiles.",
        changes={"model_profile_count": len(saved.model_profiles)},
    )
    return await _roles_projection_response(saved, credentials)


@router.delete("/model-bundles/{bundle_id}", response_model=RolesProjectionResponse)
async def delete_model_bundle(bundle_id: str) -> RolesProjectionResponse:
    """Delete one persisted model bundle and cascade off referencing roles.

    #51/#52 delete cascade: the bundle is the source of truth. When it is removed,
    a role that referenced it (bundle_id) must drop that reference (no dangling
    failed snapshot is kept); on re-materialization the role loses that chain and
    may become not-fit. The local delta on routes that no longer exist is
    discarded with the reference.
    """
    data = _load_roles_or_empty()
    bundles = dict(data.model_bundles)
    removed = bundles.pop(bundle_id, None)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"Unknown model bundle: {bundle_id}")
    del removed
    roles = {
        role_name: (
            role.model_copy(update={"bundle_id": None, "fallback_chain": []})
            if role.bundle_id == bundle_id
            else role
        )
        for role_name, role in data.roles.items()
    }
    credentials = load_credentials()
    saved = _save_roles_with_active_routes(
        data.model_copy(update={"model_bundles": bundles, "roles": roles})
    )
    await _publish_roles_changed()
    record_runtime_activity(
        source_id="llm_roles",
        action="delete_model_bundle",
        message="Deleted one LLM model bundle.",
        changes={"bundle_id": bundle_id, "remaining_model_bundle_count": len(saved.model_bundles)},
    )
    return await _roles_projection_response(saved, credentials)


@router.delete("/model-profiles/{model_profile_id}", response_model=RolesProjectionResponse)
async def delete_model_profile(model_profile_id: str) -> RolesProjectionResponse:
    """Delete profile and mark roles that still show its source snapshot."""
    data = _load_roles_or_empty()
    profiles = dict(data.model_profiles)
    removed = profiles.pop(model_profile_id, None)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"Unknown model profile: {model_profile_id}")
    credentials = load_credentials()
    roles = {}
    for role_name, role in data.roles.items():
        if role.source_profile_id == model_profile_id:
            snapshot = dict(role.source_profile_snapshot or {})
            snapshot.update(
                {
                    "model_profile_id": model_profile_id,
                    "display_name": removed.display_name,
                    "deleted_at": _now_iso(),
                    "deleted_marker": True,
                }
            )
            roles[role_name] = role.model_copy(update={"source_profile_id": None, "source_profile_snapshot": snapshot})
        else:
            roles[role_name] = role
    saved = _save_roles_with_active_routes(data.model_copy(update={"model_profiles": profiles, "roles": roles}))
    await _publish_roles_changed()
    record_runtime_activity(
        source_id="llm_roles",
        action="delete_model_profile",
        message="Deleted one LLM model profile.",
        changes={
            "model_profile_id": model_profile_id,
            "remaining_model_profile_count": len(saved.model_profiles),
        },
    )
    return await _roles_projection_response(saved, credentials)


@router.post("/roles/{role_name}/apply-profile", response_model=RoleEntry)
async def apply_model_profile(
    role_name: str,
    request: RoleApplyProfileRequest,
) -> RoleEntry:
    """Apply one profile into a role fallback chain."""
    data = _load_roles_or_empty()
    role = data.roles.get(role_name)
    profile = data.model_profiles.get(request.model_profile_id)
    if role is None:
        raise HTTPException(status_code=404, detail=f"Unknown LLM role: {role_name}")
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown model profile: {request.model_profile_id}",
        )
    snapshot_route_ids = (role.source_profile_snapshot or {}).get("route_ids")
    if (
        request.mode != "replace"
        and role.source_profile_id
        and isinstance(snapshot_route_ids, list)
        and snapshot_route_ids != [entry.route_id for entry in role.fallback_chain]
    ):
        _raise_conflict(
            "profile_apply_conflict",
            f"Role has drifted since profile was applied: {role_name}",
            {
                "role_name": role_name,
                "model_profile_id": request.model_profile_id,
                "current_route_ids": [entry.route_id for entry in role.fallback_chain],
                "profile_route_ids": [entry.route_id for entry in profile.fallback_chain],
            },
        )
    snapshot = {
        "model_profile_id": profile.model_profile_id,
        "display_name": profile.display_name,
        "route_ids": [entry.route_id for entry in profile.fallback_chain],
        "applied_at": _now_iso(),
        "deleted_at": None,
        "deleted_marker": False,
    }
    updated = role.model_copy(
        update={
            "source_profile_id": request.model_profile_id,
            "source_profile_snapshot": snapshot,
            "fallback_chain": [
                entry.model_copy(update={"runtime_settings_source": "profile_default"})
                for entry in profile.fallback_chain
            ],
            "lint_requirements": dict(profile.lint_requirements),
        }
    )
    roles = dict(data.roles)
    roles[role_name] = updated
    saved = _save_roles_with_active_routes(data.model_copy(update={"roles": roles}))
    await _publish_roles_changed()
    record_runtime_activity(
        source_id="llm_roles",
        action="apply_model_profile",
        message="Applied one LLM model profile to a role.",
        changes={"role_name": role_name, "model_profile_id": request.model_profile_id},
    )
    return saved.roles[role_name]


def _project_endpoint_provider_identities(
    credentials: LLMCredentialsFile,
) -> LLMCredentialsFile:
    """Stamp each endpoint's registrable-domain provider identity (W3-B.4 / R-B7).

    Derived from ``base_url`` (eTLD+1) at projection time — the SAME function that
    attributes probe evidence — so the UI can show the provider id under its display
    alias and it is guaranteed to match the evidence. Never persisted.
    """
    projected = {
        endpoint_id: endpoint.model_copy(
            update={
                "registrable_provider_name": (
                    registrable_provider_name(endpoint.base_url)
                    if endpoint.base_url
                    else None
                )
            }
        )
        for endpoint_id, endpoint in credentials.provider_endpoints.items()
    }
    return credentials.model_copy(update={"provider_endpoints": projected})


def _registry_response(
    credentials: LLMCredentialsFile,
    roles: RolesData,
    *,
    setup_required: bool = False,
) -> RegistryResponse:
    # R7-D: snapshot the circuit-breaker health store ONCE for the whole build —
    # every route's cooldown state is then an O(1) in-memory lookup instead of a
    # fresh SQLite connection per route (the table itself is almost always empty;
    # the old code paid a full connect+schema-ensure+query per route regardless).
    circuits_index = ActiveCircuitsIndex.build(_health_store().get_all_active_circuits())
    credentials = _normalize_credentials_for_registry_response(credentials)
    credentials = _project_route_ui_states(credentials, circuits_index=circuits_index)
    credentials = _project_endpoint_provider_identities(credentials)
    roles = _materialize_roles_for_response(roles, credentials)
    routes_by_canonical: dict[str, list[str]] = {}
    for route_id, route in credentials.provider_routes.items():
        routes_by_canonical.setdefault(route.canonical_id, []).append(route_id)
    lint_results = []
    for role_name, role in roles.roles.items():
        role_routes: list[ProviderRoute] = []
        for entry in role.fallback_chain:
            role_route = credentials.provider_routes.get(entry.route_id)
            if role_route is not None:
                role_routes.append(role_route)
        lint_results.extend(
            lint_role_routes(
                role_name,
                cast(GatewayRoleEntry, role),
                cast(list[GatewayProviderRoute], role_routes),
            )
    )
    # R9.6: the legacy remote-probe-catalog source is retired — the registry no longer
    # projects it (catalog_source stays None below).
    probe_catalog = _probe_catalog_summary()
    return RegistryResponse(
        provider_endpoints=credentials.provider_endpoints,
        provider_routes=credentials.provider_routes,
        runtime_policy=credentials.runtime_policy,
        model_profiles=roles.model_profiles,
        roles=roles.roles,
        canonical_groups=[
            {
                "canonical_id": canonical_id,
                "display_name": canonical_id,
                "routes": route_ids,
            }
            for canonical_id, route_ids in sorted(routes_by_canonical.items())
        ],
        model_groups=_model_groups_response(credentials, circuits_index=circuits_index),
        lint_results=lint_results,
        route_runtime_settings={
            route_id: build_runtime_setting_descriptors(route)
            for route_id, route in credentials.provider_routes.items()
        },
        catalog_source=None,
        probe_catalog=probe_catalog,
        role_effective_runtime_settings=_role_effective_runtime_settings(credentials, roles),
        setup_required=setup_required,
    )


def _probe_catalog_summary() -> ProbeCatalogSummary:
    # Counts derive from credentials route.evidence (SSOT, R9.2) — probe-only, so a
    # migrated provider-list-observed record never inflates "Local probe evidence".
    credentials = load_credentials()
    counts = probe_evidence_counts(credentials)
    # Phase 5: the community summary is also derived from credentials — record_count is
    # the number of community-provenance evidence records actually MERGED into routes
    # (not a remote total), and synced/generated_at come from the last-sync marker.
    community_count = sum(
        1
        for route in credentials.provider_routes.values()
        for ev in route.evidence
        if ev.metadata.get("provenance") == COMMUNITY_PROVENANCE
    )
    marker = credentials.last_remote_catalog_sync
    return ProbeCatalogSummary(
        local_evidence_records_count=counts.probe_records,
        local_verified_records_count=counts.verified,
        local_failed_records_count=counts.failed,
        local_route_candidates_count=counts.routes,
        remote_catalog_source=None,  # R9.6: legacy remote probe-catalog source retired
        community_catalog=CommunityCatalogSummary(
            synced=marker is not None,
            generated_at=marker.generated_at if marker else None,
            record_count=community_count,
        ),
    )


def _project_route_ui_states(
    credentials: LLMCredentialsFile,
    *,
    circuits_index: ActiveCircuitsIndex,
) -> LLMCredentialsFile:
    """Stamp each route's 6-state ``ui_state`` onto the registry DTO (apikeys#30).

    The registry snapshot must carry the same 6-state vocabulary LLM Roles already
    shows, so the API Keys cards can render the authoritative state inline instead
    of recomputing it. We reuse the canonical gateway projector via the in-process
    adapter (``project_route_state``) — the identical call ``_provider_model_option``
    makes — and never invent a new state vocabulary here.

    ``circuits_index`` is a snapshot built ONCE per registry request (R7-D) — a
    route's cooldown state is an O(1) lookup against it, not a fresh query.
    """
    if not credentials.provider_routes:
        return credentials
    adapter = build_gateway_adapter()
    now = datetime.now(UTC)
    projected_routes: dict[str, ProviderRoute] = {}
    changed = False
    for route_id, route in credentials.provider_routes.items():
        endpoint = credentials.provider_endpoints.get(route.endpoint_id)
        if endpoint is None:
            projected_routes[route_id] = route
            continue
        circuits = circuits_index.for_route(
            route_id=route.route_id,
            endpoint_id=endpoint.endpoint_id,
            rate_limit_bucket=endpoint.rate_limit_bucket or endpoint.endpoint_id,
        )
        projection = adapter.project_route_state(
            {
                "endpoint": endpoint,
                "route": route,
                "circuits": circuits,
                "now": now,
            }
        )
        if (
            projection.ui_state == route.ui_state
            and projection.reason_code == route.reason_code
            and projection.retry_at == route.retry_at
        ):
            projected_routes[route_id] = route
            continue
        # W2-A: stamp the authoritative ui_state AND its companions reason_code / retry_at
        # so the frontend reads them directly (no message-text re-derivation).
        projected_routes[route_id] = route.model_copy(
            update={
                "ui_state": projection.ui_state,
                "reason_code": projection.reason_code,
                "retry_at": projection.retry_at,
            }
        )
        changed = True
    if not changed:
        return credentials
    return credentials.model_copy(update={"provider_routes": projected_routes})


def _normalize_credentials_for_registry_response(
    credentials: LLMCredentialsFile,
) -> LLMCredentialsFile:
    provider_endpoints: dict[str, ProviderEndpoint] = {}
    provider_routes: dict[str, ProviderRoute] = {}
    changed = False
    for endpoint_id, endpoint in credentials.provider_endpoints.items():
        normalized_endpoint = _normalize_endpoint_metadata_for_registry_response(endpoint)
        provider_endpoints[endpoint_id] = normalized_endpoint
        changed = changed or normalized_endpoint is not endpoint
    for route_id, route in credentials.provider_routes.items():
        route_endpoint = provider_endpoints.get(route.endpoint_id)
        normalized_route = _normalize_route_for_registry_response(route, route_endpoint)
        provider_routes[route_id] = normalized_route
        changed = changed or normalized_route is not route
    if not changed:
        return credentials
    return credentials.model_copy(
        update={
            "provider_endpoints": provider_endpoints,
            "provider_routes": provider_routes,
        }
    )


def _normalize_route_for_registry_response(
    route: ProviderRoute,
    endpoint: ProviderEndpoint | None,
) -> ProviderRoute:
    if endpoint is None or endpoint.provider_kind != "official":
        return route
    doc_capabilities = _official_model_type_capability_values(
        endpoint,
        route.provider_model_id,
        source="probed_verified" if route.status == "verified" else "api_list",
    )
    doc_capabilities.update(
        _provider_doc_limit_capability_values(
            endpoint,
            route.provider_model_id,
        )
    )
    capabilities = _merge_profile_capabilities(doc_capabilities, route.capabilities)
    if capabilities == route.capabilities:
        return route
    return route.model_copy(update={"capabilities": capabilities})


def _normalize_endpoint_metadata_for_registry_response(
    endpoint: ProviderEndpoint,
) -> ProviderEndpoint:
    if _endpoint_probe_backend(endpoint) != "gemini":
        return endpoint
    library = endpoint.metadata.get("capability_library")
    if not isinstance(library, list):
        return endpoint
    normalized_library: list[object] = []
    changed = False
    for entry in library:
        normalized_entry = _normalize_gemini_catalog_entry_for_registry_response(entry)
        normalized_library.append(normalized_entry)
        changed = changed or normalized_entry is not entry
    if not changed:
        return endpoint
    return endpoint.model_copy(
        update={
            "metadata": {
                **endpoint.metadata,
                "capability_library": normalized_library,
            }
        }
    )


def _normalize_gemini_catalog_entry_for_registry_response(entry: object) -> object:
    if not isinstance(entry, dict):
        return entry
    model_id = entry.get("model_id")
    if not isinstance(model_id, str) or not _is_gemini_interactions_only_model(model_id.lower()):
        return entry
    return {
        **entry,
        "status": "catalog_candidate",
        "route_status": "unverified_manual",
        "last_probe_message": NO_VERIFIED_ROUTE_PROFILE_MESSAGE,
        "model_type": "interactions_agent",
        "model_type_label": "Interactions API agent",
        "candidate_methods": ["gemini_interactions"],
        "input_modalities": [],
        "output_modalities": [],
    }


def _model_groups_response(
    credentials: LLMCredentialsFile,
    *,
    circuits_index: ActiveCircuitsIndex,
) -> list[dict[str, Any]]:
    routes_by_identity: dict[str, list[ProviderRoute]] = {}
    for route in credentials.provider_routes.values():
        if not _include_route_in_model_groups(route, credentials):
            continue
        routes_by_identity.setdefault(
            _model_group_identity_key(route, credentials),
            [],
        ).append(route)
    # Build the gateway adapter once for the whole response. Route-state
    # projection reads credential facts only; catalog evidence must already have
    # been promoted into credentials before this read path.
    adapter = build_gateway_adapter()
    model_groups = [
        _model_group_response(
            _representative_canonical_id(routes, credentials),
            routes,
            credentials,
            adapter=adapter,
            circuits_index=circuits_index,
        )
        for routes in routes_by_identity.values()
    ]
    return sorted(
        model_groups,
        key=lambda group: (
            group["section_label"],
            group["display_name"].lower(),
            group["canonical_id"],
        ),
    )


def _include_route_in_model_groups(
    route: ProviderRoute,
    credentials: LLMCredentialsFile,
) -> bool:
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    if endpoint is None:
        return False
    return _route_is_language_capable(
        route,
        allow_unknown=endpoint.provider_kind != "official",
    )


def _route_is_language_capable(route: ProviderRoute, *, allow_unknown: bool) -> bool:
    capabilities = route_effective_capabilities(route)
    input_modalities = _capability_string_list(capabilities, "input_modalities")
    output_modalities = _capability_string_list(capabilities, "output_modalities")
    if input_modalities or output_modalities:
        return "text" in input_modalities and "text" in output_modalities
    capability_family = _capability_string(capabilities, "capability_family") or _capability_string(
        capabilities, "model_type"
    )
    if capability_family:
        return capability_family == "language_reasoning"
    return allow_unknown


def _capability_string(
    capabilities: dict[str, CapabilityValue],
    key: str,
) -> str | None:
    value = capabilities.get(key)
    if value is None or not isinstance(value.value, str):
        return None
    normalized = value.value.strip()
    return normalized or None


def _capability_string_list(
    capabilities: dict[str, CapabilityValue],
    key: str,
) -> list[str]:
    value = capabilities.get(key)
    if value is None:
        return []
    if isinstance(value.value, list):
        return [item.strip().lower() for item in value.value if isinstance(item, str) and item.strip()]
    if isinstance(value.value, str) and value.value.strip():
        return [value.value.strip().lower()]
    return []


def _model_group_identity_key(
    route: ProviderRoute,
    credentials: LLMCredentialsFile,
) -> str:
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    if endpoint is None:
        return normalize_model_group_key(route.canonical_id or route.route_slug)
    projection = project_model_group_identity(route=route, endpoint=endpoint)
    return projection.key or normalize_model_group_key(route.canonical_id or route.route_slug)


def _representative_canonical_id(
    routes: list[ProviderRoute],
    credentials: LLMCredentialsFile,
) -> str:
    route = sorted(routes, key=lambda item: _route_preference_rank(item, credentials))[0]
    return route.canonical_id or route.route_slug


def _route_preference_rank(
    route: ProviderRoute,
    credentials: LLMCredentialsFile,
) -> tuple[int, int, int, str, str]:
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    return (
        _provider_kind_rank(endpoint.provider_kind if endpoint else "third_party"),
        1 if "/" in route.provider_model_id else 0,
        len(route.canonical_id or route.route_slug),
        route.canonical_id or route.route_slug,
        route.route_id,
    )


def _provider_kind_rank(kind: str) -> int:
    if kind == "official":
        return 0
    if kind == "custom":
        return 1
    return 2


def _model_group_response(
    canonical_id: str,
    routes: list[ProviderRoute],
    credentials: LLMCredentialsFile,
    *,
    adapter: GatewayAdapter | None = None,
    circuits_index: ActiveCircuitsIndex,
) -> dict[str, Any]:
    provider_models = [
        option
        for route in sorted(routes, key=lambda item: item.route_id)
        if (
            option := _provider_model_option(
                route,
                credentials,
                adapter=adapter,
                circuits_index=circuits_index,
            )
        )
        is not None
    ]
    status_summary = {state: 0 for state in ["ready", "historical_ready", "untested", "cooling_down", "off", "failed"]}
    for option in provider_models:
        status_summary[option["ui_state"]] += 1
    identity = _model_group_identity(canonical_id, routes, credentials)
    return {
        "canonical_id": canonical_id,
        "display_name": identity["display_name"],
        "section_label": identity["section_label"],
        "provider_models": provider_models,
        "status_summary": status_summary,
        "capability_summary": _capability_summary(provider_models),
    }


def _model_group_identity(
    canonical_id: str,
    routes: list[ProviderRoute],
    credentials: LLMCredentialsFile,
) -> dict[str, str]:
    projections: list[tuple[ProviderRoute, dict[str, str]]] = []
    for route in routes:
        endpoint = credentials.provider_endpoints.get(route.endpoint_id)
        if endpoint is None:
            continue
        projection = project_model_group_identity(route=route, endpoint=endpoint)
        projections.append(
            (
                route,
                {
                    "display_name": projection.display_name,
                    "section_label": projection.section_label,
                },
            )
        )
    if projections:
        route, identity = sorted(
            projections,
            key=lambda item: _route_preference_rank(item[0], credentials),
        )[0]
        del route
        return {
            **identity,
            "section_label": _section_label_from_display_name(identity["display_name"])
            or _dominant_section_label(projections),
        }
    return {"display_name": canonical_id, "section_label": "unknown"}


def _dominant_section_label(
    projections: list[tuple[ProviderRoute, dict[str, str]]],
) -> str:
    counts: dict[str, int] = {}
    for _, identity in projections:
        section_label = identity["section_label"]
        counts[section_label] = counts.get(section_label, 0) + 1
    return sorted(counts, key=lambda section: (-counts[section], section))[0]


def _section_label_from_display_name(display_name: str) -> str:
    haystack = display_name.lower()
    if "anthropic" in haystack or "claude" in haystack:
        return "anthropic"
    if "deepseek" in haystack:
        return "deepseek"
    if "openai" in haystack or re.search(r"\bgpt[-_\s.]?\d", haystack):
        return "openai"
    if "gemini" in haystack or "antigravity" in haystack or re.search(r"\baqa\b", haystack):
        return "gemini"
    if "qwen" in haystack:
        return "qwen"
    if "doubao" in haystack or "ark" in haystack:
        return "ark"
    if "glm" in haystack:
        return "zhipu"
    if "kimi" in haystack:
        return "moonshot"
    if "llama" in haystack or "meta" in haystack:
        return "meta"
    if "mistral" in haystack or "mixtral" in haystack:
        return "mistral"
    if "grok" in haystack or "xai" in haystack:
        return "xai"
    return ""


def _provider_model_option(
    route: ProviderRoute,
    credentials: LLMCredentialsFile,
    *,
    adapter: GatewayAdapter | None = None,
    circuits_index: ActiveCircuitsIndex,
) -> dict[str, Any] | None:
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    if endpoint is None:
        return None
    if adapter is None:
        adapter = build_gateway_adapter()
    circuits = circuits_index.for_route(
        route_id=route.route_id,
        endpoint_id=endpoint.endpoint_id,
        rate_limit_bucket=endpoint.rate_limit_bucket or endpoint.endpoint_id,
    )
    projection = adapter.project_route_state(
        {
            "endpoint": endpoint,
            "route": route,
            "circuits": circuits,
            "now": datetime.now(UTC),
        }
    )
    capabilities = _provider_route_ui_capabilities(route, endpoint)
    model_type = _capability_string(capabilities, "model_type")
    capability_family = _capability_string(capabilities, "capability_family") or model_type
    return {
        "route_id": route.route_id,
        "endpoint_id": endpoint.endpoint_id,
        "provider_label": endpoint.display_name,
        "provider_kind": endpoint.provider_kind,
        "provider_model_id": route.provider_model_id,
        "model_type": model_type,
        "capability_family": capability_family,
        "input_modalities": _capability_string_list(capabilities, "input_modalities"),
        "output_modalities": _capability_string_list(capabilities, "output_modalities"),
        "ui_state": projection.ui_state,
        "ui_detail": projection.ui_detail,
        "retry_at": projection.retry_at,
        "reason_code": projection.reason_code,
        "capability_state": _capability_state(capabilities),
        "capabilities": capabilities,
        # R-F8: CopilotTab filters candidate model groups by call_method_id
        # (anthropic-messages family) instead of the old provider_type
        # heuristic. Unverified official routes also expose candidate methods
        # below so Copilot Test can create the route-level profile evidence.
        "call_method_id": _preferred_route_call_method_id(route),
        "candidate_call_method_ids": _candidate_route_call_method_ids(route, endpoint),
        "copilot_sdk_compatible": _copilot_sdk_compatible(route, endpoint),
    }


def _preferred_route_call_method_id(route: ProviderRoute) -> str | None:
    """R-F8: pick the method_id of this route's preferred verified profile so
    the FE can decide copilot eligibility without re-running the gateway
    resolver. Mirrors `select_verified_profile(route, RuntimeSettings())`:
    among `status=='ready'` profiles, prefer `default=True`, then
    `fallback_rank`, then `profile_id`. Returns None when no profile is
    ready — equivalent to "not yet verified, not yet eligible".
    """
    try:
        selected = select_verified_profile(route, RuntimeSettings())
    except Exception as exc:  # noqa: BLE001 — degradation must be observable
        # rules/logging.md: never silently swallow. A profile-selection error
        # at this point means the route's verified_profiles don't satisfy
        # default settings — degrade to None (FE shows as not-copilot-eligible)
        # and log the reason so operators can fix the credential record.
        logger.warning(
            "phase=copilot-route-call-method-id route_id=%s degraded=true reason=%s",
            route.route_id,
            exc,
        )
        return None
    return selected.method_id if selected is not None else None


def _candidate_route_call_method_ids(
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
) -> list[str]:
    candidates: list[str] = []
    if endpoint.provider_kind == "official":
        candidates.extend(
            candidate.method_id
            for candidate in _official_language_probe_candidates(
                endpoint,
                route.provider_model_id,
            )
        )
    if not candidates or endpoint.provider_kind != "official":
        candidates.extend(call_method_ids_for_endpoint(endpoint.protocol, endpoint.base_url))
    return _ordered_unique(candidates)


def _copilot_sdk_compatible(route: ProviderRoute, endpoint: ProviderEndpoint) -> bool:
    method_ids = _ordered_unique(
        [
            method_id
            for method_id in (
                _preferred_route_call_method_id(route),
                *_candidate_route_call_method_ids(route, endpoint),
            )
            if method_id
        ]
    )
    if not method_ids:
        return False
    compatibilities = [
        call_method_client_compatibility(method_id, "anthropic_messages_client")
        for method_id in method_ids
    ]
    if "supported" in compatibilities:
        return True
    return not all(value == "incompatible" for value in compatibilities)


def _health_store() -> SqliteLlmHealthStore:
    return SqliteLlmHealthStore(credentials_path().with_name("llm_health.sqlite"))


def _provider_route_ui_capabilities(
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
) -> dict[str, CapabilityValue]:
    capabilities = dict(route_effective_capabilities(route))
    group_identity = project_model_group_identity(route=route, endpoint=endpoint)
    if "thinking" in group_identity.capability_tokens and "thinking_protocol" not in capabilities:
        capabilities["thinking_protocol"] = CapabilityValue(
            value=True,
            source="api_list",
            message="Provider exposes thinking as a dedicated model route.",
        )
    return capabilities


def _capability_state(capabilities: dict[str, CapabilityValue]) -> str:
    if not capabilities:
        return "unknown"
    return "known"


def _capability_summary(provider_models: list[dict[str, Any]]) -> dict[str, Any]:
    known_count = sum(1 for option in provider_models if option["capability_state"] != "unknown")
    return {
        "capability_known_count": known_count,
        "thinking": _capability_summary_state(provider_models, _THINKING_CAPABILITY_KEYS),
        "tools": "unknown",
        "structured_output": "unknown",
        "max_context_tokens": None,
        "max_output_tokens": None,
    }


def _capability_summary_state(
    provider_models: list[dict[str, Any]],
    capability_keys: tuple[str, ...],
) -> str:
    known_values: list[bool] = []
    unknown_count = 0
    for option in provider_models:
        supported = _capability_supported(option["capabilities"], capability_keys)
        if supported is None:
            unknown_count += 1
            continue
        known_values.append(supported)
    if not known_values:
        return "unknown"
    if all(known_values) and unknown_count == 0:
        return "supported"
    if any(known_values):
        return "mixed"
    return "mixed" if unknown_count else "unsupported"


def _capability_supported(
    capabilities: dict[str, CapabilityValue],
    capability_keys: tuple[str, ...],
) -> bool | None:
    for key in capability_keys:
        capability = capabilities.get(key)
        if capability is None:
            continue
        return bool(capability.value)
    return None


async def _force_probe_route(
    credentials: LLMCredentialsFile,
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
) -> ProviderRoute:
    if not endpoint.api_key or not endpoint.api_key.get_secret_value():
        updated = route.model_copy(
            update={
                "status": "failed",
                "metadata": {
                    **route.metadata,
                    "reason_code": "missing_config",
                    "last_probe_message": "API key is empty.",
                },
            }
        )
        credentials.provider_routes[route.route_id] = updated
        save_credentials(credentials)
        return updated
    result = _model_probe_result_from_route_probe(
        await _probe_route_generation_atom(endpoint, route)
    )
    if _model_probe_is_disabled_endpoint_skip(result):
        updated = route.model_copy(
            update={
                "status": "disabled",
                "metadata": {
                    **route.metadata,
                    "reason_code": _ENDPOINT_DISABLED_ERROR_CODE,
                    "last_probe_message": DISABLED_ENDPOINT_PROBE_MESSAGE,
                },
            }
        )
        credentials.provider_routes[route.route_id] = updated
        save_credentials(credentials)
        return updated
    if result.status == "ok":
        updated = route.model_copy(
            update={
                "status": "verified",
                "metadata": {
                    key: value
                    for key, value in route.metadata.items()
                    if key not in {"reason_code", "last_probe_message"}
                },
            }
        )
        credentials.provider_routes[route.route_id] = updated
        save_credentials(credentials)
        _health_store().clear_circuit(scope="route", scope_id=route.route_id)
        return updated
    if result.status in {"timeout", "rate_limited", "quota_exceeded", "network_error"}:
        ttl_seconds = credentials.runtime_policy.provider_down_ttl_seconds
        now = datetime.now(UTC)
        _health_store().open_circuit(
            RuntimeCircuit(
                scope="route",
                scope_id=route.route_id,
                opened_at=now,
                retry_at=now + timedelta(seconds=ttl_seconds),
                ttl_seconds=ttl_seconds,
                reason_code=result.status,
                failure_count=1,
                message=result.message,
            )
        )
        return route
    updated = route.model_copy(
        update={
            "status": "failed",
            "metadata": {
                **route.metadata,
                "reason_code": result.status,
                "last_probe_message": result.message,
            },
        }
    )
    credentials.provider_routes[route.route_id] = updated
    save_credentials(credentials)
    return updated


async def _role_test_provider_result(
    entry: RoleRouteEntry | None,
    report_entry: dict[str, Any],
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
) -> dict[str, Any]:
    projection = _provider_model_projection(route, endpoint)
    provider_ui_state = projection.ui_state
    role_fit = str(report_entry.get("role_fit") or "using")
    warnings = list(report_entry.get("warnings") or [])
    admission_decision = _admission_decision(projection.ui_state)
    status = "blocked" if admission_decision == "block" else "untested"
    message = None
    runtime_settings, resolved_settings = _role_test_runtime_settings(entry, report_entry)
    if role_fit == "not_fit":
        admission_decision = "block"
        status = "blocked"
    elif admission_decision == "admit" and endpoint.api_key is not None:
        route, profile_probe_result = await _ensure_official_role_test_verified_profile(
            route,
            endpoint,
        )
        if profile_probe_result is not None and not profile_probe_result.profiles:
            result = ModelProbeResult(
                model_id=route.provider_model_id,
                status="error",
                message=_official_role_test_profile_probe_failure_message(profile_probe_result),
            )
        else:
            projection = _provider_model_projection(route, endpoint)
            provider_ui_state = projection.ui_state
            result = await _probe_role_route(
                route,
                endpoint,
                runtime_settings,
                resolved_settings,
            )
        status = "ok" if result.status == "ok" else "failed"
        if status == "ok":
            provider_ui_state = "ready"
        message = result.message
    return {
        "route_id": route.route_id,
        "provider_label": endpoint.display_name,
        "provider_ui_state": provider_ui_state,
        "role_fit": role_fit,
        "admission_decision": admission_decision,
        "status": status,
        "warnings": warnings,
        "retry_at": projection.retry_at,
        "message": message,
        "resolved_settings": resolved_settings or {},
    }


def _role_test_runtime_settings(
    entry: RoleRouteEntry | None,
    report_entry: dict[str, Any],
) -> tuple[RuntimeSettings, dict[str, Any]]:
    resolved_settings = report_entry.get("resolved_settings")
    if isinstance(resolved_settings, dict):
        try:
            runtime_settings = RuntimeSettings.model_validate(resolved_settings)
            return (
                runtime_settings,
                runtime_settings.model_dump(mode="json", exclude_none=True),
            )
        except ValidationError:
            pass

    if entry is not None:
        return (
            entry.runtime_settings,
            entry.runtime_settings.model_dump(mode="json", exclude_none=True),
        )
    return RuntimeSettings(), {}


async def _ensure_official_role_test_verified_profile(
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
    *,
    required_method_ids: frozenset[str] | None = None,
) -> tuple[ProviderRoute, OfficialModelProfileProbeResult | None]:
    if endpoint.provider_kind != "official" or _route_has_ready_verified_profile(
        route,
        required_method_ids=required_method_ids,
    ):
        return route, None
    if _endpoint_probe_is_disabled(endpoint):
        return (
            route,
            OfficialModelProfileProbeResult(
                model_id=route.provider_model_id,
                last_probe_message=DISABLED_ENDPOINT_PROBE_MESSAGE,
            ),
        )

    profile_result = await _probe_official_model_profile_atom(
        endpoint,
        route.provider_model_id,
    )
    if profile_result.profiles:
        updated_route = _persist_official_role_test_verified_profile(
            route,
            endpoint,
            profile_result,
        )
        if not _route_has_ready_verified_profile(
            updated_route,
            required_method_ids=required_method_ids,
        ):
            return (
                updated_route,
                OfficialModelProfileProbeResult(
                    model_id=route.provider_model_id,
                    last_probe_message=_NO_COPILOT_COMPATIBLE_OFFICIAL_PROFILE_MESSAGE,
                    probe_attempts=profile_result.probe_attempts,
                ),
            )
        return (
            updated_route,
            profile_result,
        )
    updated_route = _persist_official_role_test_profile_failure(route, endpoint, profile_result)
    return (
        updated_route,
        profile_result,
    )


def _route_has_ready_verified_profile(
    route: ProviderRoute,
    *,
    required_method_ids: frozenset[str] | None = None,
) -> bool:
    return any(
        profile.status == "ready"
        and (required_method_ids is None or profile.method_id in required_method_ids)
        for profile in route.verified_profiles
    )


def _persist_official_role_test_verified_profile(
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
    profile_result: OfficialModelProfileProbeResult,
) -> ProviderRoute:
    credentials = load_credentials()
    latest_endpoint = credentials.provider_endpoints.get(endpoint.endpoint_id)
    if latest_endpoint is None or route.route_id not in credentials.provider_routes:
        return route
    probe_attempts_by_model = (
        {profile_result.model_id: profile_result.probe_attempts} if profile_result.probe_attempts else None
    )
    credentials, route_ids_by_model = _upsert_discovered_routes(
        credentials,
        endpoint=latest_endpoint,
        model_ids=(profile_result.model_id,),
        verified=True,
        verified_profiles_by_model={profile_result.model_id: profile_result.profiles},
        probe_attempts_by_model=probe_attempts_by_model,
    )
    updated_route_id = route_ids_by_model.get(profile_result.model_id, route.route_id)
    if updated_route_id is None:
        return route
    updated_route = credentials.provider_routes.get(updated_route_id)
    if updated_route is None:
        return route
    cleaned_metadata = {
        key: value for key, value in updated_route.metadata.items() if key not in {"reason_code", "last_probe_message"}
    }
    if profile_result.probe_attempts:
        cleaned_metadata["probe_attempts"] = profile_result.probe_attempts
    updated_route = updated_route.model_copy(update={"metadata": cleaned_metadata})
    credentials.provider_routes[updated_route.route_id] = updated_route
    # Merge the profile-probe evidence into the SAME save (R3.3-AC2), not the catalog.
    _merge_official_profile_evidence_into_route(
        credentials, latest_endpoint, profile_result, route_id=updated_route.route_id
    )
    save_credentials(credentials)
    return credentials.provider_routes[updated_route.route_id]


def _persist_official_role_test_profile_failure(
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
    profile_result: OfficialModelProfileProbeResult,
) -> ProviderRoute:
    credentials = load_credentials()
    current_route = credentials.provider_routes.get(route.route_id)
    if current_route is None:
        return route
    metadata = {
        **current_route.metadata,
        "reason_code": "profile_probe_failed",
        "last_probe_message": _official_role_test_profile_probe_failure_message(profile_result),
    }
    if profile_result.probe_attempts:
        metadata["probe_attempts"] = profile_result.probe_attempts
    updated_route = current_route.model_copy(update={"metadata": metadata})
    credentials.provider_routes[updated_route.route_id] = updated_route
    # Merge the probe-failed evidence into the SAME save (R3.3-AC2), not the catalog.
    _merge_official_profile_evidence_into_route(
        credentials, endpoint, profile_result, route_id=updated_route.route_id
    )
    save_credentials(credentials)
    return credentials.provider_routes[updated_route.route_id]


def _official_role_test_profile_probe_failure_message(
    profile_result: OfficialModelProfileProbeResult,
) -> str:
    return profile_result.last_probe_message or NO_WORKING_OFFICIAL_LANGUAGE_METHOD_MESSAGE


def _build_official_profile_probe_evidence(
    endpoint: ProviderEndpoint,
    profile_result: OfficialModelProfileProbeResult,
    *,
    route_id: str | None,
) -> EvidenceRecord:
    profile = _selected_evidence_profile(profile_result.profiles)
    first_attempt = _first_probe_attempt(profile_result.probe_attempts)
    model_id = profile_result.model_id
    verified = bool(profile_result.profiles)
    reason = None if verified else _official_role_test_profile_probe_failure_message(profile_result)
    catalog_capabilities = _official_catalog_capabilities(endpoint, model_id)
    return (
        EvidenceRecord(
            evidence_id=new_evidence_id("probe"),
            evidence_type="probe",
            trust_state="probe-verified" if verified else "probe-failed",
            observed_at=_now_iso(),
            attempted_at=_now_iso(),
            endpoint_id=endpoint.endpoint_id,
            # W3-B / R-B7: attribute evidence to the provider's registrable-domain name.
            provider_id=registrable_provider_name(endpoint.base_url),
            route_id=route_id,
            model_id=model_id,
            provider_model_id=model_id,
            method_id=(profile.method_id if profile is not None else _probe_attempt_string(first_attempt, "method_id")),
            request_mapper_id=(
                profile.request_mapper_id
                if profile is not None
                else _probe_attempt_string(first_attempt, "request_mapper_id")
            ),
            probe_status="ok" if verified else _probe_attempt_string(first_attempt, "status"),
            reason=reason,
            model_type=_catalog_string(catalog_capabilities, "model_type"),
            capability_family=_catalog_string(catalog_capabilities, "model_type"),
            input_modalities=_evidence_modalities(
                profile_result.profiles,
                profile_result.probe_attempts,
                catalog_capabilities,
                "input_modalities",
            ),
            output_modalities=_evidence_modalities(
                profile_result.profiles,
                profile_result.probe_attempts,
                catalog_capabilities,
                "output_modalities",
            ),
            candidate_methods=_official_evidence_candidate_methods(
                profile_result.profiles,
                profile_result.probe_attempts,
                catalog_capabilities,
            ),
            candidate_capabilities=verified_profile_route_capabilities(profile_result.profiles),
            scope=_probe_evidence_scope(
                endpoint_id=endpoint.endpoint_id,
                route_id=route_id,
                model_id=model_id,
            ),
            probe_attempts=profile_result.probe_attempts,
            successful_probe=({"profile_count": len(profile_result.profiles)} if verified else None),
            failed_probe=(
                {
                    "status": _probe_attempt_string(first_attempt, "status") or "error",
                    "reason": reason,
                }
                if not verified
                else None
            ),
        )
    )


def _merge_official_profile_evidence_into_route(
    credentials: LLMCredentialsFile,
    endpoint: ProviderEndpoint,
    profile_result: OfficialModelProfileProbeResult,
    *,
    route_id: str | None,
) -> None:
    """Build official profile-probe evidence and merge it into its credentials route.

    Return-and-merge (design §5): the record is assigned back to
    ``credentials.provider_routes[route_id]`` so it lands in the SAME save as the
    profile — never the probe catalog. No-op when the route is unknown/absent.
    """
    if route_id is None:
        return
    route = credentials.provider_routes.get(route_id)
    if route is None:
        return
    record = _build_official_profile_probe_evidence(endpoint, profile_result, route_id=route_id)
    credentials.provider_routes[route_id] = merge_route_evidence(route, record)


def _build_model_probe_evidence(
    endpoint: ProviderEndpoint,
    result: ModelProbeResult,
    *,
    route_id: str | None,
    multimodal: bool = False,
) -> EvidenceRecord:
    verified = result.status == "ok"
    reason = None if verified else _model_probe_failure_message(result)
    probe_capabilities = (
        _successful_multimodal_probe_capabilities()
        if multimodal
        else _successful_generation_probe_capabilities()
    )
    capability_values = (
        _third_party_route_capability_values(
            endpoint,
            result.model_id,
            probe_capabilities,
            source="probed_verified",
        )
        if verified
        else {}
    )
    return (
        EvidenceRecord(
            evidence_id=new_evidence_id("probe"),
            evidence_type="probe",
            trust_state="probe-verified" if verified else "probe-failed",
            observed_at=_now_iso(),
            attempted_at=_now_iso(),
            endpoint_id=endpoint.endpoint_id,
            # W3-B / R-B7: attribute evidence to the provider's registrable-domain name.
            provider_id=registrable_provider_name(endpoint.base_url),
            route_id=route_id,
            model_id=result.model_id,
            provider_model_id=result.model_id,
            probe_status=result.status,
            reason=reason,
            model_type=_capability_string(capability_values, "model_type"),
            capability_family=_capability_string(capability_values, "capability_family"),
            input_modalities=_capability_string_list(capability_values, "input_modalities"),
            output_modalities=_capability_string_list(capability_values, "output_modalities"),
            candidate_capabilities=capability_values,
            scope=_probe_evidence_scope(
                endpoint_id=endpoint.endpoint_id,
                route_id=route_id,
                model_id=result.model_id,
            ),
            probe_attempts=[
                {
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "message": result.message,
                }
            ],
            successful_probe=({"status": result.status, "latency_ms": result.latency_ms} if verified else None),
            failed_probe=({"status": result.status, "reason": reason} if not verified else None),
        )
    )


def _merge_probe_evidence_into_route(
    credentials: LLMCredentialsFile,
    endpoint: ProviderEndpoint,
    result: ModelProbeResult,
    *,
    route_id: str | None,
    multimodal: bool = False,
) -> None:
    """Build probe evidence for a model and merge it into its credentials route.

    Return-and-merge (design §4.1/§5): the record is built then assigned back to
    ``credentials.provider_routes[route_id]`` — never written to the probe catalog.
    No-op when the route is unknown/absent so callers can pass a best-effort id.
    ``multimodal=True`` 记录含 image 的 input_modalities(probed_verified)。
    """
    if route_id is None:
        return
    route = credentials.provider_routes.get(route_id)
    if route is None:
        return
    record = _build_model_probe_evidence(
        endpoint, result, route_id=route_id, multimodal=multimodal
    )
    credentials.provider_routes[route_id] = merge_route_evidence(route, record)


def _selected_evidence_profile(
    profiles: list[VerifiedProfile],
) -> VerifiedProfile | None:
    if not profiles:
        return None
    return sorted(
        profiles,
        key=lambda profile: (not profile.default, profile.fallback_rank, profile.profile_id),
    )[0]


def _first_probe_attempt(
    probe_attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return probe_attempts[0] if probe_attempts else {}


def _probe_attempt_string(
    probe_attempt: dict[str, Any],
    key: str,
) -> str | None:
    value = probe_attempt.get(key)
    return value if isinstance(value, str) else None


def _catalog_string(
    capabilities: dict[str, object],
    key: str,
) -> str | None:
    value = capabilities.get(key)
    return value if isinstance(value, str) else None


def _evidence_modalities(
    profiles: list[VerifiedProfile],
    probe_attempts: list[dict[str, Any]],
    catalog_capabilities: dict[str, object],
    key: Literal["input_modalities", "output_modalities"],
) -> list[str]:
    values = [modality for profile in profiles for modality in getattr(profile, key) if isinstance(modality, str)]
    for attempt in probe_attempts:
        attempt_modalities = attempt.get(key)
        if isinstance(attempt_modalities, list):
            values.extend(modality for modality in attempt_modalities if isinstance(modality, str))
    catalog_modalities = catalog_capabilities.get(key)
    if isinstance(catalog_modalities, list):
        values.extend(modality for modality in catalog_modalities if isinstance(modality, str))
    return _ordered_unique(values)


def _official_evidence_candidate_methods(
    profiles: list[VerifiedProfile],
    probe_attempts: list[dict[str, Any]],
    catalog_capabilities: dict[str, object],
) -> list[str]:
    catalog_methods = catalog_capabilities.get("candidate_methods")
    methods: list[str] = []
    if isinstance(catalog_methods, list):
        methods.extend(method for method in catalog_methods if isinstance(method, str))
    methods.extend(profile.method_id for profile in profiles)
    for attempt in probe_attempts:
        method_id = _probe_attempt_string(attempt, "method_id")
        if method_id is not None:
            methods.append(method_id)
    return _ordered_unique(methods)


def _probe_evidence_scope(
    *,
    endpoint_id: str,
    route_id: str | None,
    model_id: str,
) -> dict[str, str]:
    scope = {"endpoint_id": endpoint_id, "model_id": model_id}
    if route_id is not None:
        scope["route_id"] = route_id
    return scope


async def _probe_role_route(
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
    runtime_settings: RuntimeSettings,
    resolved_settings: dict[str, Any],
) -> ModelProbeResult:
    if _endpoint_probe_is_disabled(endpoint):
        return _disabled_model_probe_result(route.provider_model_id)
    try:
        selected_profile = select_verified_profile(route, runtime_settings)
    except ProfileSelectionError as exc:
        return ModelProbeResult(
            model_id=route.provider_model_id,
            status="error",
            message=str(exc),
        )

    if selected_profile is not None:
        return await _probe_official_call_method_generation_atom(
            endpoint,
            route.provider_model_id,
            selected_profile.method_id,
            runtime_settings=_role_test_profile_runtime_settings(
                selected_profile,
                resolved_settings,
            ),
        )

    if endpoint.provider_kind == "official":
        return ModelProbeResult(
            model_id=route.provider_model_id,
            status="error",
            message=ROLE_TEST_NO_VERIFIED_PROFILE_MESSAGE,
        )

    return _model_probe_result_from_route_probe(
        await _probe_route_generation_atom(
            endpoint,
            route,
            runtime_settings=resolved_settings or None,
        )
    )


def _role_test_profile_runtime_settings(
    selected_profile: VerifiedProfile,
    resolved_settings: dict[str, Any],
) -> dict[str, Any]:
    return _deep_merge_runtime_settings(
        selected_profile.runtime_overrides,
        resolved_settings,
    )


def _deep_merge_runtime_settings(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_runtime_settings(existing, value)
        else:
            merged[key] = value
    return merged


async def _probe_official_model_profiles(
    endpoint: ProviderEndpoint,
    model_id: str,
) -> list[VerifiedProfile]:
    """Probe one official-provider model and return verified LLM invocation profiles."""
    return (await _probe_official_model_profile_atom(endpoint, model_id)).profiles


async def _probe_official_model_profile_result(
    endpoint: ProviderEndpoint,
    model_id: str,
) -> OfficialModelProfileProbeResult:
    """Probe one official-provider model and keep the best failure detail."""
    if not endpoint.api_key or not endpoint.api_key.get_secret_value():
        return OfficialModelProfileProbeResult(
            model_id=model_id,
            last_probe_message="API key is empty.",
        )
    candidates = _official_language_probe_candidates(endpoint, model_id)
    if not candidates:
        return OfficialModelProfileProbeResult(model_id=model_id)

    verified: list[tuple[OfficialLanguageProbeCandidate, ModelProbeResult]] = []
    failed_results: list[ModelProbeResult] = []
    probe_attempts: list[dict[str, Any]] = []
    succeeded_retry_groups: set[str] = set()
    for candidate in candidates:
        if candidate.retry_group and candidate.retry_group in succeeded_retry_groups:
            continue
        result = await _probe_official_call_method(endpoint, model_id, candidate)
        probe_attempts.append(_official_probe_attempt_record(candidate, result))
        if result.status == "ok":
            verified.append((candidate, result))
            if candidate.retry_group:
                succeeded_retry_groups.add(candidate.retry_group)
        else:
            failed_results.append(result)
    if not verified:
        return OfficialModelProfileProbeResult(
            model_id=model_id,
            last_probe_message=_official_profile_probe_failure_message(failed_results),
            probe_attempts=probe_attempts,
        )

    default_candidate = min(
        verified,
        key=lambda item: (item[0].default_rank, item[0].profile_id),
    )[0]
    return OfficialModelProfileProbeResult(
        model_id=model_id,
        profiles=[
            VerifiedProfile(
                profile_id=candidate.profile_id,
                capability=candidate.capability,
                method_id=candidate.method_id,
                request_mapper_id=candidate.request_mapper_id,
                status="ready",
                default=candidate is default_candidate,
                fallback_rank=candidate.fallback_rank,
                input_modalities=list(candidate.input_modalities),
                output_modalities=list(candidate.output_modalities),
                runtime_overrides=candidate.runtime_settings,
                metadata={
                    "probe_latency_ms": result.latency_ms,
                    "source": "official_test",
                },
            )
            for candidate, result in verified
        ],
        probe_attempts=probe_attempts,
    )


def _official_probe_attempt_record(
    candidate: OfficialLanguageProbeCandidate,
    result: ModelProbeResult,
) -> dict[str, Any]:
    return {
        "profile_id": candidate.profile_id,
        "capability": candidate.capability,
        "method_id": candidate.method_id,
        "request_mapper_id": candidate.request_mapper_id,
        "status": result.status,
        "latency_ms": result.latency_ms,
        "message": _model_probe_failure_message(result) if result.status != "ok" else None,
        "input_modalities": list(candidate.input_modalities),
        "output_modalities": list(candidate.output_modalities),
        "runtime_overrides": candidate.runtime_settings,
    }


def _official_profile_probe_failure_message(
    failed_results: list[ModelProbeResult],
) -> str | None:
    if not failed_results:
        return None
    for result in failed_results:
        if result.message:
            return _model_probe_failure_message(result)
    return _model_probe_failure_message(failed_results[0])


async def _probe_official_call_method(
    endpoint: ProviderEndpoint,
    model_id: str,
    candidate: OfficialLanguageProbeCandidate,
    *,
    multimodal: bool = False,
) -> ModelProbeResult:
    return await _probe_official_call_method_generation_atom(
        endpoint,
        model_id,
        candidate.method_id,
        runtime_settings=candidate.runtime_settings,
        multimodal=multimodal,
    )


async def _probe_official_call_method_generation_atom(
    endpoint: ProviderEndpoint,
    model_id: str,
    method_id: OfficialCallMethod,
    *,
    runtime_settings: dict[str, Any] | None = None,
    multimodal: bool = False,
) -> ModelProbeResult:
    if _endpoint_probe_is_disabled(endpoint):
        return _disabled_model_probe_result(model_id)
    if not endpoint.api_key or not endpoint.api_key.get_secret_value():
        return ModelProbeResult(
            model_id=model_id,
            status="invalid_key",
            message="API key is empty.",
        )
    await _publish_llm_probe_active(endpoint.endpoint_id, (model_id,))
    try:
        return await _gateway_probe_official_call_method(
            method_id,
            endpoint.api_key.get_secret_value(),
            _endpoint_probe_base_url(endpoint),
            model_id,
            runtime_settings=runtime_settings,
            multimodal=multimodal,
        )
    finally:
        await _publish_llm_probe_active(endpoint.endpoint_id, ())


def _official_language_probe_candidates(
    endpoint: ProviderEndpoint,
    model_id: str,
) -> list[OfficialLanguageProbeCandidate]:
    if not _is_official_language_model_candidate(endpoint, model_id):
        return []
    backend = _endpoint_probe_backend(endpoint)
    # openai + gemini pick candidates from the model id (reasoning-effort ladders,
    # thinking tiers) -> data-driven via the rules interpreter
    # (app/data/probe_candidates_dynamic.json), NOT hardcoded if/else.
    dynamic_specs = dynamic_probe_candidate_specs(backend, model_id)
    if dynamic_specs is not None:
        return [_candidate(**spec) for spec in dynamic_specs]
    # claude / deepseek / ark have fixed (model-independent) candidate lists -> static
    # config (app/data/probe_candidates.json). Each spec is _candidate() kwargs.
    specs = static_probe_candidate_specs(backend)
    if specs is not None:
        return [_candidate(**spec) for spec in specs]
    return []


def _candidate(
    method_id: OfficialCallMethod,
    profile_id: str,
    capability: str,
    request_mapper_id: str,
    default_rank: int,
    fallback_rank: int,
    *,
    runtime_settings: dict[str, Any] | None = None,
    input_modalities: tuple[str, ...] = ("text",),
    output_modalities: tuple[str, ...] = ("text",),
    retry_group: str | None = None,
) -> OfficialLanguageProbeCandidate:
    return OfficialLanguageProbeCandidate(
        profile_id=profile_id,
        capability=capability,
        method_id=method_id,
        request_mapper_id=request_mapper_id,
        runtime_settings=runtime_settings or {"max_output_tokens": 16},
        default_rank=default_rank,
        fallback_rank=fallback_rank,
        input_modalities=input_modalities,
        output_modalities=output_modalities,
        retry_group=retry_group,
    )


def _is_gemini_interactions_only_model(model: str) -> bool:
    return model.startswith("antigravity") or model.startswith("deep-research") or model == "aqa"


def _is_official_language_model_candidate(endpoint: ProviderEndpoint, model_id: str) -> bool:
    model = model_id.lower()
    catalog_provider_key = _endpoint_catalog_provider_key(endpoint)
    if catalog_provider_key == "anthropic":
        return model.startswith("claude-")
    if catalog_provider_key == "gemini":
        if _is_gemini_interactions_only_model(model):
            return False
        if _is_gemini_known_non_language_model(model):
            return False
        return True
    if catalog_provider_key == "deepseek":
        return model.startswith("deepseek-")
    if catalog_provider_key == "ark":
        # W3-A / T2: ARK's language-model prefixes + non-language tokens are data-driven
        # (app/data/provider_identity.json -> ark). A model is a language model when it
        # has no non-language token and starts with a configured prefix.
        classification = language_model_classification("ark")
        if classification is not None:
            prefixes, non_language_tokens = classification
            if any(token in model for token in non_language_tokens):
                return False
            return any(model.startswith(prefix) for prefix in prefixes)
        return False
    if any(
        token in model
        for token in (
            "embedding",
            "gpt-image",
            "chatgpt-image",
            "tts",
            "whisper",
            "transcribe",
            "realtime",
            "audio",
            "sora",
            "moderation",
            "babbage",
            "davinci",
        )
    ):
        return False
    return (
        model.startswith("gpt-")
        or model.startswith("o1")
        or model.startswith("o3")
        or model.startswith("o4")
        or model == "chat-latest"
    )


def _official_catalog_capabilities(
    endpoint: ProviderEndpoint,
    model_id: str,
    raw_capabilities: dict[str, Any] | None = None,
) -> dict[str, object]:
    model_type, label = _official_catalog_model_type(endpoint, model_id)
    input_modalities, output_modalities = _official_catalog_modalities(
        endpoint,
        model_id,
        model_type,
    )
    normalized = _plain_normalized_capabilities(endpoint, model_id, raw_capabilities)
    input_source_urls = official_doc_source_urls(
        _endpoint_capability_source_key(endpoint),
        model_type=model_type,
        modalities=input_modalities,
    )
    output_source_urls = official_doc_source_urls(
        _endpoint_capability_source_key(endpoint),
        model_type=model_type,
        modalities=output_modalities,
    )
    capabilities: dict[str, object] = {
        "model_type": model_type,
        "model_type_label": label,
        "capability_library": model_type != "language_reasoning",
        "candidate_methods": _official_catalog_candidate_methods(
            endpoint,
            model_id,
            model_type,
        ),
        "input_modalities": list(input_modalities),
        "output_modalities": list(output_modalities),
        "input_modalities_source": "provider_doc",
        "output_modalities_source": "provider_doc",
        "input_modalities_source_urls": list(input_source_urls),
        "output_modalities_source_urls": list(output_source_urls),
    }
    capabilities.update(_provider_doc_limit_capabilities(endpoint, model_id))
    capabilities.update(normalized)
    return capabilities


def _official_catalog_candidate_methods(
    endpoint: ProviderEndpoint,
    model_id: str,
    model_type: str,
) -> list[str]:
    methods: set[str] = {candidate.method_id for candidate in _official_language_probe_candidates(endpoint, model_id)}
    model = model_id.lower()
    backend = _endpoint_probe_backend(endpoint)
    if backend == "openai":
        if model_type == "image_generation":
            methods.add("openai_images")
        elif model_type == "video_generation":
            methods.add("openai_videos")
        elif model_type == "audio":
            if "realtime" in model:
                methods.add("openai_realtime")
            elif any(token in model for token in ("whisper", "transcribe")):
                methods.add("openai_audio_transcriptions")
            elif "tts" in model:
                methods.add("openai_audio_speech")
            else:
                methods.add("openai_audio")
        elif model_type == "embedding":
            methods.add("openai_embeddings")
        elif model_type == "moderation":
            methods.add("openai_moderations")
    elif backend == "gemini":
        if model_type == "image_generation":
            methods.add("gemini_generate_images" if model.startswith("imagen-") else "gemini_generate_content")
        elif model_type == "video_generation":
            methods.add("gemini_generate_videos")
        elif model_type == "audio":
            methods.add("gemini_generate_music" if "lyria" in model else "gemini_generate_content")
        elif model_type == "embedding":
            methods.add("gemini_embed_content")
        elif model_type == "interactions_agent":
            methods.add("gemini_interactions")
    elif backend == "ark":
        if model_type == "image_generation":
            methods.add("ark_images")
        elif model_type == "video_generation":
            methods.add("ark_video")
        elif model_type == "audio":
            methods.add("ark_audio")
        elif model_type == "embedding":
            methods.add("ark_embeddings")
        elif model_type == "translation":
            methods.add("ark_translation")
        elif model_type == "3d_generation":
            methods.add("ark_3d")
    return sorted(methods)


def _plain_normalized_capabilities(
    endpoint: ProviderEndpoint,
    model_id: str,
    raw_capabilities: dict[str, Any] | None,
) -> dict[str, object]:
    normalized = normalize_route_capabilities(
        protocol=endpoint.protocol,
        provider_model_id=model_id,
        raw_capabilities=raw_capabilities or {},
        source="api_list",
    )
    plain: dict[str, object] = {}
    source_urls = official_api_list_source_urls(_endpoint_capability_source_key(endpoint))
    for key, capability in normalized.items():
        if key in {
            "max_input_tokens",
            "max_output_tokens",
            "input_modalities",
            "output_modalities",
        }:
            plain[key] = capability.value
            plain[f"{key}_source"] = capability.source
            plain[f"{key}_source_urls"] = list(source_urls)
        if key in {"input_modalities", "output_modalities"}:
            plain[f"{key}_source"] = capability.source
    return plain


def _official_normalized_route_capabilities(
    endpoint: ProviderEndpoint,
    model_id: str,
    raw_capabilities: dict[str, Any] | None,
) -> dict[str, CapabilityValue]:
    capabilities = normalize_route_capabilities(
        protocol=endpoint.protocol,
        provider_model_id=model_id,
        raw_capabilities=raw_capabilities or {},
        source="api_list",
    )
    source_urls = list(official_api_list_source_urls(_endpoint_capability_source_key(endpoint)))
    for key in ("input_modalities", "output_modalities", "max_input_tokens", "max_output_tokens"):
        capability = capabilities.get(key)
        if capability is None:
            continue
        capabilities[f"{key}_source"] = CapabilityValue(
            value=capability.source,
            source=capability.source,
        )
        capabilities[f"{key}_source_urls"] = CapabilityValue(
            value=source_urls,
            source=capability.source,
        )
    return capabilities


def _provider_doc_limit_capabilities(
    endpoint: ProviderEndpoint,
    model_id: str,
) -> dict[str, object]:
    capabilities: dict[str, object] = {}
    for key, rule in provider_doc_limit_rules(
        _endpoint_capability_source_key(endpoint),
        model_id,
    ).items():
        capabilities[key] = rule.value
        capabilities[f"{key}_source"] = rule.source
        capabilities[f"{key}_source_urls"] = list(rule.source_urls)
    return capabilities


def _provider_doc_limit_capability_values(
    endpoint: ProviderEndpoint,
    model_id: str,
) -> dict[str, CapabilityValue]:
    capabilities: dict[str, CapabilityValue] = {}
    for key, rule in provider_doc_limit_rules(
        _endpoint_capability_source_key(endpoint),
        model_id,
    ).items():
        capabilities[key] = _capability_value_from_rule(rule)
        capabilities[f"{key}_source_urls"] = CapabilityValue(
            value=list(rule.source_urls),
            source=rule.source,
            message=rule.message,
        )
        capabilities[f"{key}_source"] = CapabilityValue(
            value=rule.source,
            source=rule.source,
            message=rule.message,
        )
    return capabilities


def _capability_value_from_rule(rule: OfficialCapabilityRule) -> CapabilityValue:
    return CapabilityValue(value=rule.value, source=rule.source, message=rule.message)


def _catalog_limit_fields(capabilities: dict[str, object]) -> dict[str, object]:
    return {
        key: capabilities[key]
        for key in (
            "max_input_tokens",
            "max_input_tokens_source",
            "max_input_tokens_source_urls",
            "max_output_tokens",
            "max_output_tokens_source",
            "max_output_tokens_source_urls",
        )
        if key in capabilities
    }


def _official_verified_model_capabilities(
    endpoint: ProviderEndpoint,
    model_id: str,
    profiles: list[VerifiedProfile],
    probe_attempts: list[dict[str, Any]] | None = None,
    raw_capabilities: dict[str, Any] | None = None,
) -> dict[str, object]:
    capabilities = _official_catalog_capabilities(endpoint, model_id, raw_capabilities)
    raw_input_modalities = capabilities.get("input_modalities")
    raw_output_modalities = capabilities.get("output_modalities")
    catalog_input_modalities = (
        [value for value in raw_input_modalities if isinstance(value, str)]
        if isinstance(raw_input_modalities, list)
        else []
    )
    catalog_output_modalities = (
        [value for value in raw_output_modalities if isinstance(value, str)]
        if isinstance(raw_output_modalities, list)
        else []
    )
    verified_input_modalities = sorted(
        {modality for profile in profiles for modality in (profile.input_modalities or [])}
    )
    verified_output_modalities = sorted(
        {modality for profile in profiles for modality in (profile.output_modalities or [])}
    )
    capabilities.update(
        {
            "model_type": "language_reasoning",
            "model_type_label": "Language/reasoning model",
            "capability_library": False,
            "verified_methods": sorted({profile.method_id for profile in profiles}),
            "input_modalities": _ordered_unique([*catalog_input_modalities, *verified_input_modalities]),
            "output_modalities": _ordered_unique([*catalog_output_modalities, *verified_output_modalities]),
            "input_modalities_source": (
                capabilities.get("input_modalities_source") if catalog_input_modalities else "probed_verified"
            ),
            "output_modalities_source": (
                capabilities.get("output_modalities_source") if catalog_output_modalities else "probed_verified"
            ),
            "verified_profiles": [
                {
                    "profile_id": profile.profile_id,
                    "capability": profile.capability,
                    "method_id": profile.method_id,
                    "request_mapper_id": profile.request_mapper_id,
                    "input_modalities": profile.input_modalities or [],
                    "output_modalities": profile.output_modalities or [],
                }
                for profile in profiles
            ],
        }
    )
    if probe_attempts:
        capabilities["probe_attempts"] = probe_attempts
    return capabilities


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _official_catalog_model_type(endpoint: ProviderEndpoint, model_id: str) -> tuple[str, str]:
    model = model_id.lower()
    catalog_provider_key = _endpoint_catalog_provider_key(endpoint)
    if catalog_provider_key == "gemini" and _is_gemini_interactions_only_model(model):
        return "interactions_agent", "Interactions API agent"
    if _is_official_language_model_candidate(endpoint, model_id):
        return "language_reasoning", "Language/reasoning model"
    if any(
        token in model
        for token in (
            "seedream",
            "gpt-image",
            "chatgpt-image",
            "dall-e",
            "imagen",
            "nano-banana",
        )
    ) or (catalog_provider_key == "gemini" and "image" in model):
        return "image_generation", "Image generation model"
    if any(token in model for token in ("seedance", "sora", "veo", "video", "wan")):
        return "video_generation", "Video generation model"
    if any(
        token in model
        for token in (
            "tts",
            "whisper",
            "transcribe",
            "audio",
            "chirp",
            "lyria",
            "realtime",
        )
    ):
        return "audio", "Audio/realtime model"
    if "embedding" in model or model.startswith(("babbage-", "davinci-")):
        return "embedding", "Embedding model"
    if "moderation" in model:
        return "moderation", "Moderation model"
    if "translate" in model or "translation" in model:
        return "translation", "Translation model"
    if "3d" in model:
        return "3d_generation", "3D generation model"
    return "catalog_candidate", "Catalog-only model"


def _official_catalog_modalities(
    endpoint: ProviderEndpoint,
    model_id: str,
    model_type: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    catalog_provider_key = _endpoint_catalog_provider_key(endpoint)
    model = model_id.lower()
    if model_type == "language_reasoning":
        if catalog_provider_key == "anthropic":
            return ("text", "image", "pdf"), ("text",)
        if catalog_provider_key == "gemini" and not model.startswith("gemma-"):
            return ("text", "image", "audio", "video"), ("text",)
        if catalog_provider_key == "openai":
            if model.startswith(("gpt-4", "gpt-5", "o1", "o3", "o4")):
                return ("text", "image", "file"), ("text",)
            return ("text",), ("text",)
        return ("text",), ("text",)
    if model_type == "image_generation":
        if any(token in model for token in ("edit", "gpt-image", "image")):
            return ("text", "image"), ("image",)
        return ("text",), ("image",)
    if model_type == "video_generation":
        inputs = ["text"]
        if any(token in model for token in ("i2v", "flf2v", "image")):
            inputs.append("image")
        if any(token in model for token in ("v2v", "video")):
            inputs.append("video")
        return tuple(dict.fromkeys(inputs)), ("video",)
    if model_type == "audio":
        if any(token in model for token in ("whisper", "transcribe")):
            return ("audio",), ("text",)
        if "tts" in model or "lyria" in model:
            return ("text",), ("audio",)
        return ("text", "audio"), ("text", "audio")
    if model_type == "embedding":
        if catalog_provider_key == "gemini" and "embedding-2" in model:
            return ("text", "image", "audio", "video"), ("embedding",)
        return ("text",), ("embedding",)
    if model_type == "moderation":
        return ("text",), ("moderation",)
    if model_type == "translation":
        return ("text",), ("text",)
    if model_type == "3d_generation":
        return ("text", "image"), ("3d",)
    return (), ()


def _is_gemini_known_non_language_model(model: str) -> bool:
    return any(
        token in model
        for token in (
            "embedding",
            "imagen",
            "image",
            "nano-banana",
            "veo",
            "video",
            "tts",
            "chirp",
            "lyria",
        )
    )


def _official_catalog_library_entry(
    endpoint: ProviderEndpoint,
    model_id: str,
    raw_capabilities: dict[str, Any] | None = None,
) -> dict[str, object]:
    capabilities = _official_catalog_capabilities(endpoint, model_id, raw_capabilities)
    return {
        "model_id": model_id,
        "status": "catalog_candidate",
        "route_status": "unverified_manual",
        "last_probe_message": NO_VERIFIED_ROUTE_PROFILE_MESSAGE,
        "model_type": capabilities["model_type"],
        "model_type_label": capabilities["model_type_label"],
        "candidate_methods": capabilities["candidate_methods"],
        "input_modalities": capabilities["input_modalities"],
        "output_modalities": capabilities["output_modalities"],
        "input_modalities_source": capabilities["input_modalities_source"],
        "output_modalities_source": capabilities["output_modalities_source"],
        "input_modalities_source_urls": capabilities["input_modalities_source_urls"],
        "output_modalities_source_urls": capabilities["output_modalities_source_urls"],
        **_catalog_limit_fields(capabilities),
    }


def _official_failed_language_probe_entry(
    endpoint: ProviderEndpoint,
    model_id: str,
    last_probe_message: str | None = None,
    probe_attempts: list[dict[str, Any]] | None = None,
    raw_capabilities: dict[str, Any] | None = None,
) -> dict[str, object]:
    capabilities = _official_catalog_capabilities(endpoint, model_id, raw_capabilities)
    entry: dict[str, object] = {
        "model_id": model_id,
        "status": "probe_failed",
        "route_status": "failed",
        "last_probe_message": last_probe_message or NO_WORKING_OFFICIAL_LANGUAGE_METHOD_MESSAGE,
        "model_type": capabilities["model_type"],
        "model_type_label": capabilities["model_type_label"],
        "candidate_methods": capabilities["candidate_methods"],
        "input_modalities": capabilities["input_modalities"],
        "output_modalities": capabilities["output_modalities"],
        "input_modalities_source": capabilities["input_modalities_source"],
        "output_modalities_source": capabilities["output_modalities_source"],
        "input_modalities_source_urls": capabilities["input_modalities_source_urls"],
        "output_modalities_source_urls": capabilities["output_modalities_source_urls"],
        **_catalog_limit_fields(capabilities),
    }
    if probe_attempts:
        entry["probe_attempts"] = probe_attempts
    return entry


def _merged_capability_library_entries(
    endpoint: ProviderEndpoint,
    current_entries: list[dict[str, object]],
    *,
    verified_model_ids: set[str],
) -> list[dict[str, object]]:
    current_model_ids = {
        str(entry.get("model_id"))
        for entry in current_entries
        if isinstance(entry.get("model_id"), str) and entry.get("model_id")
    }
    stale_entries = [
        entry
        for entry in endpoint.metadata.get("capability_library", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("model_id"), str)
        and entry["model_id"] not in current_model_ids
        and entry["model_id"] not in verified_model_ids
    ]
    return [*stale_entries, *current_entries]


def _official_model_type_capability_values(
    endpoint: ProviderEndpoint,
    model_id: str,
    *,
    source: Literal["api_list", "probed_verified"],
) -> dict[str, CapabilityValue]:
    model_type, label = _official_catalog_model_type(endpoint, model_id)
    input_modalities, output_modalities = _official_catalog_modalities(
        endpoint,
        model_id,
        model_type,
    )
    backend = _endpoint_capability_source_key(endpoint)
    input_source_urls = official_doc_source_urls(
        backend,
        model_type=model_type,
        modalities=input_modalities,
    )
    output_source_urls = official_doc_source_urls(
        backend,
        model_type=model_type,
        modalities=output_modalities,
    )
    return {
        "model_type": CapabilityValue(value=model_type, source=source, message=label),
        "model_type_label": CapabilityValue(value=label, source=source),
        **(
            {
                "input_modalities": CapabilityValue(
                    value=list(input_modalities),
                    source="provider_doc",
                ),
                "input_modalities_source_urls": CapabilityValue(
                    value=list(input_source_urls),
                    source="provider_doc",
                ),
                "input_modalities_source": CapabilityValue(
                    value="provider_doc",
                    source="provider_doc",
                ),
            }
            if input_modalities
            else {}
        ),
        **(
            {
                "output_modalities": CapabilityValue(
                    value=list(output_modalities),
                    source="provider_doc",
                ),
                "output_modalities_source_urls": CapabilityValue(
                    value=list(output_source_urls),
                    source="provider_doc",
                ),
                "output_modalities_source": CapabilityValue(
                    value="provider_doc",
                    source="provider_doc",
                ),
            }
            if output_modalities
            else {}
        ),
    }


async def _probe_official_profile_batch(
    endpoint: ProviderEndpoint,
    model_ids: tuple[str, ...],
) -> list[OfficialModelProfileProbeResult]:
    if _endpoint_probe_is_disabled(endpoint):
        return [
            OfficialModelProfileProbeResult(
                model_id=model_id,
                last_probe_message=DISABLED_ENDPOINT_PROBE_MESSAGE,
            )
            for model_id in model_ids
        ]
    semaphore = asyncio.Semaphore(OFFICIAL_PROVIDER_TEST_CONCURRENCY)

    async def probe(model_id: str) -> OfficialModelProfileProbeResult:
        async with semaphore:
            return await _probe_official_model_profile_atom(endpoint, model_id)

    return await asyncio.gather(*(probe(model_id) for model_id in model_ids))


def _compact_model_info_for_listed_route(
    credentials: LLMCredentialsFile,
    endpoint: ProviderEndpoint,
    model_id: str,
    route_id: str | None,
    raw_capabilities: dict[str, Any] | None,
) -> EndpointTestCompactModelInfo:
    if endpoint.provider_kind == "official":
        return _compact_model_info_for_listed_official_route(
            credentials,
            endpoint,
            model_id,
            route_id,
            raw_capabilities,
        )
    route = credentials.provider_routes.get(route_id) if route_id is not None else None
    model_status: Literal["verified", "unverified_manual", "disabled", "failed", "testing", "probe-verified"]
    model_status = route.status if route is not None else "unverified_manual"
    return EndpointTestCompactModelInfo(
        id=model_id,
        route_id=route_id,
        status=model_status,
        verified_profile_count=0,
        last_probe_message=_route_failure_message(route),
        capabilities=raw_capabilities or {},
    )


def _compact_model_info_for_listed_official_route(
    credentials: LLMCredentialsFile,
    endpoint: ProviderEndpoint,
    model_id: str,
    route_id: str | None,
    raw_capabilities: dict[str, Any] | None,
) -> EndpointTestCompactModelInfo:
    route = credentials.provider_routes.get(route_id) if route_id is not None else None
    verified_profiles = (
        route.verified_profiles if route is not None and route.status == "verified" and route.verified_profiles else []
    )
    capabilities = (
        _official_verified_model_capabilities(
            endpoint,
            model_id,
            verified_profiles,
            _route_probe_attempts(route),
            raw_capabilities,
        )
        if verified_profiles
        else _official_catalog_capabilities(endpoint, model_id, raw_capabilities)
    )
    # is_probe_verified derives from the route's own evidence (SSOT, R9.3); with no
    # route there is no evidence, so the model is untested rather than probe-verified.
    is_probe_verified = route is not None and route_is_probe_verified(route)
    model_status: Literal["verified", "unverified_manual", "disabled", "failed", "testing", "probe-verified"]
    if route is not None:
        model_status = route.status
        if model_status == "unverified_manual" and is_probe_verified:
            model_status = "probe-verified"
    else:
        model_status = "unverified_manual"

    return EndpointTestCompactModelInfo(
        id=model_id,
        route_id=route_id,
        status=model_status,
        verified_profile_count=len(verified_profiles),
        last_probe_message=_route_failure_message(route),
        capabilities=capabilities,
    )


def _route_probe_attempts(route: ProviderRoute | None) -> list[dict[str, Any]] | None:
    if route is None:
        return None
    attempts = route.metadata.get("probe_attempts")
    if isinstance(attempts, list) and all(isinstance(attempt, dict) for attempt in attempts):
        return attempts
    return None


def _route_failure_message(route: ProviderRoute | None) -> str | None:
    if route is None or route.status != "failed":
        return None
    for key in ("last_probe_message", "failure_reason", "reason"):
        value = route.metadata.get(key)
        if isinstance(value, str) and value:
            return value
    attempts = _route_probe_attempts(route)
    if attempts:
        message = attempts[-1].get("message")
        if isinstance(message, str) and message:
            return message
    return "Route is marked failed; run a single-model test for details."


def _compact_model_infos_with_active_status(
    model_infos_by_id: dict[str, EndpointTestCompactModelInfo],
    active_model_ids: tuple[str, ...],
) -> list[EndpointTestCompactModelInfo]:
    active = set(active_model_ids)
    compact: list[EndpointTestCompactModelInfo] = []
    for model in model_infos_by_id.values():
        if (
            model.id in active
            and model.status in {None, "unverified_manual", "testing"}
            and not model.last_probe_message
        ):
            compact.append(
                model.model_copy(
                    update={
                        "status": "testing",
                        "last_probe_message": "Testing route.",
                    },
                )
            )
        else:
            compact.append(model)
    return compact


def _chunks(values: tuple[str, ...], size: int) -> list[tuple[str, ...]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _default_official_text_method(endpoint: ProviderEndpoint) -> tuple[str, str]:
    endpoint_id = endpoint.endpoint_id.lower()
    base_url = endpoint.base_url.lower()
    if endpoint.protocol == "anthropic_compatible":
        return "anthropic_messages", "anthropic_text"
    if endpoint.protocol == "google_genai":
        return "gemini_generate_content", "gemini_generate_content_text"
    if endpoint.protocol == "ark_runtime":
        return "ark_chat", "ark_chat_text"
    if "deepseek" in endpoint_id or "deepseek" in base_url:
        return "deepseek_chat_completions", "deepseek_chat_completions_text"
    return "openai_responses", "openai_responses_text"


def _role_test_entries(
    role: RoleEntry | ModelBundle,
) -> list[tuple[dict[str, Any], RoleRouteEntry | None]]:
    fallback_by_route = {entry.route_id: entry for entry in role.fallback_chain}
    report = role.materialization_report if isinstance(role.materialization_report, dict) else {}
    report_entries = [
        entry
        for entry in report.get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("route_id"), str)
    ]
    if report_entries:
        return [(entry, fallback_by_route.get(entry["route_id"])) for entry in report_entries]
    return [
        (
            {
                "route_id": entry.route_id,
                "role_fit": "using",
                "warnings": [],
                "resolved_settings": entry.runtime_settings.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
            },
            entry,
        )
        for entry in role.fallback_chain
    ]


def _merge_role_test_status(current: str, provider_result: dict[str, Any]) -> str:
    if current == "blocked" or provider_result["status"] == "blocked":
        return "blocked"
    if current == "failed" or provider_result["status"] == "failed":
        return "failed"
    if current == "warning" or provider_result["warnings"]:
        return "warning"
    return current


def _provider_model_projection(
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
) -> ProviderModelStateProjection:
    now = datetime.now(UTC)
    adapter = build_gateway_adapter()
    return adapter.project_route_state(
        {
            "endpoint": endpoint,
            "route": route,
            "circuits": _health_store().get_active_circuits(
                route_id=route.route_id,
                endpoint_id=endpoint.endpoint_id,
                rate_limit_bucket=endpoint.rate_limit_bucket or endpoint.endpoint_id,
                now=now,
            ),
            "now": now,
        }
    )


def _admission_decision(ui_state: str) -> str:
    if ui_state == "cooling_down":
        return "temporary_skip"
    if ui_state in {"failed", "off"}:
        return "block"
    return "admit"


def _successful_generation_probe_capabilities() -> dict[str, Any]:
    return {
        "model_type": "language_reasoning",
        "capability_family": "language_reasoning",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
    }


def _successful_multimodal_probe_capabilities() -> dict[str, Any]:
    """成功的多模态探测(provider 接受图输入)断言 input_modalities 含 image;
    normalize_route_capabilities 会据此自动派生 vision=True(capabilities.py)。"""
    return {
        "model_type": "language_reasoning",
        "capability_family": "language_reasoning",
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
    }


# apikeys#25: structural probe failures that will reject EVERY model on the
# endpoint (bad key / billing / URL does not speak this protocol), so the batch
# model-probe loop short-circuits instead of burning a probe per model.
# invalid_model is NOT structural — it is model-specific and means "this
# protocol reached the provider, that model id is just wrong", so the loop
# keeps trying other models.
_STRUCTURAL_PROBE_STATUSES: frozenset[str] = frozenset(
    {"invalid_key", "quota_exceeded", "protocol_unsupported"}
)
# How many candidate model ids the batch inference probe will try before giving
# up on an otherwise-reachable endpoint.
_ENDPOINT_PROBE_MODEL_LIMIT = 6
# Design §1.2 (protocol matrix) point 4: protocol_unsupported is an
# architectural fact about the (base_url, protocol) cell, so its observation
# has a long half-life — the routine Test skips the cell until it expires;
# `force=true` re-probes immediately.
_PROTOCOL_UNSUPPORTED_RECHECK = timedelta(days=30)


def _protocol_unsupported_recheck_at(endpoint: ProviderEndpoint) -> datetime | None:
    """When this cell's protocol_unsupported observation is due for re-probe.

    Returns ``None`` when the endpoint's latest observation is not
    protocol_unsupported (no gate applies).
    """
    if endpoint.last_error_code != "protocol_unsupported" or not endpoint.last_test_at:
        return None
    try:
        observed_at = datetime.fromisoformat(endpoint.last_test_at)
    except ValueError:
        return None
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    return observed_at + _PROTOCOL_UNSUPPORTED_RECHECK


@dataclass(frozen=True)
class EndpointGenerationVerification:
    """Outcome of the endpoint batch-inference verification (both provider kinds).

    ``status='verified'`` is set ONLY when a real generation probe (test_provider_route)
    returned ``ok`` — get-models reachability alone never reaches verified
    (apikeys#24/#25, revised 2026-07-01): a reachable endpoint can still be unable
    to generate, e.g. an exhausted credit balance keeps the model list working
    while every generation call fails.
    """

    # "no_model": get-models reached the provider (key+URL connectivity proven)
    # but there is no real model to verify generation — reachable-but-untested,
    # NOT a failure (W2-D / R-E1). The user adds a model id and single-model-tests.
    status: Literal["verified", "failed", "no_model", "skipped_disabled"]
    verified_model_id: str | None
    message: str
    probe_capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)
    # True when the failure is protocol-agnostic within this cell (invalid_key /
    # quota_exceeded / protocol_unsupported): the endpoint itself cannot generate,
    # so a prior verified route must NOT be reused.
    failure_is_structural: bool = False
    # The actual failing probe (model_id/status/latency/message) so the Test flow
    # can build a probe-failed evidence record for that real model (R3.1-AC3 /
    # codex-3) — not just a human message.
    failed_probe: RouteProbeResult | None = None
    # W2-E.1b diagnostics: every generation probe attempted, as
    # {protocol, model, status} — surfaced in the endpoint_test runtime-activity log
    # so the user can see which model probes were tried and how each fared.
    probe_attempts: list[dict[str, Any]] = field(default_factory=list)


def _base_url_hostname(base_url: str) -> str:
    raw_url = base_url.strip()
    if not raw_url:
        return ""
    try:
        parsed = urlsplit(raw_url)
        if parsed.hostname is None and "://" not in raw_url:
            parsed = urlsplit(f"//{raw_url}")
    except ValueError:
        return ""
    return (parsed.hostname or "").lower().strip(".")


def _endpoint_notable_provider_key(endpoint: ProviderEndpoint) -> str:
    # W3-A / T2: the qiniu / openrouter / wavespeed keyword+domain matches are
    # data-driven now (app/data/provider_identity.json) — a new provider is a config
    # edit, not a code change. Falls back to the probe backend for unconfigured hosts.
    text_haystack = " ".join([endpoint.endpoint_id, endpoint.display_name or ""])
    hostname = _base_url_hostname(endpoint.base_url)
    matched = notable_provider_key_for(text_haystack, hostname)
    if matched is not None:
        return matched
    official = official_provider_key_for_host(hostname)
    if official is not None:
        return official
    return _endpoint_probe_backend(endpoint)


def _endpoint_catalog_provider_key(endpoint: ProviderEndpoint) -> str:
    return _endpoint_notable_provider_key(endpoint)


def _endpoint_capability_source_key(endpoint: ProviderEndpoint) -> str:
    """Return the provider key used by official capability source tables.

    Catalog identity and capability-source identity are adjacent but not the same
    vocabulary: Anthropic models are cataloged under the provider key
    ``anthropic``, while the existing official capability source table is keyed
    by the model family ``claude``.
    """
    catalog_provider_key = _endpoint_catalog_provider_key(endpoint)
    if catalog_provider_key == "anthropic":
        return "claude"
    return catalog_provider_key


def _prioritize_notable_probe_models(
    endpoint: ProviderEndpoint,
    candidate_model_ids: Sequence[str],
) -> list[str]:
    requested = _requested_model_ids(candidate_model_ids)
    if not requested:
        return []
    notable = notable_model_ids(_endpoint_notable_provider_key(endpoint))
    if not notable:
        return requested
    requested_set = set(requested)
    prioritized = [model_id for model_id in notable if model_id in requested_set]
    prioritized_set = set(prioritized)
    return [
        *prioritized,
        *(model_id for model_id in requested if model_id not in prioritized_set),
    ]


def _endpoint_generation_probe_model_ids(
    endpoint: ProviderEndpoint,
    discovered_model_ids: tuple[str, ...],
) -> list[str]:
    """Pick the model ids to drive the endpoint batch inference probe.

    Discovered ids (from the get-models call) drive the candidate set, falling
    back to the endpoint's own known routes. We do NOT invent candidates from the
    doc-maintained notable ids (W2-D / R-E1): an endpoint that lists no models and
    has no known routes returns an empty candidate set, so the Test stays
    reachable-but-untested rather than probing a guessed phantom model. The real
    candidates are then ordered by ``endpoint_probe_priority`` (R9.4) so the probe
    leads with a known-good model — all derived from credentials, not the catalog.
    """
    credentials = load_credentials()
    candidates = list(discovered_model_ids)
    if not candidates:
        # model-list truth = routes (R3.4): fall back to the endpoint's known routes.
        candidates = endpoint_listed_model_ids(credentials, endpoint.endpoint_id)
    if endpoint.provider_kind == "official":
        # Official model lists mix in non-language models (image / audio /
        # embedding); a text-generation probe can only prove anything on a
        # language model, so restrict the candidates to those.
        candidates = [
            model_id
            for model_id in candidates
            if _official_catalog_model_type(endpoint, model_id)[0] == "language_reasoning"
        ]
    # W2-D / R-E1: NO doc-maintained "notable" fallback. If get-models returned no
    # models and the endpoint has no known routes, there is nothing real to probe —
    # return empty so the endpoint Test stays reachable-but-untested (the user adds
    # a model id and single-model-tests) instead of probing a guessed phantom model
    # (this is what wrongly drove WaveSpeed to "failed" on a guessed o3-mini).
    if not candidates:
        return []
    prioritized_candidates = _prioritize_notable_probe_models(endpoint, candidates)
    ordered = endpoint_probe_priority(
        credentials,
        endpoint.endpoint_id,
        prioritized_candidates,
    )
    return ordered[:_ENDPOINT_PROBE_MODEL_LIMIT]


async def _verify_endpoint_by_generation_probe(
    endpoint: ProviderEndpoint,
    discovered_model_ids: tuple[str, ...],
    raw_capabilities_by_model: dict[str, dict[str, Any]],
    *,
    allow_disabled: bool = False,
) -> EndpointGenerationVerification:
    """Run batch inference probing to verify an endpoint can actually generate.

    apikeys#24/#25 + design protocol matrix (2026-07-02): an endpoint is one
    immutable (base_url, protocol) cell, so the batch probes with the endpoint's
    OWN protocol only: no candidate rotation, no clone-with-another-protocol,
    no protocol rewrite. get-models only proves key+URL reachability, so the
    endpoint is promoted to ``verified`` ONLY when a real generation probe
    returns ``ok``. Every attempt lands in ``probe_attempts`` (the old rotation
    swallowed its intermediate failures, which made protocol flips unexplainable
    from the runtime log). The batch stops on the first ``ok`` and
    short-circuits structural errors (invalid_key / quota_exceeded /
    protocol_unsupported, all of which reject every model on this cell).
    Each concrete generation attempt goes through ``_probe_model_generation_atom``;
    that atom owns the live active-model event used by the UI animation.
    """
    probe_attempts: list[dict[str, Any]] = []
    if _endpoint_probe_is_disabled(endpoint, allow_disabled=allow_disabled):
        return EndpointGenerationVerification(
            status="skipped_disabled",
            verified_model_id=None,
            message=DISABLED_ENDPOINT_PROBE_MESSAGE,
            probe_attempts=probe_attempts,
        )
    probe_model_ids = _endpoint_generation_probe_model_ids(
        endpoint,
        discovered_model_ids,
    )
    if not probe_model_ids:
        # W2-D / R-E1: get-models reached the provider (connectivity proven) but no
        # real model is available to verify generation. Reachable-but-untested, NOT
        # failed: the user adds a model id and runs a single-model test.
        return EndpointGenerationVerification(
            status="no_model",
            verified_model_id=None,
            message=(
                "Endpoint reachable, but it returned no models to verify. "
                "Add a model id and run a single-model test."
            ),
            probe_attempts=probe_attempts,
        )

    last_failure: RouteProbeResult | None = None
    for model_id in probe_model_ids:
        probe = await _probe_model_generation_atom(
            endpoint,
            model_id,
            allow_disabled=allow_disabled,
        )
        probe_attempts.append(
            {"protocol": endpoint.protocol, "model": model_id, "status": probe.status}
        )
        if probe.status == "ok":
            logger.info(
                "endpoint batch probe verified endpoint=%s protocol=%s model=%s",
                endpoint.endpoint_id,
                endpoint.protocol,
                model_id,
            )
            return EndpointGenerationVerification(
                status="verified",
                verified_model_id=model_id,
                message=f"Generation verified via {endpoint.protocol}. Model: {model_id}.",
                probe_capabilities={
                    model_id: _third_party_probe_capabilities(
                        model_id,
                        raw_capabilities_by_model.get(model_id),
                    )
                },
                probe_attempts=probe_attempts,
            )
        last_failure = probe
        if probe.status in _STRUCTURAL_PROBE_STATUSES:
            logger.warning(
                "endpoint batch probe short-circuit endpoint=%s status=%s",
                endpoint.endpoint_id,
                probe.status,
            )
            break

    assert last_failure is not None  # probe_model_ids is non-empty => loop probed
    return EndpointGenerationVerification(
        status="failed",
        verified_model_id=None,
        message=_model_probe_failure_message(
            _model_probe_result_from_route_probe(last_failure)
        ),
        failure_is_structural=last_failure.status in _STRUCTURAL_PROBE_STATUSES,
        failed_probe=last_failure,
        probe_attempts=probe_attempts,
    )


async def _probe_third_party_models_for_endpoint(
    endpoint: ProviderEndpoint,
    discovered_model_ids: tuple[str, ...],
) -> list[ModelProbeResult]:
    probe_model_ids = _endpoint_generation_probe_model_ids(endpoint, discovered_model_ids)
    results: list[ModelProbeResult] = []
    for model_id in probe_model_ids:
        result = _model_probe_result_from_route_probe(
            await _probe_model_generation_atom(endpoint, model_id)
        )
        results.append(result)
        if result.status in _STRUCTURAL_PROBE_STATUSES:
            break
    return results


def _endpoint_status_from_model_probe_results(
    probe_results: list[ModelProbeResult],
) -> Literal["verified", "failed"]:
    return "verified" if any(result.status == "ok" for result in probe_results) else "failed"


def _endpoint_message_from_model_probe_results(probe_results: list[ModelProbeResult]) -> str:
    successful = [result for result in probe_results if result.status == "ok"]
    if successful:
        return f"Connected. Model seen: {successful[0].model_id}."
    if probe_results:
        return _model_probe_failure_message(probe_results[-1])
    return "Endpoint reachable but no model ids were available to probe."


async def _list_model_capabilities_for_endpoint(
    endpoint: ProviderEndpoint,
) -> dict[str, dict[str, Any]]:
    """Fetch the endpoint's list-models rich capabilities, keyed by model id.

    apikeys#27: the third-party manual-model probe path derives capabilities from
    the endpoint's list API (the same rich fields the official side normalizes),
    so official and third-party return a symmetric capability structure. Returns
    an empty mapping when the list call is unreachable — callers then fall back to
    the generation-probe default per model.
    """
    result = await _probe_endpoint_model_list_atom(endpoint)
    if result.status != "ok":
        logger.info(
            "list-models capabilities unavailable endpoint=%s status=%s",
            endpoint.endpoint_id,
            result.status,
        )
        return {}
    return dict(result.model_capabilities)


def _gateway_probe_route(endpoint: ProviderEndpoint, model_id: str) -> ProviderRoute:
    """Build a throwaway ProviderRoute used only to drive test_provider_route."""
    route_slug = _route_slug(model_id)
    return ProviderRoute(
        route_id=f"{endpoint.endpoint_id}:{route_slug}",
        endpoint_id=endpoint.endpoint_id,
        route_slug=route_slug,
        provider_model_id=model_id,
        canonical_id=model_id,
    )


def _third_party_probe_capabilities(
    model_id: str,
    raw_capabilities: dict[str, Any] | None,
) -> dict[str, Any]:
    """Prefer the list-models rich capabilities; fall back to the text-only default.

    apikeys#27: third-party capability must come from the endpoint's list-models
    rich fields (normalized) when available, not be hard-coded text-only. The
    generation-probe default is only used when the list API gave us nothing.
    """
    del model_id
    if raw_capabilities:
        return dict(raw_capabilities)
    return _successful_generation_probe_capabilities()


def _third_party_route_capability_values(
    endpoint: ProviderEndpoint,
    model_id: str,
    raw_capabilities: dict[str, Any],
    *,
    source: Literal["api_list", "probed_verified"],
) -> dict[str, CapabilityValue]:
    capabilities = normalize_route_capabilities(
        protocol=endpoint.protocol,
        provider_model_id=model_id,
        raw_capabilities=raw_capabilities,
        source=source,
    )
    model_type = _raw_model_type(raw_capabilities) or _model_type_from_modalities(capabilities)
    if model_type is None:
        return capabilities
    label = _model_type_label(model_type)
    capabilities.setdefault(
        "model_type",
        CapabilityValue(value=model_type, source=source, message=label),
    )
    capabilities.setdefault(
        "model_type_label",
        CapabilityValue(value=label, source=source),
    )
    capabilities.setdefault(
        "capability_family",
        CapabilityValue(value=model_type, source=source, message=label),
    )
    return capabilities


def _raw_model_type(raw_capabilities: dict[str, Any]) -> str | None:
    for key in ("model_type", "capability_family"):
        value = raw_capabilities.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _model_type_from_modalities(
    capabilities: dict[str, CapabilityValue],
) -> str | None:
    input_modalities = _capability_string_list(capabilities, "input_modalities")
    output_modalities = _capability_string_list(capabilities, "output_modalities")
    if "text" in input_modalities and "text" in output_modalities:
        return "language_reasoning"
    if "image" in output_modalities:
        return "image_generation"
    if "video" in output_modalities:
        return "video_generation"
    if "audio" in output_modalities:
        return "audio"
    if "embedding" in output_modalities:
        return "embedding"
    if "translation" in output_modalities:
        return "translation"
    if "3d" in output_modalities:
        return "3d_generation"
    if "moderation" in output_modalities:
        return "moderation"
    return None


def _model_type_label(model_type: str) -> str:
    return {
        "language_reasoning": "Language/reasoning model",
        "image_generation": "Image generation model",
        "video_generation": "Video generation model",
        "audio": "Audio/realtime model",
        "embedding": "Embedding model",
        "translation": "Translation model",
        "3d_generation": "3D generation model",
        "moderation": "Moderation model",
        "interactions_agent": "Interactions API agent",
    }.get(model_type, model_type.replace("_", " ").title())


def _upsert_discovered_routes(
    credentials: LLMCredentialsFile,
    *,
    endpoint: ProviderEndpoint,
    model_ids: tuple[str, ...],
    verified: bool,
    replace_endpoint_routes: bool = False,
    verified_profiles_by_model: dict[str, list[VerifiedProfile]] | None = None,
    probe_attempts_by_model: dict[str, list[dict[str, Any]]] | None = None,
    raw_capabilities_by_model: dict[str, dict[str, Any]] | None = None,
) -> tuple[LLMCredentialsFile, dict[str, str]]:
    routes = dict(credentials.provider_routes)
    route_ids_by_model: dict[str, str] = {}
    for model_id in model_ids:
        route_id = _route_id(endpoint.endpoint_id, model_id, routes)
        route_ids_by_model[model_id] = route_id
        existing = routes.get(route_id)
        status: Literal["verified", "unverified_manual"] = "verified" if verified else "unverified_manual"
        capability_source: Literal["api_list", "probed_verified"] = "probed_verified" if verified else "api_list"
        if existing is None:
            route = _provider_route(
                endpoint=endpoint,
                model_id=model_id,
                status=status,
                capability_source=capability_source,
                verified_profiles=(verified_profiles_by_model or {}).get(model_id, []),
                probe_attempts=(probe_attempts_by_model or {}).get(model_id, []),
                raw_capabilities=(raw_capabilities_by_model or {}).get(model_id, {}),
            )
            routes[route_id] = route
            continue
        updates: dict[str, Any] = {}
        if verified:
            base_capabilities = {
                **existing.capabilities,
                **(
                    _official_model_type_capability_values(
                        endpoint,
                        model_id,
                        source=capability_source,
                    )
                    if endpoint.provider_kind == "official"
                    else {}
                ),
                **(
                    _provider_doc_limit_capability_values(endpoint, model_id)
                    if endpoint.provider_kind == "official"
                    else {}
                ),
                **(
                    _official_normalized_route_capabilities(
                        endpoint,
                        model_id,
                        (raw_capabilities_by_model or {}).get(model_id, {}),
                    )
                    if endpoint.provider_kind == "official"
                    else _third_party_route_capability_values(
                        endpoint,
                        model_id,
                        (raw_capabilities_by_model or {}).get(model_id, {}),
                        source=capability_source,
                    )
                ),
            }
            updates["status"] = "verified"
            updates["capabilities"] = _merge_profile_capabilities(
                base_capabilities,
                verified_profile_route_capabilities((verified_profiles_by_model or {}).get(model_id, [])),
            )
        if probe_attempts_by_model and probe_attempts_by_model.get(model_id):
            updates["metadata"] = {
                **existing.metadata,
                "probe_attempts": probe_attempts_by_model[model_id],
            }
        if verified_profiles_by_model and model_id in verified_profiles_by_model:
            updates["verified_profiles"] = verified_profiles_by_model[model_id]
        route = existing.model_copy(update=updates) if updates else existing
        routes[route_id] = route
    if replace_endpoint_routes:
        discovered_model_ids = set(model_ids)
        routes = {
            route_id: route
            for route_id, route in routes.items()
            if route.endpoint_id != endpoint.endpoint_id or route.provider_model_id in discovered_model_ids
        }
    return credentials.model_copy(update={"provider_routes": routes}), route_ids_by_model


def _upsert_third_party_model_probe_routes(
    credentials: LLMCredentialsFile,
    *,
    endpoint: ProviderEndpoint,
    probe_results: tuple[ModelProbeResult, ...],
    raw_capabilities_by_model: dict[str, dict[str, Any]] | None = None,
) -> tuple[LLMCredentialsFile, dict[str, str]]:
    routes = dict(credentials.provider_routes)
    route_ids_by_model: dict[str, str] = {}
    for result in probe_results:
        route_id = _route_id(endpoint.endpoint_id, result.model_id, routes)
        route_ids_by_model[result.model_id] = route_id
        existing = routes.get(route_id)
        status: Literal["verified", "failed"] = "verified" if result.status == "ok" else "failed"
        raw_capabilities = (raw_capabilities_by_model or {}).get(result.model_id, {})
        metadata = {
            **(existing.metadata if existing is not None else {}),
            "last_probe_message": None if result.status == "ok" else _model_probe_failure_message(result),
            "reason_code": result.status,
            "probe_attempts": [
                {
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "message": result.message,
                }
            ],
        }
        route = _provider_route(
            endpoint=endpoint,
            model_id=result.model_id,
            status=status,
            capability_source="probed_verified" if status == "verified" else "api_list",
            raw_capabilities=raw_capabilities,
            probe_attempts=metadata["probe_attempts"],
        )
        if existing is not None:
            route = route.model_copy(
                update={
                    "display_name": existing.display_name,
                    "metadata": metadata,
                }
            )
        else:
            route = route.model_copy(update={"metadata": metadata})
        routes[route_id] = route
    return credentials.model_copy(update={"provider_routes": routes}), route_ids_by_model


def _upsert_failed_official_model_routes(
    credentials: LLMCredentialsFile,
    *,
    endpoint: ProviderEndpoint,
    profile_results: tuple[OfficialModelProfileProbeResult, ...],
) -> tuple[LLMCredentialsFile, dict[str, str]]:
    routes = dict(credentials.provider_routes)
    route_ids_by_model: dict[str, str] = {}
    for result in profile_results:
        route_id = _route_id(endpoint.endpoint_id, result.model_id, routes)
        route_ids_by_model[result.model_id] = route_id
        existing = routes.get(route_id)
        message = _official_role_test_profile_probe_failure_message(result)
        metadata = {
            **(existing.metadata if existing is not None else {}),
            "reason_code": "profile_probe_failed",
            "last_probe_message": message,
        }
        if result.probe_attempts:
            metadata["probe_attempts"] = result.probe_attempts
        if existing is None:
            route = _provider_route(
                endpoint=endpoint,
                model_id=result.model_id,
                status="failed",
                capability_source="api_list",
                probe_attempts=result.probe_attempts,
            )
            routes[route_id] = route.model_copy(update={"metadata": metadata})
            continue
        routes[route_id] = existing.model_copy(
            update={
                "status": "failed",
                "verified_profiles": [],
                "metadata": metadata,
            }
        )
    return credentials.model_copy(update={"provider_routes": routes}), route_ids_by_model


def _provider_route(
    *,
    endpoint: ProviderEndpoint,
    model_id: str,
    status: Literal["verified", "unverified_manual", "failed"],
    capability_source: Literal["api_list", "probed_verified"],
    verified_profiles: list[VerifiedProfile] | None = None,
    probe_attempts: list[dict[str, Any]] | None = None,
    raw_capabilities: dict[str, Any] | None = None,
) -> ProviderRoute:
    route_slug = _route_slug(model_id)
    canonical = canonicalize_model(endpoint_id=endpoint.endpoint_id, provider_model_id=route_slug)
    return ProviderRoute(
        route_id=f"{endpoint.endpoint_id}:{route_slug}",
        endpoint_id=endpoint.endpoint_id,
        route_slug=route_slug,
        provider_model_id=model_id,
        canonical_id=canonical.canonical_id,
        status=status,
        capabilities=_merge_profile_capabilities(
            {
                **(
                    _official_model_type_capability_values(
                        endpoint,
                        model_id,
                        source=capability_source,
                    )
                    if endpoint.provider_kind == "official"
                    else {}
                ),
                **(
                    _provider_doc_limit_capability_values(endpoint, model_id)
                    if endpoint.provider_kind == "official"
                    else {}
                ),
                **(
                    _official_normalized_route_capabilities(
                        endpoint,
                        model_id,
                        raw_capabilities or {},
                    )
                    if endpoint.provider_kind == "official"
                    else _third_party_route_capability_values(
                        endpoint,
                        model_id,
                        raw_capabilities or {},
                        source=capability_source,
                    )
                ),
            },
            verified_profile_route_capabilities(verified_profiles or []),
        ),
        verified_profiles=verified_profiles or [],
        metadata={"probe_attempts": probe_attempts} if probe_attempts else {},
    )


def _merge_profile_capabilities(
    base_capabilities: dict[str, CapabilityValue],
    profile_capabilities: dict[str, CapabilityValue],
) -> dict[str, CapabilityValue]:
    capabilities = {**base_capabilities, **profile_capabilities}
    for key in ("input_modalities", "output_modalities"):
        base_value = base_capabilities.get(key)
        profile_value = profile_capabilities.get(key)
        if base_value is None or profile_value is None:
            continue
        if not isinstance(base_value.value, list) or not isinstance(profile_value.value, list):
            continue
        merged = _ordered_unique([item for item in [*base_value.value, *profile_value.value] if isinstance(item, str)])
        capabilities[key] = base_value.model_copy(update={"value": merged})
    return capabilities


def _route_id(
    endpoint_id: str,
    model_id: str,
    routes: dict[str, ProviderRoute] | None = None,
) -> str:
    base_slug = _route_slug(model_id)
    route_id = f"{endpoint_id}:{base_slug}"
    if not routes:
        return route_id
    existing = routes.get(route_id)
    if existing is None or existing.provider_model_id == model_id:
        return route_id
    suffix = hashlib.sha256(f"{endpoint_id}:{model_id}".encode()).hexdigest()[:8]
    return f"{endpoint_id}:{base_slug}-{suffix}"


def _requested_model_ids(model_ids: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    requested: list[str] = []
    for model_id in model_ids:
        normalized = model_id.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        requested.append(normalized)
    return requested


def _role_effective_runtime_settings(
    credentials: LLMCredentialsFile,
    roles: RolesData,
) -> dict[str, dict[str, dict[str, Any]]]:
    adapter = build_gateway_adapter()
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for role_name in roles.roles:
        try:
            resolved = adapter.resolve_routes(
                {
                    "role_name": role_name,
                    "credentials": credentials,
                    "roles": roles,
                }
            )
        except RegistryResolutionError:
            result[role_name] = {}
            continue
        except Exception as exc:
            if getattr(exc, "error_code", None) != "resource.no_available_route":
                raise
            result[role_name] = {}
            continue
        result[role_name] = {
            route.route_id: route.effective_runtime_settings for route in resolved.routes
        }
    return result


def _load_roles_or_empty(path: Path | None = None) -> RolesData:
    active_path = path or roles_path()
    if not active_path.exists():
        return RolesData()
    return load_roles_file(active_path)


def _materialize_roles_for_response(
    data: RolesData,
    credentials: LLMCredentialsFile | None = None,
) -> RolesData:
    has_role_authoring = any(role.model_groups for role in data.roles.values())
    has_bundle_authoring = any(bundle.model_groups for bundle in data.model_bundles.values())
    # #51: a pure bundle-reference role (bundle_id set, no own model_groups) also
    # needs materialization — its chain comes from the referenced bundle.
    has_reference_roles = any(role.bundle_id for role in data.roles.values())
    if not has_role_authoring and not has_bundle_authoring and not has_reference_roles:
        return data
    active_credentials = credentials or load_credentials()
    adapter = build_gateway_adapter()
    materialized_bundles = {
        bundle_id: adapter.materialize_model_bundle(
            {
                "bundle": bundle,
                "credentials": active_credentials,
            }
        )
        if bundle.model_groups
        else bundle
        for bundle_id, bundle in data.model_bundles.items()
    }
    return data.model_copy(
        update={
            "schema_version": 3,
            "roles": {
                role_name: _materialize_one_role_for_response(
                    role,
                    materialized_bundles,
                    active_credentials,
                    adapter,
                )
                for role_name, role in data.roles.items()
            },
            "model_bundles": materialized_bundles,
        }
    )


def _materialize_one_role_for_response(
    role: RoleEntry,
    materialized_bundles: dict[str, ModelBundle],
    credentials: LLMCredentialsFile,
    adapter: Any,
) -> RoleEntry:
    """Materialize one role for the registry response.

    A role with its own model_groups materializes directly (existing path). A
    pure bundle-reference role (#51: bundle_id set, no own model_groups) delegates
    the bundle+delta overlay to the gateway resolver's ``materialize_role_entry``:
    we hand it a snapshot whose ``model_bundles`` already carry the bundle's
    flattened chain + report, and the role's own ``fallback_chain`` is the local
    delta the overlay applies. The shell never hand-rolls the merge.
    """
    if role.model_groups:
        return cast(
            RoleEntry,
            adapter.materialize_role(
                {
                    "role": role,
                    "credentials": credentials,
                }
            ),
        )
    if not role.bundle_id:
        return role
    bundle = materialized_bundles.get(role.bundle_id)
    if bundle is None:
        # #52 delete cascade: the referenced bundle is gone. Surface a not-fit
        # role with an empty chain rather than raising mid-response.
        logger.warning(
            "role references missing model bundle %s; materializing empty chain",
            role.bundle_id,
        )
        return role.model_copy(update={"fallback_chain": []})
    return _materialize_reference_role(role, bundle)


def _materialize_reference_role(role: RoleEntry, bundle: ModelBundle) -> RoleEntry:
    """Overlay a role's local delta onto a referenced bundle via the gateway.

    The by-reference + delta overlay is owned by the gateway resolver
    (materialize_role_entry); ``overlay_bundle_reference_chain`` plumbs the role +
    materialized bundle into it. The bundle's materialization_report (role-fit per
    route) is carried onto the role so the status lights project.
    """
    fallback_chain = overlay_bundle_reference_chain(role, bundle)
    return role.model_copy(
        update={
            "fallback_chain": fallback_chain,
            "materialization_report": dict(bundle.materialization_report),
        }
    )


def _materialize_role_for_response(
    role: RoleEntry,
    credentials: LLMCredentialsFile | None = None,
) -> RoleEntry:
    if not role.model_groups:
        return role
    adapter = build_gateway_adapter()
    return cast(
        RoleEntry,
        adapter.materialize_role(
            {
                "role": role,
                "credentials": credentials or load_credentials(),
            }
        ),
    )


def bundle_role_name(bundle_id: str) -> str:
    """The __bundle__ job key (#50b): keeps bundle test results out of the role
    results namespace; mirrors the frontend bundleRoleName(bundleId)."""
    return f"__bundle__{bundle_id}"


def compare_candidate_role_name(request: CompareCandidateTestRequest) -> str:
    """Ephemeral job key for a node compare candidate."""
    raw = request.route_id or request.canonical_id
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-") or "candidate"
    return f"__compare__{slug}"


def _compare_candidate_role(
    request: CompareCandidateTestRequest,
    credentials: LLMCredentialsFile,
) -> RoleEntry:
    routes = _compare_candidate_routes(request, credentials)
    display_name = _model_group_identity(request.canonical_id, routes, credentials)["display_name"]
    return RoleEntry(
        model_groups=[
            RoleModelGroup(
                canonical_id=request.canonical_id,
                display_name=display_name,
                provider_models=[
                    RoleProviderModel(route_id=route.route_id)
                    for route in sorted(routes, key=lambda route: route.route_id)
                ],
            )
        ],
    )


def _compare_candidate_routes(
    request: CompareCandidateTestRequest,
    credentials: LLMCredentialsFile,
) -> list[ProviderRoute]:
    canonical_id = request.canonical_id.strip()
    requested_route_id = request.route_id.strip().removeprefix("route:").strip() if request.route_id else None
    if not canonical_id:
        raise HTTPException(status_code=400, detail="Compare candidate canonical_id is required.")

    normalized_id = normalize_model_group_key(canonical_id)
    routes_by_identity: dict[str, list[ProviderRoute]] = {}
    for route in credentials.provider_routes.values():
        if not _include_route_in_model_groups(route, credentials):
            continue
        routes_by_identity.setdefault(
            _model_group_identity_key(route, credentials),
            [],
        ).append(route)

    candidate_groups: list[list[ProviderRoute]] = []
    for identity_key, routes in routes_by_identity.items():
        representative = _representative_canonical_id(routes, credentials)
        route_canonical_ids = {route.canonical_id for route in routes if route.canonical_id}
        if (
            identity_key == normalized_id
            or normalize_model_group_key(representative) == normalized_id
            or canonical_id in route_canonical_ids
        ):
            candidate_groups.append(routes)

    if not candidate_groups:
        raise HTTPException(status_code=404, detail=f"Unknown model group: {canonical_id}")

    routes = [
        route
        for group in candidate_groups
        for route in group
        if requested_route_id is None or route.route_id == requested_route_id
    ]
    if not routes:
        detail = f"Unknown route for model group {canonical_id}: {requested_route_id}"
        raise HTTPException(status_code=404, detail=detail)
    return routes


def _materialize_bundle_for_response(
    bundle: ModelBundle,
    credentials: LLMCredentialsFile | None = None,
) -> ModelBundle:
    """Materialize a bundle into its flat chain + report via the gateway (#50b).

    Wraps the bundle into a transient role-like entry (materialize_model_bundle);
    the persisted roles store is never written.
    """
    if not bundle.model_groups:
        return bundle
    adapter = build_gateway_adapter()
    return cast(
        ModelBundle,
        adapter.materialize_model_bundle(
            {
                "bundle": bundle,
                "credentials": credentials or load_credentials(),
            }
        ),
    )


def _save_roles_with_active_routes(data: RolesData) -> RolesData:
    active_path = roles_path()
    active_route_ids = set(load_credentials().provider_routes)
    # #51: bundle ids are slugged by model_profile_id; a role's bundle_id must
    # point at one of these or it is a dangling reference.
    known_bundle_ids = {bundle.model_profile_id for bundle in data.model_bundles.values()}
    try:
        validate_references(
            data,
            known_route_ids=active_route_ids,
            known_bundle_ids=known_bundle_ids,
        )
        save_roles_file(
            active_path,
            data,
            known_route_ids=active_route_ids,
            known_bundle_ids=known_bundle_ids,
        )
        reloaded = load_roles_file(active_path)
    except InvalidRoleReference as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 底座一: no gateway snapshot to refresh — build_gateway_route_runtime now reads
    # the on-disk truth fresh on every call, so the just-saved roles are seen
    # immediately (e.g. by the next copilot test-sdk) without a sync hook.
    return reloaded


def _reconcile_fixed_roles_after_credential_change() -> list[str]:
    """凭证变更后自动把固定角色缺的推荐模型组补齐(用户在 API Keys 配好模型 → 固定
    角色即自动可用,不用手动去角色页拖)。组级粒度,不动用户已删的 endpoint;没改就不写盘。
    返回被补齐的角色名(便于活动日志)。"""
    from app.services.llm_fixed_roles import reconcile_fixed_roles

    if not roles_path().exists():
        return []
    credentials = load_credentials()
    roles = _load_roles_or_empty()
    updated, changed = reconcile_fixed_roles(roles, credentials)
    if not changed:
        return []
    _save_roles_with_active_routes(updated)
    record_runtime_activity(
        source_id="llm_roles",
        action="reconcile_fixed_roles",
        message="Auto-filled fixed roles with newly available recommended models.",
        changes={"role_names": sorted(changed)},
    )
    return changed


def _now_iso() -> str:
    """R-F10: ISO-8601 UTC timestamp for roles_changed broadcast payloads."""
    return datetime.now(UTC).isoformat()


async def _publish_roles_changed() -> None:
    """R-F10: broadcast a ``roles_changed`` event on the studio events topic
    after a PUT/DELETE roles endpoint successfully writes to disk. Failure
    here is logged via ``logger.exception`` but never propagates — a downed
    event bus must not corrupt the just-completed write.
    """
    payload: dict[str, Any] = {
        "type": "roles_changed",
        "timestamp": _now_iso(),
        "source": "http_api",
    }
    try:
        await event_bus.publish(STUDIO_EVENTS_TOPIC, payload)
    except Exception:
        logger.exception(
            "phase=publish_roles_changed action=publish status=failed payload=%s",
            payload,
        )


async def _publish_llm_probe_active(
    endpoint_id: str,
    active_model_ids: tuple[str, ...],
) -> None:
    payload: dict[str, Any] = {
        "type": "llm_probe_active",
        "timestamp": _now_iso(),
        "source": "http_api",
        "endpoint_id": endpoint_id,
        "active_model_ids": list(active_model_ids),
    }
    try:
        await event_bus.publish(STUDIO_EVENTS_TOPIC, payload)
    except Exception:
        logger.exception(
            "phase=publish_llm_probe_active action=publish status=failed payload=%s",
            payload,
        )


def _endpoint_references(
    endpoint_id: str,
    credentials: LLMCredentialsFile,
    roles: RolesData,
) -> dict[str, list[str]]:
    route_ids = [
        route_id for route_id, route in credentials.provider_routes.items() if route.endpoint_id == endpoint_id
    ]
    refs = {"routes": route_ids, "roles": [], "model_profiles": [], "model_bundles": []}
    route_set = set(route_ids)
    for role_name, role in roles.roles.items():
        refs["roles"].extend(_role_route_references(role_name, role, route_set))
    for profile_id, profile in roles.model_profiles.items():
        for index, entry in enumerate(profile.fallback_chain):
            if entry.route_id in route_set:
                refs["model_profiles"].append(f"{profile_id}.fallback_chain[{index}]")
    for bundle_id, bundle in roles.model_bundles.items():
        refs["model_bundles"].extend(_bundle_route_references(bundle_id, bundle, route_set))
    return refs


def _remove_route_references_from_roles(
    data: RolesData,
    route_ids: set[str],
) -> RolesData:
    roles = {
        role_name: role.model_copy(
            update={
                "fallback_chain": [entry for entry in role.fallback_chain if entry.route_id not in route_ids],
                "model_groups": [
                    group.model_copy(
                        update={
                            "provider_models": [
                                provider_model
                                for provider_model in group.provider_models
                                if provider_model.route_id not in route_ids
                            ]
                        }
                    )
                    for group in role.model_groups
                ],
            }
        )
        for role_name, role in data.roles.items()
    }
    model_profiles = {
        profile_id: profile.model_copy(
            update={"fallback_chain": [entry for entry in profile.fallback_chain if entry.route_id not in route_ids]}
        )
        for profile_id, profile in data.model_profiles.items()
    }
    model_bundles = {
        bundle_id: bundle.model_copy(
            update={
                "fallback_chain": [entry for entry in bundle.fallback_chain if entry.route_id not in route_ids],
                "model_groups": [
                    group.model_copy(
                        update={
                            "provider_models": [
                                provider_model
                                for provider_model in group.provider_models
                                if provider_model.route_id not in route_ids
                            ]
                        }
                    )
                    for group in bundle.model_groups
                ],
            }
        )
        for bundle_id, bundle in data.model_bundles.items()
    }
    return data.model_copy(
        update={
            "roles": roles,
            "model_profiles": model_profiles,
            "model_bundles": model_bundles,
        }
    )


def _route_references(route_id: str, roles: RolesData) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {"roles": [], "model_profiles": [], "model_bundles": []}
    for role_name, role in roles.roles.items():
        refs["roles"].extend(_role_route_references(role_name, role, {route_id}))
    for profile_id, profile in roles.model_profiles.items():
        for index, entry in enumerate(profile.fallback_chain):
            if entry.route_id == route_id:
                refs["model_profiles"].append(f"{profile_id}.fallback_chain[{index}]")
    for bundle_id, bundle in roles.model_bundles.items():
        refs["model_bundles"].extend(_bundle_route_references(bundle_id, bundle, {route_id}))
    return refs


def _role_route_references(
    role_name: str,
    role: RoleEntry,
    route_ids: set[str],
) -> list[str]:
    refs: list[str] = []
    for index, entry in enumerate(role.fallback_chain):
        if entry.route_id in route_ids:
            refs.append(f"{role_name}.fallback_chain[{index}]")
    for group_index, group in enumerate(role.model_groups):
        for provider_index, provider_model in enumerate(group.provider_models):
            if provider_model.route_id in route_ids:
                refs.append(f"{role_name}.model_groups[{group_index}].provider_models[{provider_index}]")
    return refs


def _bundle_route_references(
    bundle_id: str,
    bundle: ModelBundle,
    route_ids: set[str],
) -> list[str]:
    refs: list[str] = []
    for index, entry in enumerate(bundle.fallback_chain):
        if entry.route_id in route_ids:
            refs.append(f"{bundle_id}.fallback_chain[{index}]")
    for group_index, group in enumerate(bundle.model_groups):
        for provider_index, provider_model in enumerate(group.provider_models):
            if provider_model.route_id in route_ids:
                refs.append(f"{bundle_id}.model_groups[{group_index}].provider_models[{provider_index}]")
    return refs


def _capability_key(value: str) -> str:
    return {
        "thinking": "thinking_protocol",
        "tool_calling": "tool_protocol",
        "structured_output": "structured_output_protocol",
    }.get(value, value)


def _endpoint_probe_backend(endpoint: ProviderEndpoint) -> ProviderProbeBackend:
    return _gateway_endpoint_probe_backend(endpoint)


def _endpoint_probe_base_url(endpoint: ProviderEndpoint) -> str:
    return _gateway_endpoint_probe_base_url(endpoint)


def _endpoint_probe_is_disabled(
    endpoint: ProviderEndpoint,
    *,
    allow_disabled: bool = False,
) -> bool:
    return endpoint.status == "disabled" and not allow_disabled


def _disabled_endpoint_probe_result(endpoint: ProviderEndpoint) -> EndpointProbeResult:
    return EndpointProbeResult(
        endpoint_id=endpoint.endpoint_id,
        provider_kind=endpoint.provider_kind,
        backend=_endpoint_probe_backend(endpoint),
        base_url=_endpoint_probe_base_url(endpoint),
        status="error",
        message=DISABLED_ENDPOINT_PROBE_MESSAGE,
        error_code=_ENDPOINT_DISABLED_ERROR_CODE,
    )


def _disabled_route_probe_result(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
) -> RouteProbeResult:
    return RouteProbeResult(
        endpoint_id=endpoint.endpoint_id,
        route_id=route.route_id,
        provider_kind=endpoint.provider_kind,
        backend=_endpoint_probe_backend(endpoint),
        base_url=_endpoint_probe_base_url(endpoint),
        model_id=route.provider_model_id,
        status="error",
        message=DISABLED_ENDPOINT_PROBE_MESSAGE,
    )


def _disabled_model_probe_result(model_id: str) -> ModelProbeResult:
    return ModelProbeResult(
        model_id=model_id,
        status="error",
        message=DISABLED_ENDPOINT_PROBE_MESSAGE,
    )


def _model_probe_is_disabled_endpoint_skip(result: ModelProbeResult) -> bool:
    return result.status == "error" and result.message == DISABLED_ENDPOINT_PROBE_MESSAGE


async def _probe_endpoint_model_list_atom(
    endpoint: ProviderEndpoint,
    *,
    allow_disabled: bool = False,
) -> EndpointProbeResult:
    if _endpoint_probe_is_disabled(endpoint, allow_disabled=allow_disabled):
        return _disabled_endpoint_probe_result(endpoint)
    return await _gateway_test_provider_endpoint(endpoint)


async def _probe_route_generation_atom(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    *,
    allow_disabled: bool = False,
    runtime_settings: dict[str, Any] | None = None,
) -> RouteProbeResult:
    if _endpoint_probe_is_disabled(endpoint, allow_disabled=allow_disabled):
        return _disabled_route_probe_result(endpoint, route)
    await _publish_llm_probe_active(endpoint.endpoint_id, (route.provider_model_id,))
    try:
        return await _gateway_test_provider_route(
            endpoint,
            route,
            runtime_settings=runtime_settings,
        )
    finally:
        await _publish_llm_probe_active(endpoint.endpoint_id, ())


async def _probe_model_generation_atom(
    endpoint: ProviderEndpoint,
    model_id: str,
    *,
    allow_disabled: bool = False,
    runtime_settings: dict[str, Any] | None = None,
) -> RouteProbeResult:
    return await _probe_route_generation_atom(
        endpoint,
        _gateway_probe_route(endpoint, model_id),
        allow_disabled=allow_disabled,
        runtime_settings=runtime_settings,
    )


async def _probe_official_model_profile_atom(
    endpoint: ProviderEndpoint,
    model_id: str,
    *,
    allow_disabled: bool = False,
) -> OfficialModelProfileProbeResult:
    if _endpoint_probe_is_disabled(endpoint, allow_disabled=allow_disabled):
        return OfficialModelProfileProbeResult(
            model_id=model_id,
            last_probe_message=DISABLED_ENDPOINT_PROBE_MESSAGE,
        )
    return await _probe_official_model_profile_result(endpoint, model_id)


async def _gateway_test_provider_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
    return await _gateway_test_provider_endpoint_request(endpoint)


async def _gateway_test_provider_model(
    endpoint: ProviderEndpoint,
    model_id: str,
    *,
    runtime_settings: dict[str, Any] | None = None,
) -> RouteProbeResult:
    route_slug = _route_slug(model_id)
    route = ProviderRoute(
        route_id=f"{endpoint.endpoint_id}:{route_slug}",
        endpoint_id=endpoint.endpoint_id,
        route_slug=route_slug,
        provider_model_id=model_id,
        canonical_id=model_id,
    )
    return await _gateway_test_provider_route(endpoint, route, runtime_settings=runtime_settings)


async def _gateway_test_provider_route(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    *,
    runtime_settings: dict[str, Any] | None = None,
) -> RouteProbeResult:
    return await _gateway_test_provider_route_request(
        endpoint,
        route,
        runtime_settings=runtime_settings,
    )


async def _gateway_probe_official_call_method(
    method_id: OfficialCallMethod,
    api_key: str,
    base_url: str,
    model_id: str,
    *,
    runtime_settings: dict[str, Any] | None = None,
    multimodal: bool = False,
) -> ModelProbeResult:
    result = await _gateway_probe_official_call_method_request(
        method_id,
        api_key,
        base_url,
        model_id,
        runtime_settings=runtime_settings,
        multimodal=multimodal,
    )
    return _model_probe_result_from_route_probe(result)


def _model_probe_result_from_route_probe(result: RouteProbeResult) -> ModelProbeResult:
    return ModelProbeResult(
        model_id=result.model_id,
        status=result.status,
        latency_ms=result.latency_ms,
        message=result.message,
    )


def _endpoint_success_message(result: EndpointProbeResult) -> str:
    message = f"Connected in {result.latency_ms}ms."
    if result.model_seen:
        message = f"{message} Model seen: {result.model_seen}."
    return message


def _endpoint_probe_failure_message(result: EndpointProbeResult) -> str:
    if result.status == "invalid_key":
        return _provider_probe_error_message("Invalid API key", result)
    if result.status == "rate_limited":
        return _provider_probe_error_message("Provider rate limited the test request", result)
    if result.status == "quota_exceeded":
        return _provider_probe_error_message(
            "Provider rejected the key because quota or billing is unavailable",
            result,
        )
    if result.status == "timeout":
        return "Endpoint test timed out."
    if result.status == "network_error":
        return _provider_probe_error_message("Network error while testing endpoint", result)
    return _provider_probe_error_message("Endpoint test failed", result)


def _model_probe_failure_message(result: ModelProbeResult) -> str:
    message = f"Endpoint model probe failed ({result.status})."
    if result.message:
        message = f"{message} {result.message}"
    return message


def _provider_error_message(prefix: str, exc: BaseException) -> str:
    error_code = getattr(exc, "error_code", "")
    if error_code:
        return f"{prefix} ({error_code})."
    return f"{prefix}."


def _provider_probe_error_message(prefix: str, result: EndpointProbeResult) -> str:
    if result.error_code:
        return f"{prefix} ({result.error_code})."
    if result.message:
        return f"{prefix}. {result.message}"
    return f"{prefix}."


def _raise_conflict(error_code: str, message: str, details: dict[str, Any]) -> NoReturn:
    raise HTTPException(
        status_code=409,
        detail={
            "error_code": error_code,
            "http_status": 409,
            "message": message,
            "details": details,
            "retry_strategy": "not_retryable",
        },
    )


__all__ = ["router"]
