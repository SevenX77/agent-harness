"""Studio LLM registry API endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, NoReturn, cast
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.adapters.gateway import (
    CredentialProviderProtocol,
    GatewayAdapter,
    GatewayProviderRoute,
    GatewayRoleEntry,
    ProfileSelectionError,
    ProviderModelStateProjection,
    RegistryResolutionError,
    ResolvedRoute,
    RuntimeSettings,
    VerifiedProfile,
    build_runtime_setting_descriptors,
    canonicalize_model,
    lint_role_routes,
    normalize_route_capabilities,
    select_verified_profile,
)
from app.models.llm_config import (
    CapabilityValue,
    EvidenceRecord,
    FieldSource,
    LLMCredentialsFile,
    ModelBundle,
    ModelProfile,
    ProviderEndpoint,
    ProviderImportDraft,
    ProviderRoute,
    RegistryResponse,
    RoleEntry,
    RoleRouteEntry,
    RolesData,
    RouteCandidate,
)
from app.services import copilot
from app.services.copilot_test import (
    CopilotProvider,
    ModelProbeResult,
    OfficialCallMethod,
    PingResult,
    _NetworkError,
    _ping_provider,
    _probe_model,
    _QuotaExceeded,
    _RateLimited,
    _Unauthorized,
)
from app.services.copilot_test import (
    _probe_official_call_method as _probe_official_call_method_request,
)
from app.services.gateway_resolver import build_gateway_model_resolver
from app.services.llm_credentials import (
    _route_slug,
    credentials_path,
    delete_endpoint,
    delete_route,
    load_credentials,
    save_credentials,
    serialize_for_response,
    upsert_endpoints,
    upsert_routes,
)
from app.services.llm_health_store import RuntimeCircuit, SqliteLlmHealthStore
from app.services.llm_import_drafts import (
    DraftApplyConflict,
    DraftExpired,
    DraftNotFound,
    append_evidence_record,
    apply_draft,
    create_draft,
    load_draft,
    load_evidence_library,
    new_evidence_id,
    sync_remote_evidence_library,
)
from app.services.llm_model_groups import (
    normalize_model_group_key,
    project_model_group_identity,
)
from app.services.llm_model_identity import project_model_identity
from app.services.llm_notable_models import notable_model_ids
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
from app.services.official_capability_sources import (
    OfficialCapabilityRule,
    official_api_list_source_urls,
    official_doc_source_urls,
    provider_doc_limit_rules,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])
logger = logging.getLogger(__name__)
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


class EndpointTestJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    endpoint_id: str
    status: Literal["queued", "running", "completed", "failed"]
    total_model_count: int = 0
    tested_model_count: int = 0
    verified_route_count: int = 0
    failed_model_count: int = 0
    catalog_only_count: int = 0
    message: str | None = None
    available_models: list[EndpointTestCompactModelInfo] = Field(default_factory=list)
    available_sdks: list[str] = Field(default_factory=list)


class ProviderNotableModelsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notable_models: list[str]


class RoleTestProviderProgressInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    route_id: str
    status: Literal["queued", "testing", "ok", "failed", "blocked", "untested"]
    message: str | None = None


class RoleTestJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    role_name: str
    status: Literal["queued", "running", "completed", "failed"]
    message: str | None = None
    provider_statuses: list[RoleTestProviderProgressInfo] = Field(default_factory=list)
    result: dict[str, Any] | None = None


_endpoint_test_jobs: dict[str, EndpointTestJobResponse] = {}
_running_endpoint_test_jobs: dict[str, str] = {}
_endpoint_test_jobs_lock = asyncio.Lock()
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


@router.get("/registry", response_model=RegistryResponse)
async def get_llm_registry() -> RegistryResponse:
    """Return the joined redacted endpoint/route/role registry."""
    setup_required = not credentials_path().exists()
    credentials = load_credentials()
    roles = _load_roles_or_empty()
    return _registry_response(credentials, roles, setup_required=setup_required)


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


@router.put("/registry/endpoints")
async def put_registry_endpoints(request: EndpointUpsertRequest) -> dict[str, Any]:
    """Upsert endpoints; absent endpoint IDs are retained."""
    data = upsert_endpoints({endpoint_id: endpoint for endpoint_id, endpoint in request.provider_endpoints.items()})
    return serialize_for_response(data)


@router.delete("/registry/endpoints/{endpoint_id}")
async def delete_registry_endpoint(endpoint_id: str) -> dict[str, Any]:
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
    data = delete_endpoint(endpoint_id)
    return serialize_for_response(data)


@router.post(
    "/endpoints/{endpoint_id}/test-jobs",
    response_model=EndpointTestJobResponse,
)
async def start_endpoint_test_job(endpoint_id: str) -> EndpointTestJobResponse:
    """Start an official provider test job that reports compact progress."""
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint_id}")
    if endpoint.provider_kind != "official":
        raise HTTPException(
            status_code=400,
            detail=f"Endpoint test jobs are only supported for official providers: {endpoint_id}",
        )
    async with _endpoint_test_jobs_lock:
        running_job_id = _running_endpoint_test_jobs.get(endpoint_id)
        if running_job_id is not None:
            running = _endpoint_test_jobs.get(running_job_id)
            if running is not None and running.status in {"queued", "running"}:
                return running
        job = EndpointTestJobResponse(
            job_id=uuid.uuid4().hex,
            endpoint_id=endpoint_id,
            status="queued",
            message="Provider test queued.",
            available_sdks=[endpoint.protocol],
        )
        _endpoint_test_jobs[job.job_id] = job
        _running_endpoint_test_jobs[endpoint_id] = job.job_id
    _spawn_background_task(_run_official_endpoint_test_job(job.job_id, endpoint_id))
    return job


@router.post("/catalog/sync")
async def sync_catalog() -> dict[str, Any]:
    """Pull the remote evidence library and merge it locally."""
    try:
        updated = await sync_remote_evidence_library()
        return {
            "status": "success",
            "message": "Catalog synced successfully with remote repository.",
            "route_candidates_count": len(updated.route_candidates),
            "evidence_records_count": len(updated.evidence_records),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync catalog: {exc}",
        ) from exc


@router.post("/catalog/share")
async def share_catalog() -> dict[str, Any]:
    """Export and return all local successful evidence records ready to be shared with the community."""
    try:
        library = load_evidence_library()
        probed_records = [
            rec.model_dump(mode="json")
            for rec in library.evidence_records
            if rec.evidence_type == "probe" and rec.trust_state == "probe-verified"
        ]

        credentials = load_credentials()
        verified_routes_count = sum(1 for r in credentials.provider_routes.values() if r.status == "verified")

        return {
            "status": "success",
            "message": "Local verified catalog evidence exported successfully.",
            "verified_routes_in_credentials": verified_routes_count,
            "evidence_records_to_share": probed_records,
            "export_instructions": (
                "To share these verified profiles with the community, submit a Pull Request "
                "to SevenX77/agent-harness with these evidence records added to llm_import_drafts.json."
            ),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to share catalog evidence: {exc}",
        ) from exc


@router.get(
    "/endpoint-test-jobs/{job_id}",
    response_model=EndpointTestJobResponse,
)
async def get_endpoint_test_job(job_id: str) -> EndpointTestJobResponse:
    """Return compact progress for one provider test job."""
    job = _endpoint_test_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint test job: {job_id}")
    return job


@router.post("/endpoints/{endpoint_id}/test", response_model=EndpointTestResponse)
async def test_endpoint(endpoint_id: str) -> EndpointTestResponse:
    """Verify an endpoint by making the provider's minimal models-list call."""
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint_id}")
    starting_fingerprint = credentials.endpoint_fingerprint(endpoint_id)
    status: Literal["verified", "unverified_manual", "failed"] = "failed"
    message = "API key is empty."
    model_list_reached = False
    discovered_model_ids: tuple[str, ...] = ()
    raw_capabilities_by_model: dict[str, dict[str, Any]] = {}
    if endpoint.api_key and endpoint.api_key.get_secret_value():
        probe_backend = _endpoint_probe_backend(endpoint)
        probe_base_url = _endpoint_probe_base_url(endpoint)
        logger.warning(
            "testing LLM endpoint protocol=%s backend=%s",
            endpoint.protocol,
            probe_backend,
        )
        try:
            result = await _ping_provider(
                probe_backend,
                endpoint.api_key.get_secret_value(),
                probe_base_url,
            )
        except _Unauthorized as exc:
            message = _provider_error_message("Invalid API key", exc)
        except _RateLimited as exc:
            message = _provider_error_message("Provider rate limited the test request", exc)
        except _QuotaExceeded as exc:
            message = _provider_error_message(
                "Provider rejected the key because quota or billing is unavailable",
                exc,
            )
        except httpx.TimeoutException:
            message = "Endpoint test timed out."
        except _NetworkError as exc:
            message = _provider_error_message("Network error while testing endpoint", exc)
        else:
            status = "unverified_manual"
            model_list_reached = True
            if not result.model_ids:
                message = "Endpoint reachable but returned no models."
            else:
                message = _endpoint_success_message(result)
                discovered_model_ids = result.model_ids
                raw_capabilities_by_model = result.model_capabilities
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
        return EndpointTestResponse(
            registry=_registry_response(latest_credentials, _load_roles_or_empty()),
            tested_endpoint_id=endpoint_id,
            discovered_model_count=0,
        )
    if model_list_reached:
        route_ids_by_model: dict[str, str] = {}
        if latest_endpoint.provider_kind == "official":
            latest_credentials, route_ids_by_model = _upsert_discovered_routes(
                latest_credentials,
                endpoint=latest_endpoint,
                model_ids=discovered_model_ids,
                verified=False,
                raw_capabilities_by_model=raw_capabilities_by_model,
            )
            if discovered_model_ids:
                status = "verified"
        else:
            latest_credentials, route_ids_by_model = _upsert_discovered_routes(
                latest_credentials,
                endpoint=latest_endpoint,
                model_ids=discovered_model_ids,
                verified=False,
                raw_capabilities_by_model=raw_capabilities_by_model,
            )
        _append_model_list_observation_evidence(
            latest_endpoint,
            discovered_model_ids,
            raw_capabilities_by_model,
            route_ids_by_model,
        )
    updated = latest_endpoint.model_copy(
        update={
            "status": status,
            "last_test_at": _now_iso(),
            "last_test_message": message,
        }
    )
    latest_credentials.provider_endpoints[endpoint_id] = updated
    save_credentials(latest_credentials)
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
    """Probe requested model IDs against one stored endpoint and upsert successful routes."""
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint_id}")
    starting_fingerprint = credentials.endpoint_fingerprint(endpoint_id)

    requested_model_ids = _requested_model_ids(request.model_ids)
    results: list[EndpointModelTestResult] = []
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
            official_results.append(await _probe_official_model_profile_result(endpoint, model_id))
        successful_model_ids = [result.model_id for result in official_results if result.profiles]
        route_ids_by_model: dict[str, str] = {}
        latest_credentials = credentials
        if successful_model_ids:
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
            save_credentials(latest_credentials)
        results = [
            EndpointModelTestResult(
                model_id=result.model_id,
                status="ok" if result.profiles else "error",
                route_id=route_ids_by_model.get(result.model_id) if result.profiles else None,
                message=None if result.profiles else result.last_probe_message,
            )
            for result in official_results
        ]
        for result in official_results:
            _append_official_profile_probe_evidence(
                endpoint,
                result,
                route_id=route_ids_by_model.get(result.model_id),
            )
        return EndpointModelTestResponse(
            registry=_registry_response(latest_credentials, _load_roles_or_empty()),
            results=results,
        )

    probe_results: list[ModelProbeResult] = []
    for model_id in requested_model_ids:
        probe_results.append(
            await _probe_model(
                _endpoint_probe_backend(endpoint),
                endpoint.api_key.get_secret_value(),
                _endpoint_probe_base_url(endpoint),
                model_id,
            )
        )
    successful_model_ids = [result.model_id for result in probe_results if result.status == "ok"]
    if successful_model_ids:
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
        latest_credentials, route_ids_by_model = _upsert_discovered_routes(
            latest_credentials,
            endpoint=latest_endpoint,
            model_ids=tuple(successful_model_ids),
            verified=True,
            raw_capabilities_by_model={
                model_id: _successful_generation_probe_capabilities() for model_id in successful_model_ids
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
        save_credentials(latest_credentials)
    else:
        latest_credentials = credentials
        latest_endpoint = credentials.provider_endpoints.get(endpoint_id)
        if latest_endpoint is not None and probe_results:
            latest_credentials = latest_credentials.model_copy(
                update={
                    "provider_endpoints": {
                        **latest_credentials.provider_endpoints,
                        endpoint_id: latest_endpoint.model_copy(
                            update={
                                "status": "failed",
                                "last_test_at": _now_iso(),
                                "last_test_message": _model_probe_failure_message(probe_results[0]),
                            }
                        ),
                    }
                }
            )
            save_credentials(latest_credentials)
        route_ids_by_model = {}
    results = [
        EndpointModelTestResult(
            model_id=probe_result.model_id,
            status=probe_result.status,
            route_id=route_ids_by_model.get(probe_result.model_id) if probe_result.status == "ok" else None,
            message=probe_result.message,
        )
        for probe_result in probe_results
    ]
    for probe_result in probe_results:
        _append_model_probe_evidence(
            endpoint,
            probe_result,
            route_id=route_ids_by_model.get(probe_result.model_id),
        )
    return EndpointModelTestResponse(
        registry=_registry_response(latest_credentials, _load_roles_or_empty()),
        results=results,
    )


@router.post("/routes/{route_id}/probe")
async def probe_route(
    route_id: str,
    request: RouteProbeRequest,
    force: bool = False,
) -> ProviderRoute:
    """Probe one route and update normalized capability metadata."""
    credentials = load_credentials()
    route = credentials.provider_routes.get(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"Unknown route: {route_id}")
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {route.endpoint_id}")
    if force:
        return await _force_probe_route(credentials, route, endpoint)
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
    return updated


@router.put("/routes/{route_id}", response_model=ProviderRoute)
async def put_route_metadata(route_id: str, request: RouteEditableUpdate) -> ProviderRoute:
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
    return updated


@router.delete("/routes/{route_id}")
async def delete_registry_route(route_id: str) -> dict[str, Any]:
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
    return serialize_for_response(data)


@router.post("/import-drafts", response_model=ProviderImportDraft)
async def post_import_draft(request: ProviderImportDraft) -> ProviderImportDraft:
    """Create an import draft from already extracted candidates."""
    return create_draft(request)


@router.get("/import-drafts/{draft_id}", response_model=ProviderImportDraft)
async def get_import_draft(draft_id: str) -> ProviderImportDraft:
    """Return one import draft."""
    try:
        return load_draft(draft_id)
    except DraftNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Unknown draft: {draft_id}") from exc


@router.post("/import-drafts/{draft_id}/probe", response_model=ProviderImportDraft)
async def probe_import_draft(draft_id: str) -> ProviderImportDraft:
    """Mark a draft as probed; real agent probing is handled by a later worker."""
    draft = await get_import_draft(draft_id)
    updated = draft.model_copy(update={"status": "probed", "updated_at": _now_iso()})
    return create_draft(updated)


@router.post("/import-drafts/{draft_id}/apply", response_model=ProviderImportDraft)
async def apply_import_draft(
    draft_id: str,
    mode: Literal["merge"] | None = None,
) -> ProviderImportDraft:
    """Apply selected draft records into active credentials."""
    try:
        return apply_draft(draft_id, conflict_mode=mode)
    except DraftNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Unknown draft: {draft_id}") from exc
    except DraftExpired:
        _raise_conflict(
            "draft_expired",
            f"Import draft has expired: {draft_id}",
            {"draft_id": draft_id},
        )
    except DraftApplyConflict as exc:
        _raise_conflict("draft_conflict", str(exc), {"draft_id": draft_id})


@router.get("/roles", response_model=RolesData)
async def get_llm_roles() -> RolesData:
    """Return all route-backed roles."""
    return _materialize_roles_for_response(_load_roles_or_empty())


@router.put("/roles", response_model=RolesData)
async def put_llm_roles(request: RolesData) -> RolesData:
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
    return _materialize_roles_for_response(saved, credentials)


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
    adapter = GatewayAdapter(transport="in_process")
    role = adapter.materialize_role({"role": request, "credentials": credentials}) if request.model_groups else request
    roles = dict(data.roles)
    roles[role_name] = role
    schema_version = 3 if role.model_groups else data.schema_version
    saved = _save_roles_with_active_routes(data.model_copy(update={"schema_version": schema_version, "roles": roles}))
    return _materialize_role_for_response(saved.roles[role_name], credentials)


@router.delete("/roles/{role_name}", response_model=RolesData)
async def delete_llm_role(role_name: str) -> RolesData:
    """Delete one persisted role."""
    data = _load_roles_or_empty()
    if role_name not in data.roles:
        raise HTTPException(status_code=404, detail=f"Unknown LLM role: {role_name}")
    roles = dict(data.roles)
    del roles[role_name]
    credentials = load_credentials()
    saved = _save_roles_with_active_routes(data.model_copy(update={"roles": roles}))
    return _materialize_roles_for_response(saved, credentials)


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
    targets: list[RoleTestTarget] = []
    for report_entry, fallback_entry in _role_test_entries(role):
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


async def _start_copilot_sdk_test_job(role_name: str) -> RoleTestJobResponse:
    job_id = str(uuid.uuid4())
    try:
        routes, credential_provider = _resolve_copilot_test_routes(role_name)
    except Exception as exc:  # noqa: BLE001 — surfaced as a failed job, not swallowed
        logger.warning("copilot SDK test: cannot resolve routes for %s: %s", role_name, exc)
        job = RoleTestJobResponse(
            job_id=job_id,
            role_name=role_name,
            status="failed",
            message=f"无法解析 copilot 路线: {exc}",
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
    resolver = build_gateway_model_resolver()
    resolved = resolver.resolve_routes(role_name)
    return list(resolved.routes), resolver.credential_provider


def _copilot_route_progress(
    route: ResolvedRoute,
    status: Literal["queued", "testing", "ok", "failed", "blocked", "untested"],
    message: str | None = None,
) -> RoleTestProviderProgressInfo:
    return RoleTestProviderProgressInfo(
        canonical_id=route.canonical_id,
        route_id=route.route_id,
        status=status,
        message=message,
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
            result = await copilot.run_route_sdk_test(route, credential_provider)
            await _update_copilot_route(job_id, route, result.status, result.message)
            return result

    try:
        results = await asyncio.gather(*(test_route(route) for route in routes))
    except Exception as exc:  # pragma: no cover - defensive job boundary
        logger.exception("Copilot SDK test job failed: %s", job_id)
        await _update_role_test_job(job_id, status="failed", message=str(exc))
        return

    await _update_role_test_job(
        job_id,
        status="completed",
        message="Copilot SDK test completed.",
        result=_build_copilot_sdk_result(role_name, routes, list(results)),
    )


async def _update_copilot_route(
    job_id: str,
    route: ResolvedRoute,
    status: Literal["testing", "ok", "failed", "blocked", "untested"],
    message: str | None,
) -> None:
    async with _role_test_jobs_lock:
        current = _role_test_jobs.get(job_id)
        if current is None:
            return
        provider_statuses = [
            _copilot_route_progress(route, status, message)
            if provider.route_id == route.route_id
            else provider
            for provider in current.provider_statuses
        ]
        _role_test_jobs[job_id] = current.model_copy(
            update={"provider_statuses": provider_statuses}
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
    routes_evidence = {
        result.route_id: {"status": result.status, "message": result.message}
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
                "message": result.message if result else None,
            }
        )
    return [
        {"canonical_id": canonical_id, "provider_results": provider_results}
        for canonical_id, provider_results in groups.items()
    ]


@router.get("/model-profiles")
async def get_model_profiles() -> dict[str, ModelProfile]:
    """Return model profiles."""
    return _load_roles_or_empty().model_profiles


@router.put("/model-profiles")
async def put_model_profiles(profiles: dict[str, ModelProfile]) -> dict[str, ModelProfile]:
    """Replace model profile set."""
    data = _load_roles_or_empty().model_copy(update={"model_profiles": profiles})
    return _save_roles_with_active_routes(data).model_profiles


@router.delete("/model-bundles/{bundle_id}", response_model=RolesData)
async def delete_model_bundle(bundle_id: str) -> RolesData:
    """Delete one persisted model bundle."""
    data = _load_roles_or_empty()
    bundles = dict(data.model_bundles)
    removed = bundles.pop(bundle_id, None)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"Unknown model bundle: {bundle_id}")
    del removed
    credentials = load_credentials()
    saved = _save_roles_with_active_routes(data.model_copy(update={"model_bundles": bundles}))
    return _materialize_roles_for_response(saved, credentials)


@router.delete("/model-profiles/{model_profile_id}")
async def delete_model_profile(model_profile_id: str) -> RolesData:
    """Delete profile and mark roles that still show its source snapshot."""
    data = _load_roles_or_empty()
    profiles = dict(data.model_profiles)
    removed = profiles.pop(model_profile_id, None)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"Unknown model profile: {model_profile_id}")
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
    return _save_roles_with_active_routes(data.model_copy(update={"model_profiles": profiles, "roles": roles}))


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
    return _save_roles_with_active_routes(data.model_copy(update={"roles": roles})).roles[role_name]


def _registry_response(
    credentials: LLMCredentialsFile,
    roles: RolesData,
    *,
    setup_required: bool = False,
) -> RegistryResponse:
    credentials = _normalize_credentials_for_registry_response(credentials)
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
        model_groups=_model_groups_response(credentials),
        lint_results=lint_results,
        route_runtime_settings={
            route_id: build_runtime_setting_descriptors(route)
            for route_id, route in credentials.provider_routes.items()
        },
        role_effective_runtime_settings=_role_effective_runtime_settings(credentials, roles),
        setup_required=setup_required,
    )


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


def _model_groups_response(credentials: LLMCredentialsFile) -> list[dict[str, Any]]:
    routes_by_identity: dict[str, list[ProviderRoute]] = {}
    for route in credentials.provider_routes.values():
        if not _include_route_in_model_groups(route, credentials):
            continue
        routes_by_identity.setdefault(
            _model_group_identity_key(route, credentials),
            [],
        ).append(route)
    model_groups = [
        _model_group_response(
            _representative_canonical_id(routes, credentials),
            routes,
            credentials,
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
) -> dict[str, Any]:
    provider_models = [
        option
        for route in sorted(routes, key=lambda item: item.route_id)
        if (option := _provider_model_option(route, credentials)) is not None
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
) -> dict[str, Any] | None:
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    if endpoint is None:
        return None
    circuits = _health_store().get_active_circuits(
        route_id=route.route_id,
        endpoint_id=endpoint.endpoint_id,
        rate_limit_bucket=endpoint.rate_limit_bucket or endpoint.endpoint_id,
        now=datetime.now(UTC),
    )
    adapter = GatewayAdapter(transport="in_process")
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
    }


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
    result = await _probe_model(
        _endpoint_probe_backend(endpoint),
        endpoint.api_key.get_secret_value(),
        _endpoint_probe_base_url(endpoint),
        route.provider_model_id,
    )
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
) -> tuple[ProviderRoute, OfficialModelProfileProbeResult | None]:
    if endpoint.provider_kind != "official" or _route_has_ready_verified_profile(route):
        return route, None

    profile_result = await _probe_official_model_profile_result(
        endpoint,
        route.provider_model_id,
    )
    if profile_result.profiles:
        updated_route = _persist_official_role_test_verified_profile(
            route,
            endpoint,
            profile_result,
        )
        _append_official_profile_probe_evidence(
            endpoint,
            profile_result,
            route_id=updated_route.route_id,
        )
        return (
            updated_route,
            profile_result,
        )
    updated_route = _persist_official_role_test_profile_failure(route, profile_result)
    _append_official_profile_probe_evidence(
        endpoint,
        profile_result,
        route_id=updated_route.route_id,
    )
    return (
        updated_route,
        profile_result,
    )


def _route_has_ready_verified_profile(route: ProviderRoute) -> bool:
    return any(profile.status == "ready" for profile in route.verified_profiles)


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
    save_credentials(credentials)
    return updated_route


def _persist_official_role_test_profile_failure(
    route: ProviderRoute,
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
    save_credentials(credentials)
    return updated_route


def _official_role_test_profile_probe_failure_message(
    profile_result: OfficialModelProfileProbeResult,
) -> str:
    return profile_result.last_probe_message or NO_WORKING_OFFICIAL_LANGUAGE_METHOD_MESSAGE


def _append_official_profile_probe_evidence(
    endpoint: ProviderEndpoint,
    profile_result: OfficialModelProfileProbeResult,
    *,
    route_id: str | None,
) -> None:
    profile = _selected_evidence_profile(profile_result.profiles)
    first_attempt = _first_probe_attempt(profile_result.probe_attempts)
    model_id = profile_result.model_id
    verified = bool(profile_result.profiles)
    reason = None if verified else _official_role_test_profile_probe_failure_message(profile_result)
    catalog_capabilities = _official_catalog_capabilities(endpoint, model_id)
    append_evidence_record(
        EvidenceRecord(
            evidence_id=new_evidence_id("probe"),
            evidence_type="probe",
            trust_state="probe-verified" if verified else "probe-failed",
            observed_at=_now_iso(),
            attempted_at=_now_iso(),
            endpoint_id=endpoint.endpoint_id,
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


def _append_model_probe_evidence(
    endpoint: ProviderEndpoint,
    result: ModelProbeResult,
    *,
    route_id: str | None,
) -> None:
    verified = result.status == "ok"
    reason = None if verified else _model_probe_failure_message(result)
    capability_values = (
        _third_party_route_capability_values(
            endpoint,
            result.model_id,
            _successful_generation_probe_capabilities(),
            source="probed_verified",
        )
        if verified
        else {}
    )
    append_evidence_record(
        EvidenceRecord(
            evidence_id=new_evidence_id("probe"),
            evidence_type="probe",
            trust_state="probe-verified" if verified else "probe-failed",
            observed_at=_now_iso(),
            attempted_at=_now_iso(),
            endpoint_id=endpoint.endpoint_id,
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


def _append_model_list_observation_evidence(
    endpoint: ProviderEndpoint,
    model_ids: tuple[str, ...],
    raw_capabilities_by_model: dict[str, dict[str, Any]],
    route_ids_by_model: dict[str, str],
) -> None:
    library = load_evidence_library()
    previous_model_ids = {
        candidate.provider_model_id
        for candidate in library.route_candidates.values()
        if candidate.endpoint_id == endpoint.endpoint_id
    }
    observed_model_ids = list(model_ids)
    observed_set = set(observed_model_ids)
    added_model_ids = [model_id for model_id in observed_model_ids if model_id not in previous_model_ids]
    removed_model_ids = sorted(previous_model_ids - observed_set)
    unchanged_model_ids = [model_id for model_id in observed_model_ids if model_id in previous_model_ids]
    route_candidates = {
        route_id: _route_candidate_from_model_list(
            endpoint,
            model_id,
            route_id,
            raw_capabilities_by_model.get(model_id, {}),
        )
        for model_id, route_id in route_ids_by_model.items()
    }
    append_evidence_record(
        EvidenceRecord(
            evidence_id=new_evidence_id("model-list"),
            evidence_type="model_list_observation",
            trust_state="provider-list-observed",
            observed_at=_now_iso(),
            endpoint_id=endpoint.endpoint_id,
            provider_id=endpoint.endpoint_id,
            scope={"endpoint_id": endpoint.endpoint_id},
            model_list_observation={
                "base_url_fingerprint": _redacted_base_url_fingerprint(endpoint.base_url),
                "observed_model_ids": observed_model_ids,
                "added_model_ids": added_model_ids,
                "removed_model_ids": removed_model_ids,
                "unchanged_model_ids": unchanged_model_ids,
            },
            metadata={"model_count": len(observed_model_ids)},
        ),
        route_candidates=route_candidates,
    )


def _route_candidate_from_model_list(
    endpoint: ProviderEndpoint,
    model_id: str,
    route_id: str,
    raw_capabilities: dict[str, Any],
) -> RouteCandidate:
    route_slug = route_id.split(":", 1)[1] if ":" in route_id else _route_slug(model_id)
    canonical = canonicalize_model(endpoint_id=endpoint.endpoint_id, provider_model_id=route_slug)
    capabilities = (
        {
            **_official_model_type_capability_values(
                endpoint,
                model_id,
                source="api_list",
            ),
            **_provider_doc_limit_capability_values(endpoint, model_id),
            **_official_normalized_route_capabilities(endpoint, model_id, raw_capabilities),
        }
        if endpoint.provider_kind == "official"
        else _third_party_route_capability_values(
            endpoint,
            model_id,
            raw_capabilities,
            source="api_list",
        )
    )
    return RouteCandidate(
        endpoint_id=endpoint.endpoint_id,
        route_slug=route_slug,
        provider_model_id=model_id,
        canonical_id=canonical.canonical_id,
        display_name=model_id,
        capabilities=capabilities,
        field_sources={
            "provider_model_id": FieldSource(source="api_list"),
            "capabilities": FieldSource(source="api_list"),
        },
        metadata={
            "trust_state": "provider-list-observed",
            "route_id": route_id,
            "provider_kind": endpoint.provider_kind,
        },
    )


def _redacted_base_url_fingerprint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


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
    try:
        selected_profile = select_verified_profile(route, runtime_settings)
    except ProfileSelectionError as exc:
        return ModelProbeResult(
            model_id=route.provider_model_id,
            status="error",
            message=str(exc),
        )

    if selected_profile is not None:
        if endpoint.api_key is None or not endpoint.api_key.get_secret_value():
            return ModelProbeResult(
                model_id=route.provider_model_id,
                status="invalid_key",
                message="API key is empty.",
            )
        return await _probe_official_call_method_request(
            cast(OfficialCallMethod, selected_profile.method_id),
            endpoint.api_key.get_secret_value(),
            _endpoint_probe_base_url(endpoint),
            route.provider_model_id,
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

    return await _probe_model(
        _endpoint_probe_backend(endpoint),
        endpoint.api_key.get_secret_value() if endpoint.api_key is not None else "",
        _endpoint_probe_base_url(endpoint),
        route.provider_model_id,
        runtime_settings=resolved_settings or None,
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
    return (await _probe_official_model_profile_result(endpoint, model_id)).profiles


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
) -> ModelProbeResult:
    if not endpoint.api_key or not endpoint.api_key.get_secret_value():
        return ModelProbeResult(
            model_id=model_id,
            status="invalid_key",
            message="API key is empty.",
        )
    return await _probe_official_call_method_request(
        candidate.method_id,
        endpoint.api_key.get_secret_value(),
        _endpoint_probe_base_url(endpoint),
        model_id,
        runtime_settings=candidate.runtime_settings,
    )


def _official_language_probe_candidates(
    endpoint: ProviderEndpoint,
    model_id: str,
) -> list[OfficialLanguageProbeCandidate]:
    if not _is_official_language_model_candidate(endpoint, model_id):
        return []
    backend = _endpoint_probe_backend(endpoint)
    if backend == "openai":
        model = model_id.lower()
        if model.startswith("gpt-3.5-turbo-instruct"):
            return [
                _candidate(
                    "openai_completions",
                    "text:openai_completions",
                    "text_chat",
                    "openai_completions_text",
                    10,
                    1,
                ),
            ]
        reasoning_runtime_settings = _openai_reasoning_probe_runtime_settings(model_id)
        reasoning_candidates = _openai_reasoning_probe_candidates(
            method_id="openai_responses",
            model_id=model_id,
            default_rank=5,
            fallback_rank=1,
        )
        if _openai_prefers_responses_only(model_id):
            return [
                _candidate(
                    "openai_responses",
                    "text:openai_responses",
                    "text_chat",
                    "openai_responses_text",
                    10,
                    1,
                    runtime_settings=reasoning_runtime_settings
                    if _openai_requires_high_reasoning_model(model_id)
                    else None,
                ),
                *reasoning_candidates,
            ]
        return [
            _candidate(
                "openai_responses",
                "text:openai_responses",
                "text_chat",
                "openai_responses_text",
                10,
                1,
            ),
            _candidate(
                "openai_chat_completions",
                "text:openai_chat_completions",
                "text_chat",
                "openai_chat_completions_text",
                20,
                2,
            ),
            *reasoning_candidates,
            *_openai_reasoning_probe_candidates(
                method_id="openai_chat_completions",
                model_id=model_id,
                default_rank=25,
                fallback_rank=2,
            ),
        ]
    if backend == "claude":
        return [
            _candidate(
                "anthropic_messages",
                "text:anthropic_messages",
                "text_chat",
                "anthropic_text",
                10,
                1,
            ),
            _candidate(
                "anthropic_messages",
                "thinking:anthropic_messages:adaptive",
                "thinking",
                "anthropic_thinking_adaptive",
                5,
                1,
                runtime_settings={
                    "max_output_tokens": 1025,
                    "reasoning": {"enabled": True, "type": "adaptive", "effort": "low"},
                },
            ),
            _candidate(
                "anthropic_messages",
                "thinking:anthropic_messages:manual",
                "thinking",
                "anthropic_thinking_manual_budget",
                6,
                2,
                runtime_settings={
                    "max_output_tokens": 1025,
                    "reasoning": {"enabled": True, "budget_tokens": 1024},
                },
            ),
        ]
    if backend == "gemini":
        if _gemini_prefers_thinking_level(model_id):
            return [
                _candidate(
                    "gemini_generate_content",
                    "text:gemini_generate_content:minimal_thinking",
                    "text_chat",
                    "gemini_generate_content_text",
                    10,
                    1,
                    runtime_settings={
                        "max_output_tokens": 16,
                        "reasoning": {"enabled": True, "effort": "minimal"},
                    },
                ),
                _candidate(
                    "gemini_generate_content",
                    "thinking:gemini_generate_content:level_low",
                    "thinking",
                    "gemini_generate_content_thinking_level_low",
                    5,
                    1,
                    runtime_settings={
                        "max_output_tokens": 16,
                        "reasoning": {"enabled": True, "effort": "low"},
                    },
                ),
            ]
        return [
            _candidate(
                "gemini_generate_content",
                "text:gemini_generate_content:no_thinking",
                "text_chat",
                "gemini_generate_content_text",
                10,
                1,
                runtime_settings={
                    "max_output_tokens": 16,
                    "reasoning": {"enabled": False, "budget_tokens": 0},
                },
            ),
            _candidate(
                "gemini_generate_content",
                "thinking:gemini_generate_content:budget_128",
                "thinking",
                "gemini_generate_content_thinking_budget_128",
                5,
                1,
                runtime_settings={
                    "max_output_tokens": 256,
                    "reasoning": {"enabled": True, "budget_tokens": 128},
                },
            ),
            _candidate(
                "gemini_generate_content",
                "thinking:gemini_generate_content:budget_512",
                "thinking",
                "gemini_generate_content_thinking_budget_512",
                6,
                2,
                runtime_settings={
                    "max_output_tokens": 768,
                    "reasoning": {"enabled": True, "budget_tokens": 512},
                },
            ),
        ]
    if backend == "deepseek":
        return [
            _candidate(
                "deepseek_chat_completions",
                "text:deepseek_chat_completions",
                "text_chat",
                "deepseek_chat_completions_text",
                10,
                1,
            ),
            _candidate(
                "deepseek_chat_completions",
                "reasoning:deepseek_chat_completions",
                "reasoning",
                "deepseek_chat_completions_reasoning_effort",
                5,
                1,
                runtime_settings={
                    "max_output_tokens": 16,
                    "reasoning": {"enabled": True, "effort": "low"},
                },
            ),
            _candidate(
                "deepseek_anthropic_messages",
                "text:deepseek_anthropic_messages",
                "text_chat",
                "deepseek_anthropic_messages_text",
                15,
                2,
            ),
            _candidate(
                "deepseek_anthropic_messages",
                "thinking:deepseek_anthropic_messages",
                "thinking",
                "deepseek_anthropic_messages_thinking",
                6,
                2,
                runtime_settings={
                    "max_output_tokens": 1025,
                    "reasoning": {"enabled": True, "budget_tokens": 1024},
                },
            ),
        ]
    if backend == "ark":
        return [
            _candidate(
                "ark_chat",
                "text:ark_chat",
                "text_chat",
                "ark_chat_text",
                10,
                2,
                runtime_settings={
                    "max_output_tokens": 16,
                    "reasoning": {"enabled": False},
                },
            ),
            _candidate(
                "ark_responses",
                "text:ark_responses",
                "text_chat",
                "ark_responses_text",
                8,
                1,
                runtime_settings={
                    "max_output_tokens": 16,
                    "reasoning": {"enabled": False},
                },
            ),
            _candidate(
                "ark_chat",
                "thinking:ark_chat",
                "thinking",
                "ark_chat_thinking_enabled",
                6,
                2,
                runtime_settings={
                    "max_output_tokens": 16,
                    "reasoning": {"enabled": True},
                },
            ),
            _candidate(
                "ark_responses",
                "thinking:ark_responses",
                "thinking",
                "ark_responses_thinking_enabled",
                5,
                1,
                runtime_settings={
                    "max_output_tokens": 16,
                    "reasoning": {"enabled": True},
                },
            ),
            _candidate(
                "ark_anthropic_messages",
                "text:ark_anthropic_messages",
                "text_chat",
                "ark_anthropic_messages_text",
                12,
                3,
            ),
            _candidate(
                "ark_anthropic_messages",
                "thinking:ark_anthropic_messages",
                "thinking",
                "ark_anthropic_messages_thinking",
                7,
                3,
                runtime_settings={
                    "max_output_tokens": 1025,
                    "reasoning": {"enabled": True, "budget_tokens": 1024},
                },
            ),
        ]
    return []


def _openai_reasoning_probe_runtime_settings(model_id: str) -> dict[str, Any]:
    return _openai_reasoning_runtime_settings(
        model_id,
        "high" if _openai_requires_high_reasoning_model(model_id) else "low",
    )


def _openai_reasoning_probe_candidates(
    *,
    method_id: OfficialCallMethod,
    model_id: str,
    default_rank: int,
    fallback_rank: int,
) -> list[OfficialLanguageProbeCandidate]:
    efforts = ("high",) if _openai_requires_high_reasoning_model(model_id) else ("low", "medium", "high")
    request_mapper_id = (
        "openai_responses_reasoning" if method_id == "openai_responses" else "openai_chat_completions_reasoning"
    )
    retry_group = f"openai:reasoning:{model_id.lower()}"
    return [
        _candidate(
            method_id,
            f"reasoning:{method_id}:{effort}",
            "reasoning",
            request_mapper_id,
            default_rank + index,
            fallback_rank,
            runtime_settings=_openai_reasoning_runtime_settings(model_id, effort),
            retry_group=retry_group,
        )
        for index, effort in enumerate(efforts)
    ]


def _openai_reasoning_runtime_settings(model_id: str, effort: str) -> dict[str, Any]:
    model = model_id.lower()
    return {
        "max_output_tokens": 64 if _openai_is_pro_reasoning_model(model) else 16,
        "reasoning": {"enabled": True, "effort": effort},
    }


def _openai_requires_high_reasoning_model(model_id: str) -> bool:
    return model_id.lower().startswith("gpt-5-pro")


def _openai_is_pro_reasoning_model(model_id: str) -> bool:
    model = model_id.lower()
    return model.startswith("gpt-5") and "-pro" in model


def _openai_prefers_responses_only(model_id: str) -> bool:
    return _openai_is_pro_reasoning_model(model_id)


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


def _gemini_prefers_thinking_level(model_id: str) -> bool:
    model = model_id.lower()
    return (
        model.startswith("gemini-3")
        or model.startswith("deep-research")
        or model.startswith("antigravity")
        or model == "aqa"
    )


def _is_gemini_interactions_only_model(model: str) -> bool:
    return model.startswith("antigravity") or model.startswith("deep-research") or model == "aqa"


def _is_official_language_model_candidate(endpoint: ProviderEndpoint, model_id: str) -> bool:
    model = model_id.lower()
    backend = _endpoint_probe_backend(endpoint)
    if backend == "claude":
        return model.startswith("claude-")
    if backend == "gemini":
        if _is_gemini_interactions_only_model(model):
            return False
        if _is_gemini_known_non_language_model(model):
            return False
        return True
    if backend == "deepseek":
        return model.startswith("deepseek-")
    if backend == "ark":
        ark_non_language_tokens = (
            "seedream",
            "seedance",
            "wan",
            "embedding",
            "translate",
            "translation",
            "tts",
            "audio",
            "video",
            "3d",
        )
        if any(token in model for token in ark_non_language_tokens):
            return False
        return any(
            model.startswith(prefix)
            for prefix in (
                "doubao-",
                "deepseek-",
                "glm-",
                "kimi-",
                "mistral-",
                "qwen",
                "seed-",
                "ep-",
            )
        )
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
        _endpoint_probe_backend(endpoint),
        model_type=model_type,
        modalities=input_modalities,
    )
    output_source_urls = official_doc_source_urls(
        _endpoint_probe_backend(endpoint),
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
    source_urls = official_api_list_source_urls(_endpoint_probe_backend(endpoint))
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
    source_urls = list(official_api_list_source_urls(_endpoint_probe_backend(endpoint)))
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
        _endpoint_probe_backend(endpoint),
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
        _endpoint_probe_backend(endpoint),
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
    if _endpoint_probe_backend(endpoint) == "gemini" and _is_gemini_interactions_only_model(model):
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
    ) or (_endpoint_probe_backend(endpoint) == "gemini" and "image" in model):
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
    backend = _endpoint_probe_backend(endpoint)
    model = model_id.lower()
    if model_type == "language_reasoning":
        if backend == "claude":
            return ("text", "image", "pdf"), ("text",)
        if backend == "gemini" and not model.startswith("gemma-"):
            return ("text", "image", "audio", "video"), ("text",)
        if backend == "openai":
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
        if backend == "gemini" and "embedding-2" in model:
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
    backend = _endpoint_probe_backend(endpoint)
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


async def _run_official_endpoint_test_job(job_id: str, endpoint_id: str) -> None:
    try:
        await _run_official_endpoint_test_job_impl(job_id, endpoint_id)
    except Exception as exc:
        logger.exception("official endpoint test job failed")
        await _record_endpoint_test_job_failure(
            job_id,
            endpoint_id,
            f"Endpoint test failed before completion: {exc}",
        )


async def _run_official_endpoint_test_job_impl(job_id: str, endpoint_id: str) -> None:
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is None:
        await _finish_endpoint_test_job(job_id, "failed", f"Unknown endpoint: {endpoint_id}")
        return
    starting_fingerprint = credentials.endpoint_fingerprint(endpoint_id)
    if not endpoint.api_key or not endpoint.api_key.get_secret_value():
        await _record_endpoint_test_job_failure(job_id, endpoint_id, "API key is empty.")
        return

    await _update_endpoint_test_job(job_id, status="running", message="Reading provider catalog.")
    probe_backend = _endpoint_probe_backend(endpoint)
    probe_base_url = _endpoint_probe_base_url(endpoint)
    try:
        result = await _ping_provider(
            probe_backend,
            endpoint.api_key.get_secret_value(),
            probe_base_url,
        )
    except _Unauthorized as exc:
        await _record_endpoint_test_job_failure(
            job_id,
            endpoint_id,
            _provider_error_message("Invalid API key", exc),
        )
        return
    except _RateLimited as exc:
        await _record_endpoint_test_job_failure(
            job_id,
            endpoint_id,
            _provider_error_message("Provider rate limited the test request", exc),
        )
        return
    except _QuotaExceeded as exc:
        await _record_endpoint_test_job_failure(
            job_id,
            endpoint_id,
            _provider_error_message(
                "Provider rejected the key because quota or billing is unavailable",
                exc,
            ),
        )
        return
    except httpx.TimeoutException:
        await _record_endpoint_test_job_failure(job_id, endpoint_id, "Endpoint test timed out.")
        return
    except _NetworkError as exc:
        await _record_endpoint_test_job_failure(
            job_id,
            endpoint_id,
            _provider_error_message("Network error while testing endpoint", exc),
        )
        return

    discovered_model_ids = result.model_ids
    raw_capabilities_by_model = result.model_capabilities
    latest_credentials = load_credentials()
    latest_endpoint = latest_credentials.provider_endpoints.get(endpoint_id)
    if latest_endpoint is None:
        await _finish_endpoint_test_job(job_id, "failed", f"Unknown endpoint: {endpoint_id}")
        return
    if latest_credentials.endpoint_fingerprint(endpoint_id) != starting_fingerprint:
        latest_credentials.provider_endpoints[endpoint_id] = latest_endpoint.model_copy(
            update={
                "status": "unverified_manual",
                "last_test_at": _now_iso(),
                "last_test_message": ("Endpoint changed while endpoint test was running. Test result discarded."),
            }
        )
        save_credentials(latest_credentials)
        await _finish_endpoint_test_job(
            job_id,
            "failed",
            "Endpoint changed while endpoint test was running. Test result discarded.",
        )
        return

    if not discovered_model_ids:
        latest_credentials.provider_endpoints[endpoint_id] = latest_endpoint.model_copy(
            update={
                "status": "unverified_manual",
                "last_test_at": _now_iso(),
                "last_test_message": "Endpoint reachable but returned no models.",
            }
        )
        save_credentials(latest_credentials)
        _append_model_list_observation_evidence(
            latest_endpoint,
            (),
            raw_capabilities_by_model,
            {},
        )
        await _finish_endpoint_test_job(
            job_id,
            "completed",
            "Endpoint reachable but returned no models.",
            total_model_count=0,
            tested_model_count=0,
            verified_route_count=0,
            failed_model_count=0,
            catalog_only_count=0,
        )
        return

    latest_credentials, route_ids_by_model = _upsert_discovered_routes(
        latest_credentials,
        endpoint=latest_endpoint,
        model_ids=discovered_model_ids,
        verified=False,
        raw_capabilities_by_model=raw_capabilities_by_model,
    )
    latest_endpoint = latest_credentials.provider_endpoints.get(endpoint_id)
    if latest_endpoint is None:
        await _finish_endpoint_test_job(job_id, "failed", f"Unknown endpoint: {endpoint_id}")
        return
    final_models = [
        _compact_model_info_for_listed_official_route(
            latest_credentials,
            latest_endpoint,
            model_id,
            route_ids_by_model.get(model_id),
            raw_capabilities_by_model.get(model_id),
        )
        for model_id in discovered_model_ids
    ]
    latest_endpoint = latest_credentials.provider_endpoints.get(endpoint_id, latest_endpoint)
    latest_credentials.provider_endpoints[endpoint_id] = latest_endpoint.model_copy(
        update={
            "status": "verified",
            "last_test_at": _now_iso(),
            "last_test_message": _endpoint_success_message(result),
        }
    )
    save_credentials(latest_credentials)
    _append_model_list_observation_evidence(
        latest_endpoint,
        discovered_model_ids,
        raw_capabilities_by_model,
        route_ids_by_model,
    )
    await _finish_endpoint_test_job(
        job_id,
        "completed",
        _endpoint_success_message(result),
        total_model_count=len(discovered_model_ids),
        tested_model_count=0,
        verified_route_count=0,
        failed_model_count=0,
        catalog_only_count=0,
        available_models=final_models,
        available_sdks=[latest_endpoint.protocol],
    )


async def _probe_official_profile_batch(
    endpoint: ProviderEndpoint,
    model_ids: tuple[str, ...],
    *,
    on_active_change: Callable[[tuple[str, ...]], Awaitable[None]] | None = None,
) -> list[OfficialModelProfileProbeResult]:
    semaphore = asyncio.Semaphore(OFFICIAL_PROVIDER_TEST_CONCURRENCY)
    active_model_ids: set[str] = set()
    active_lock = asyncio.Lock()

    async def mark_active(model_id: str, is_active: bool) -> None:
        if on_active_change is None:
            return
        async with active_lock:
            if is_active:
                active_model_ids.add(model_id)
            else:
                active_model_ids.discard(model_id)
            active_snapshot = tuple(active_model_ids)
        await on_active_change(active_snapshot)

    async def probe(model_id: str) -> OfficialModelProfileProbeResult:
        async with semaphore:
            await mark_active(model_id, True)
            try:
                return await _probe_official_model_profile_result(endpoint, model_id)
            finally:
                await mark_active(model_id, False)

    return await asyncio.gather(*(probe(model_id) for model_id in model_ids))


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
    library = load_evidence_library()
    is_probe_verified = any(
        rec.endpoint_id == endpoint.endpoint_id and rec.model_id == model_id and rec.trust_state == "probe-verified"
        for rec in library.evidence_records
    )
    model_status: Literal["verified", "unverified_manual", "disabled", "failed", "testing", "probe-verified"]
    if route is not None:
        model_status = route.status
        if model_status == "unverified_manual" and is_probe_verified:
            model_status = "probe-verified"
    else:
        model_status = "probe-verified" if is_probe_verified else "unverified_manual"

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


async def _record_endpoint_test_job_failure(
    job_id: str,
    endpoint_id: str,
    message: str,
) -> None:
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is not None:
        credentials.provider_endpoints[endpoint_id] = endpoint.model_copy(
            update={
                "status": "failed",
                "last_test_at": _now_iso(),
                "last_test_message": message,
            }
        )
        save_credentials(credentials)
    await _finish_endpoint_test_job(job_id, "failed", message)


async def _update_endpoint_test_job(job_id: str, **updates: Any) -> None:
    async with _endpoint_test_jobs_lock:
        current = _endpoint_test_jobs.get(job_id)
        if current is None:
            return
        _endpoint_test_jobs[job_id] = current.model_copy(update=updates)


async def _finish_endpoint_test_job(
    job_id: str,
    status: Literal["completed", "failed"],
    message: str,
    **updates: Any,
) -> None:
    async with _endpoint_test_jobs_lock:
        current = _endpoint_test_jobs.get(job_id)
        if current is None:
            return
        finished = current.model_copy(update={"status": status, "message": message, **updates})
        _endpoint_test_jobs[job_id] = finished
        if _running_endpoint_test_jobs.get(finished.endpoint_id) == job_id:
            _running_endpoint_test_jobs.pop(finished.endpoint_id, None)


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


def _role_test_entries(role: RoleEntry) -> list[tuple[dict[str, Any], RoleRouteEntry | None]]:
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
    adapter = GatewayAdapter(transport="in_process")
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
            routes[route_id] = _provider_route(
                endpoint=endpoint,
                model_id=model_id,
                status=status,
                capability_source=capability_source,
                verified_profiles=(verified_profiles_by_model or {}).get(model_id, []),
                probe_attempts=(probe_attempts_by_model or {}).get(model_id, []),
                raw_capabilities=(raw_capabilities_by_model or {}).get(model_id, {}),
            )
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
        routes[route_id] = existing.model_copy(update=updates) if updates else existing
    if replace_endpoint_routes:
        discovered_model_ids = set(model_ids)
        routes = {
            route_id: route
            for route_id, route in routes.items()
            if route.endpoint_id != endpoint.endpoint_id or route.provider_model_id in discovered_model_ids
        }
    return credentials.model_copy(update={"provider_routes": routes}), route_ids_by_model


def _provider_route(
    *,
    endpoint: ProviderEndpoint,
    model_id: str,
    status: Literal["verified", "unverified_manual"],
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


def _requested_model_ids(model_ids: list[str]) -> list[str]:
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
    adapter = GatewayAdapter(transport="in_process")
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
        result[role_name] = {route.route_id: route.effective_runtime_settings for route in resolved.routes}
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
    if not has_role_authoring and not has_bundle_authoring:
        return data
    active_credentials = credentials or load_credentials()
    adapter = GatewayAdapter(transport="in_process")
    return data.model_copy(
        update={
            "schema_version": 3,
            "roles": {
                role_name: adapter.materialize_role({"role": role, "credentials": active_credentials})
                if role.model_groups
                else role
                for role_name, role in data.roles.items()
            },
            "model_bundles": {
                bundle_id: adapter.materialize_model_bundle({"bundle": bundle, "credentials": active_credentials})
                if bundle.model_groups
                else bundle
                for bundle_id, bundle in data.model_bundles.items()
            },
        }
    )


def _materialize_role_for_response(
    role: RoleEntry,
    credentials: LLMCredentialsFile | None = None,
) -> RoleEntry:
    if not role.model_groups:
        return role
    adapter = GatewayAdapter(transport="in_process")
    return cast(RoleEntry, adapter.materialize_role({"role": role, "credentials": credentials or load_credentials()}))


def _save_roles_with_active_routes(data: RolesData) -> RolesData:
    active_path = roles_path()
    active_route_ids = set(load_credentials().provider_routes)
    try:
        validate_references(data, known_route_ids=active_route_ids)
        save_roles_file(active_path, data, known_route_ids=active_route_ids)
        return load_roles_file(active_path)
    except InvalidRoleReference as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


def _endpoint_probe_backend(endpoint: ProviderEndpoint) -> CopilotProvider:
    base_host = _url_hostname(endpoint.base_url)
    endpoint_id = endpoint.endpoint_id.lower()
    if endpoint.protocol == "ark_runtime" or _host_matches(base_host, "volces.com") or "ark" in endpoint_id:
        return "ark"
    if endpoint.protocol == "anthropic_compatible":
        return "claude"
    if endpoint.protocol == "google_genai":
        return "gemini"
    if "deepseek" in base_host or "deepseek" in endpoint_id:
        return "deepseek"
    return "openai"


def _endpoint_probe_base_url(endpoint: ProviderEndpoint) -> str:
    return endpoint.base_url.rstrip("/")


def _url_hostname(raw_url: str) -> str:
    if not raw_url:
        return ""
    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    return (parsed.hostname or "").lower().rstrip(".")


def _host_matches(hostname: str, domain: str) -> bool:
    normalized_domain = domain.lower().rstrip(".")
    return hostname == normalized_domain or hostname.endswith(f".{normalized_domain}")


def _endpoint_success_message(result: PingResult) -> str:
    message = f"Connected in {result.latency_ms}ms."
    if result.model_seen:
        message = f"{message} Model seen: {result.model_seen}."
    return message


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


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


__all__ = ["router"]
