"""Studio LLM registry API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
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
    PingResult,
    _NetworkError,
    _ping_provider,
    _QuotaExceeded,
    _RateLimited,
    _Unauthorized,
)
from app.services.llm_credentials import (
    credentials_path,
    delete_endpoint,
    delete_route,
    load_credentials,
    save_credentials,
    serialize_for_response,
    upsert_endpoints,
    upsert_routes,
)
from app.services.llm_import_drafts import (
    DraftApplyConflict,
    DraftExpired,
    DraftNotFound,
    apply_draft,
    create_draft,
    load_draft,
)
from app.services.llm_roles import (
    InvalidRoleReference,
    get_role,
    load_roles_file,
    roles_path,
    save_roles_file,
    validate_references,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])


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


@router.post("/endpoints/{endpoint_id}/test")
async def test_endpoint(endpoint_id: str) -> ProviderEndpoint:
    """Verify an endpoint by making the provider's minimal models-list call."""
    credentials = load_credentials()
    endpoint = credentials.provider_endpoints.get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint_id}")
    status: Literal["verified", "failed"] = "failed"
    message = "API key is empty."
    if endpoint.api_key and endpoint.api_key.get_secret_value():
        try:
            result = await _ping_provider(
                _endpoint_probe_backend(endpoint),
                endpoint.api_key.get_secret_value(),
                _endpoint_probe_base_url(endpoint),
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
            status = "verified"
            message = _endpoint_success_message(result)
    updated = endpoint.model_copy(
        update={
            "status": status,
            "last_test_at": _now_iso(),
            "last_test_message": message,
        }
    )
    credentials.provider_endpoints[endpoint_id] = updated
    save_credentials(credentials)
    return updated


@router.post("/routes/{route_id}/probe")
async def probe_route(route_id: str, request: RouteProbeRequest) -> ProviderRoute:
    """Probe one route and update normalized capability metadata."""
    credentials = load_credentials()
    route = credentials.provider_routes.get(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"Unknown route: {route_id}")
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {route.endpoint_id}")
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
    return _load_roles_or_empty()


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
    return _save_roles_with_active_routes(merged)


@router.get("/roles/{role_name}", response_model=RoleEntry)
async def get_llm_role(role_name: str) -> RoleEntry:
    """Return one role."""
    data = _load_roles_or_empty()
    try:
        return get_role(data, role_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown LLM role: {role_name}") from exc


@router.put("/roles/{role_name}", response_model=RoleEntry)
async def put_llm_role(role_name: str, request: RoleEntry) -> RoleEntry:
    """Full replace one role."""
    data = _load_roles_or_empty()
    roles = dict(data.roles)
    roles[role_name] = request
    saved = _save_roles_with_active_routes(data.model_copy(update={"roles": roles}))
    return saved.roles[role_name]


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
        lint_results=lint_results,
        route_runtime_settings={
            route_id: build_runtime_setting_descriptors(route)
            for route_id, route in credentials.provider_routes.items()
        },
        role_effective_runtime_settings=_role_effective_runtime_settings(credentials, roles),
        setup_required=setup_required,
    )


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
    if endpoint.protocol == "anthropic_compatible":
        return "claude"
    if endpoint.protocol == "google_genai":
        return "gemini"
    if "deepseek" in endpoint.base_url.lower() or "deepseek" in endpoint.endpoint_id.lower():
        return "deepseek"
    return "openai"


def _endpoint_probe_base_url(endpoint: ProviderEndpoint) -> str:
    base_url = endpoint.base_url.rstrip("/")
    if (
        endpoint.protocol in ("anthropic_compatible", "openai_compatible")
        and base_url.endswith("/v1")
    ):
        return base_url[: -len("/v1")]
    if endpoint.protocol == "google_genai" and base_url.endswith("/v1beta"):
        return base_url[: -len("/v1beta")]
    return base_url


def _endpoint_success_message(result: PingResult) -> str:
    message = f"Connected in {result.latency_ms}ms."
    if result.model_seen:
        message = f"{message} Model seen: {result.model_seen}."
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
