"""Pure deterministic registry resolver."""

from __future__ import annotations

from pydantic import ValidationError

from graph_agent_gateway.registry.lint import lint_role_routes
from graph_agent_gateway.registry.schema import (
    RegistrySnapshot,
    ResolvedRole,
    ResolvedRoute,
    RoleEntry,
    RoleRouteEntry,
)
from graph_agent_gateway.registry.storage import compute_credential_fingerprint

EXECUTABLE_ROUTE_STATUSES = {"verified", "unverified_manual"}


class RegistryResolutionError(ValueError):
    """Registry resolution failed before any provider call."""


def resolve_role(
    snapshot: RegistrySnapshot,
    role_name: str,
    *,
    route_override: str | None = None,
) -> ResolvedRole:
    """Resolve one role to an ordered route chain without dynamic matching."""
    role = snapshot.roles.get(role_name)
    if role is None:
        raise RegistryResolutionError(f"role is not configured: {role_name}")

    try:
        entries = (
            [RoleRouteEntry(route_id=route_override)]
            if route_override is not None
            else role.fallback_chain
        )
    except ValidationError as exc:
        raise RegistryResolutionError(f"invalid route override: {route_override}") from exc
    provider_routes = []
    resolved_routes = []
    for entry in entries:
        route = snapshot.provider_routes.get(entry.route_id)
        if route is None:
            raise RegistryResolutionError(f"route is not configured: {entry.route_id}")
        if route.status not in EXECUTABLE_ROUTE_STATUSES:
            raise RegistryResolutionError(f"route is not executable: {entry.route_id}")
        endpoint = snapshot.provider_endpoints.get(route.endpoint_id)
        if endpoint is None:
            raise RegistryResolutionError(f"endpoint is not configured: {route.endpoint_id}")
        if endpoint.api_key is None or not endpoint.api_key.get_secret_value():
            raise RegistryResolutionError(f"endpoint has no credential: {route.endpoint_id}")
        provider_routes.append(route)
        resolved_routes.append(
            ResolvedRoute(
                role_name=role_name,
                route_id=route.route_id,
                endpoint_id=route.endpoint_id,
                protocol=endpoint.protocol,
                base_url=endpoint.base_url,
                api_key=endpoint.api_key,
                credential_fingerprint=compute_credential_fingerprint(endpoint),
                timeout_seconds=endpoint.timeout_seconds,
                trust_env=endpoint.trust_env,
                proxy_env=endpoint.proxy_env,
                provider_model_id=route.provider_model_id,
                canonical_id=route.canonical_id,
                display_name=route.display_name,
                capabilities=route.capabilities,
                temperature=entry.temperature,
                max_output_tokens=entry.max_output_tokens,
            )
        )

    lints = lint_role_routes(role_name, role, provider_routes)
    blocking = [item for item in lints if item.blocking]
    if blocking:
        first = blocking[0]
        raise RegistryResolutionError(
            f"route {first.route_id} blocked by lint {first.capability}: {first.message}"
        )

    return ResolvedRole(
        role_name=role_name,
        system_prompt_prefix=role.system_prompt_prefix,
        runtime_policy=snapshot.runtime_policy,
        routes=resolved_routes,
        lint_results=lints,
        source_profile_id=role.source_profile_id,
        source_profile_snapshot=role.source_profile_snapshot,
    )
