"""Studio LLM registry API endpoints."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from graph_agent_gateway.registry.canonical import canonicalize_model
from graph_agent_gateway.registry.capabilities import (
    build_runtime_setting_descriptors,
    normalize_route_capabilities,
)
from graph_agent_gateway.registry.lint import lint_role_routes
from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role
from pydantic import BaseModel, ConfigDict, Field

from app.models.llm_config import (
    CapabilityValue,
    LLMCredentialsFile,
    ModelProfile,
    ProviderEndpoint,
    ProviderImportDraft,
    ProviderRoute,
    RegistryResponse,
    RoleEntry,
    RolesData,
)
from app.services.copilot_test import (
    CopilotProvider,
    ModelProbeResult,
    PingResult,
    _NetworkError,
    _ping_provider,
    _probe_model,
    _QuotaExceeded,
    _RateLimited,
    _Unauthorized,
)
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
    apply_draft,
    create_draft,
    load_draft,
)
from app.services.llm_model_identity import project_model_identity
from app.services.llm_role_materializer import materialize_role
from app.services.llm_roles import (
    InvalidRoleReference,
    get_role,
    load_roles_file,
    roles_path,
    save_roles_file,
    validate_references,
)
from app.services.llm_state_projection import project_provider_model_state

router = APIRouter(prefix="/api/llm", tags=["llm"])
logger = logging.getLogger(__name__)


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
    data = upsert_endpoints(
        {
            endpoint_id: endpoint
            for endpoint_id, endpoint in request.provider_endpoints.items()
        }
    )
    return serialize_for_response(data)


@router.delete("/registry/endpoints/{endpoint_id}")
async def delete_registry_endpoint(endpoint_id: str) -> dict[str, Any]:
    """Delete an endpoint unless active references still exist."""
    credentials = load_credentials()
    roles = _load_roles_or_empty()
    refs = _endpoint_references(endpoint_id, credentials, roles)
    if refs["routes"] or refs["roles"] or refs["model_profiles"]:
        _raise_conflict(
            "endpoint_in_use",
            f"Endpoint is still referenced: {endpoint_id}",
            {"endpoint_id": endpoint_id, **refs},
        )
    data = delete_endpoint(endpoint_id)
    return serialize_for_response(data)


@router.post("/endpoints/{endpoint_id}/test", response_model=EndpointTestResponse)
async def test_endpoint(endpoint_id: str) -> EndpointTestResponse:
    """Verify an endpoint by making the provider's minimal models-list call."""
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint_id}")
    starting_fingerprint = credentials.endpoint_fingerprint(endpoint_id)
    status: Literal["unverified_manual", "failed"] = "failed"
    message = "API key is empty."
    model_list_reached = False
    discovered_model_ids: tuple[str, ...] = ()
    if endpoint.api_key and endpoint.api_key.get_secret_value():
        probe_backend = _endpoint_probe_backend(endpoint)
        probe_base_url = _endpoint_probe_base_url(endpoint)
        logger.warning(
            "testing LLM endpoint endpoint_id=%s protocol=%s backend=%s base_url=%s",
            endpoint_id,
            endpoint.protocol,
            probe_backend,
            probe_base_url,
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
                "last_test_message": (
                    "Endpoint changed while endpoint test was running. Test result discarded."
                ),
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
        latest_credentials, _ = _upsert_discovered_routes(
            latest_credentials,
            endpoint=latest_endpoint,
            model_ids=discovered_model_ids,
            verified=False,
            replace_endpoint_routes=True,
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
    successful_model_ids = [
        result.model_id for result in probe_results if result.status == "ok"
    ]
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
        route_ids_by_model: dict[str, str] = {}
    results = [
        EndpointModelTestResult(
            model_id=result.model_id,
            status=result.status,
            route_id=route_ids_by_model.get(result.model_id) if result.status == "ok" else None,
            message=result.message,
        )
        for result in probe_results
    ]
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
    if refs["roles"] or refs["model_profiles"]:
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
    role = (
        materialize_role(request, credentials, _health_store())
        if request.model_groups
        else request
    )
    roles = dict(data.roles)
    roles[role_name] = role
    schema_version = 3 if role.model_groups else data.schema_version
    saved = _save_roles_with_active_routes(
        data.model_copy(update={"schema_version": schema_version, "roles": roles})
    )
    return _materialize_role_for_response(saved.roles[role_name], credentials)


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
    model_groups: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []
    aggregate_status = "ok"
    for report_entry, fallback_entry in _role_test_entries(role):
        route_id = report_entry["route_id"]
        route = credentials.provider_routes.get(route_id)
        if route is None:
            continue
        endpoint = credentials.provider_endpoints.get(route.endpoint_id)
        if endpoint is None:
            continue
        provider_result = await _role_test_provider_result(
            fallback_entry,
            report_entry,
            route,
            endpoint,
        )
        if provider_result["warnings"]:
            warnings.extend(provider_result["warnings"])
        aggregate_status = _merge_role_test_status(aggregate_status, provider_result)
        canonical_id = str(report_entry.get("canonical_id") or route.canonical_id)
        identity = project_model_identity(route=route, endpoint=endpoint)
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


@router.get("/model-profiles")
async def get_model_profiles() -> dict[str, ModelProfile]:
    """Return model profiles."""
    return _load_roles_or_empty().model_profiles


@router.put("/model-profiles")
async def put_model_profiles(profiles: dict[str, ModelProfile]) -> dict[str, ModelProfile]:
    """Replace model profile set."""
    data = _load_roles_or_empty().model_copy(update={"model_profiles": profiles})
    return _save_roles_with_active_routes(data).model_profiles


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
            roles[role_name] = role.model_copy(
                update={"source_profile_id": None, "source_profile_snapshot": snapshot}
            )
        else:
            roles[role_name] = role
    return _save_roles_with_active_routes(
        data.model_copy(update={"model_profiles": profiles, "roles": roles})
    )


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
    roles = _materialize_roles_for_response(roles, credentials)
    routes_by_canonical: dict[str, list[str]] = {}
    for route_id, route in credentials.provider_routes.items():
        routes_by_canonical.setdefault(route.canonical_id, []).append(route_id)
    lint_results = []
    for role_name, role in roles.roles.items():
        role_routes = [
            route
            for entry in role.fallback_chain
            if (route := credentials.provider_routes.get(entry.route_id)) is not None
        ]
        lint_results.extend(lint_role_routes(role_name, role, role_routes))
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


def _model_groups_response(credentials: LLMCredentialsFile) -> list[dict[str, Any]]:
    routes_by_identity: dict[str, list[ProviderRoute]] = {}
    for route in credentials.provider_routes.values():
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


def _model_group_identity_key(
    route: ProviderRoute,
    credentials: LLMCredentialsFile,
) -> str:
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    if endpoint is None:
        return _normalize_model_group_key(route.canonical_id or route.route_slug)
    projection = project_model_identity(route=route, endpoint=endpoint)
    return _normalize_model_group_key(projection.display_name) or _normalize_model_group_key(
        route.canonical_id or route.route_slug
    )


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


def _normalize_model_group_key(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.strip().lower()))


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
    status_summary = {
        state: 0
        for state in ["ready", "untested", "cooling_down", "needs_setup", "off"]
    }
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
        projection = project_model_identity(route=route, endpoint=endpoint)
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
    projection = project_provider_model_state(
        endpoint=endpoint,
        route=route,
        circuits=circuits,
        now=datetime.now(UTC),
    )
    return {
        "route_id": route.route_id,
        "provider_label": endpoint.display_name,
        "provider_kind": endpoint.provider_kind,
        "provider_model_id": route.provider_model_id,
        "ui_state": projection.ui_state,
        "ui_detail": projection.ui_detail,
        "retry_at": projection.retry_at,
        "reason_code": projection.reason_code,
        "capability_state": _capability_state(route),
        "capabilities": route.capabilities,
    }


def _health_store() -> SqliteLlmHealthStore:
    return SqliteLlmHealthStore(credentials_path().with_name("llm_health.sqlite"))


def _capability_state(route: ProviderRoute) -> str:
    if not route.capabilities:
        return "unknown"
    return "known"


def _capability_summary(provider_models: list[dict[str, Any]]) -> dict[str, Any]:
    known_count = sum(1 for option in provider_models if option["capability_state"] != "unknown")
    return {
        "capability_known_count": known_count,
        "thinking": "unknown",
        "tools": "unknown",
        "structured_output": "unknown",
        "max_context_tokens": None,
        "max_output_tokens": None,
    }


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
                    "reason_code": "missing_key",
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
    entry,
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
    if role_fit in {"needs_test", "not_fit"}:
        admission_decision = "block"
        status = "blocked"
    elif admission_decision == "admit" and endpoint.api_key is not None and entry is not None:
        result = await _probe_model(
            _endpoint_probe_backend(endpoint),
            endpoint.api_key.get_secret_value(),
            _endpoint_probe_base_url(endpoint),
            route.provider_model_id,
        )
        status = "ok" if result.status == "ok" else "failed"
        if status == "ok":
            provider_ui_state = "ready"
        message = result.message
    resolved_settings = report_entry.get("resolved_settings")
    if resolved_settings is None and entry is not None:
        resolved_settings = entry.runtime_settings.model_dump(
            mode="json",
            exclude_none=True,
        )
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


def _role_test_entries(role: RoleEntry):
    fallback_by_route = {entry.route_id: entry for entry in role.fallback_chain}
    report = role.materialization_report if isinstance(role.materialization_report, dict) else {}
    report_entries = [
        entry
        for entry in report.get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("route_id"), str)
    ]
    if report_entries:
        return [
            (entry, fallback_by_route.get(entry["route_id"]))
            for entry in report_entries
        ]
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


def _provider_model_projection(route: ProviderRoute, endpoint: ProviderEndpoint):
    now = datetime.now(UTC)
    return project_provider_model_state(
        endpoint=endpoint,
        route=route,
        circuits=_health_store().get_active_circuits(
            route_id=route.route_id,
            endpoint_id=endpoint.endpoint_id,
            rate_limit_bucket=endpoint.rate_limit_bucket or endpoint.endpoint_id,
            now=now,
        ),
        now=now,
    )


def _admission_decision(ui_state: str) -> str:
    if ui_state == "cooling_down":
        return "temporary_skip"
    if ui_state in {"needs_setup", "off"}:
        return "block"
    return "admit"


def _upsert_discovered_routes(
    credentials: LLMCredentialsFile,
    *,
    endpoint: ProviderEndpoint,
    model_ids: tuple[str, ...],
    verified: bool,
    replace_endpoint_routes: bool = False,
) -> tuple[LLMCredentialsFile, dict[str, str]]:
    routes = dict(credentials.provider_routes)
    route_ids_by_model: dict[str, str] = {}
    for model_id in model_ids:
        route_id = _route_id(endpoint.endpoint_id, model_id, routes)
        route_ids_by_model[model_id] = route_id
        existing = routes.get(route_id)
        status: Literal["verified", "unverified_manual"] = (
            "verified" if verified else "unverified_manual"
        )
        capability_source = "probed_verified" if verified else "api_list"
        if existing is None:
            routes[route_id] = _provider_route(
                endpoint=endpoint,
                model_id=model_id,
                status=status,
                capability_source=capability_source,
            )
            continue
        updates: dict[str, Any] = {}
        if verified:
            updates["status"] = "verified"
            updates["capabilities"] = {
                **existing.capabilities,
                **normalize_route_capabilities(
                    protocol=endpoint.protocol,
                    provider_model_id=model_id,
                    raw_capabilities={},
                    source=capability_source,
                ),
            }
        routes[route_id] = existing.model_copy(update=updates) if updates else existing
    if replace_endpoint_routes:
        discovered_model_ids = set(model_ids)
        routes = {
            route_id: route
            for route_id, route in routes.items()
            if route.endpoint_id != endpoint.endpoint_id
            or route.provider_model_id in discovered_model_ids
        }
    return credentials.model_copy(update={"provider_routes": routes}), route_ids_by_model


def _provider_route(
    *,
    endpoint: ProviderEndpoint,
    model_id: str,
    status: Literal["verified", "unverified_manual"],
    capability_source: Literal["api_list", "probed_verified"],
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
        capabilities=normalize_route_capabilities(
            protocol=endpoint.protocol,
            provider_model_id=model_id,
            raw_capabilities={},
            source=capability_source,
        ),
    )


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
    snapshot = roles.to_registry_snapshot(credentials)
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for role_name in roles.roles:
        try:
            resolved = resolve_role(snapshot, role_name)
        except RegistryResolutionError:
            continue
        result[role_name] = {
            route.route_id: route.effective_runtime_settings
            for route in resolved.routes
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
    if not any(role.model_groups for role in data.roles.values()):
        return data
    active_credentials = credentials or load_credentials()
    health_store = _health_store()
    return data.model_copy(
        update={
            "schema_version": 3,
            "roles": {
                role_name: materialize_role(role, active_credentials, health_store)
                if role.model_groups
                else role
                for role_name, role in data.roles.items()
            },
        }
    )


def _materialize_role_for_response(
    role: RoleEntry,
    credentials: LLMCredentialsFile | None = None,
) -> RoleEntry:
    if not role.model_groups:
        return role
    return materialize_role(role, credentials or load_credentials(), _health_store())


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
        route_id
        for route_id, route in credentials.provider_routes.items()
        if route.endpoint_id == endpoint_id
    ]
    refs = {"routes": route_ids, "roles": [], "model_profiles": []}
    route_set = set(route_ids)
    for role_name, role in roles.roles.items():
        for index, entry in enumerate(role.fallback_chain):
            if entry.route_id in route_set:
                refs["roles"].append(f"{role_name}.fallback_chain[{index}]")
    for profile_id, profile in roles.model_profiles.items():
        for index, entry in enumerate(profile.fallback_chain):
            if entry.route_id in route_set:
                refs["model_profiles"].append(f"{profile_id}.fallback_chain[{index}]")
    return refs


def _route_references(route_id: str, roles: RolesData) -> dict[str, list[str]]:
    refs = {"roles": [], "model_profiles": []}
    for role_name, role in roles.roles.items():
        for index, entry in enumerate(role.fallback_chain):
            if entry.route_id == route_id:
                refs["roles"].append(f"{role_name}.fallback_chain[{index}]")
    for profile_id, profile in roles.model_profiles.items():
        for index, entry in enumerate(profile.fallback_chain):
            if entry.route_id == route_id:
                refs["model_profiles"].append(f"{profile_id}.fallback_chain[{index}]")
    return refs


def _capability_key(value: str) -> str:
    return {
        "thinking": "thinking_protocol",
        "tool_calling": "tool_protocol",
        "structured_output": "structured_output_protocol",
    }.get(value, value)


def _endpoint_probe_backend(endpoint: ProviderEndpoint) -> CopilotProvider:
    base_url = endpoint.base_url.lower()
    endpoint_id = endpoint.endpoint_id.lower()
    if endpoint.protocol == "ark_runtime" or "volces.com" in base_url or "ark" in endpoint_id:
        return "ark"
    if endpoint.protocol == "anthropic_compatible":
        return "claude"
    if endpoint.protocol == "google_genai":
        return "gemini"
    if "deepseek" in base_url or "deepseek" in endpoint_id:
        return "deepseek"
    return "openai"


def _endpoint_probe_base_url(endpoint: ProviderEndpoint) -> str:
    return endpoint.base_url.rstrip("/")


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


def _raise_conflict(error_code: str, message: str, details: dict[str, Any]) -> None:
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
