"""Pure deterministic registry resolver."""

from __future__ import annotations

from pydantic import ValidationError

from graph_agent_gateway.registry.lint import lint_role_routes
from graph_agent_gateway.registry.schema import (
    CapabilityValue,
    EffectiveRuntimeSetting,
    RegistrySnapshot,
    ResolvedRole,
    ResolvedRoute,
    RoleRouteEntry,
    RuntimeSettings,
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
                capabilities=route.capabilities,
                runtime_settings=entry.runtime_settings,
                effective_runtime_settings=_effective_runtime_settings(
                    entry,
                    entry.runtime_settings,
                    route.capabilities,
                    endpoint.protocol,
                ),
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


def _effective_runtime_settings(
    entry: RoleRouteEntry,
    settings: RuntimeSettings,
    capabilities: dict[str, CapabilityValue],
    protocol: str,
) -> dict[str, EffectiveRuntimeSetting]:
    effective: dict[str, EffectiveRuntimeSetting] = {}
    entry_source = entry.runtime_settings_source

    if settings.temperature is not None:
        effective["temperature"] = EffectiveRuntimeSetting(
            value=settings.temperature,
            source=entry_source,
        )
    else:
        effective["temperature"] = EffectiveRuntimeSetting(
            value=1.0 if protocol == "anthropic_compatible" else 0.7,
            source="protocol_default",
        )

    if settings.top_p is not None:
        effective["top_p"] = EffectiveRuntimeSetting(value=settings.top_p, source=entry_source)

    if settings.max_output_tokens is not None:
        effective["max_output_tokens"] = EffectiveRuntimeSetting(
            value=settings.max_output_tokens,
            source=entry_source,
        )
    else:
        default_max_output = _capability_default(capabilities.get("max_output_tokens"))
        if default_max_output is not None:
            effective["max_output_tokens"] = EffectiveRuntimeSetting(
                value=default_max_output,
                source="route_capability_default",
            )
        else:
            effective["max_output_tokens"] = EffectiveRuntimeSetting(
                value=4096,
                source="studio_default",
            )

    if settings.stop_sequences is not None:
        effective["stop_sequences"] = EffectiveRuntimeSetting(
            value=list(settings.stop_sequences),
            source=entry_source,
        )

    if settings.seed is not None:
        effective["seed"] = EffectiveRuntimeSetting(value=settings.seed, source=entry_source)

    if settings.tool_choice is not None:
        effective["tool_choice"] = EffectiveRuntimeSetting(
            value=settings.tool_choice,
            source=entry_source,
        )

    if settings.parallel_tool_calls is not None:
        effective["parallel_tool_calls"] = EffectiveRuntimeSetting(
            value=settings.parallel_tool_calls,
            source=entry_source,
        )

    if settings.structured_output is not None:
        effective["structured_output.mode"] = EffectiveRuntimeSetting(
            value=settings.structured_output.mode,
            source=entry_source,
        )
        if settings.structured_output.json_schema is not None:
            effective["structured_output.json_schema"] = EffectiveRuntimeSetting(
                value=settings.structured_output.json_schema,
                source=entry_source,
            )
        if settings.structured_output.strict is not None:
            effective["structured_output.strict"] = EffectiveRuntimeSetting(
                value=settings.structured_output.strict,
                source=entry_source,
            )

    if settings.reasoning.enabled is not None:
        effective["reasoning.enabled"] = EffectiveRuntimeSetting(
            value=settings.reasoning.enabled,
            source=entry_source,
        )
    else:
        effective["reasoning.enabled"] = EffectiveRuntimeSetting(
            value=False,
            source="studio_default",
        )

    if settings.reasoning.effort is not None:
        effective["reasoning.effort"] = EffectiveRuntimeSetting(
            value=settings.reasoning.effort,
            source=entry_source,
        )

    if settings.reasoning.budget_tokens is not None:
        effective["reasoning.budget_tokens"] = EffectiveRuntimeSetting(
            value=settings.reasoning.budget_tokens,
            source=entry_source,
        )
    elif effective["reasoning.enabled"].value is True:
        default_budget = _capability_default(capabilities.get("reasoning_budget_tokens"))
        if default_budget is None:
            default_budget = _capability_default(capabilities.get("default_thinking_budget_tokens"))
        if default_budget is not None:
            effective["reasoning.budget_tokens"] = EffectiveRuntimeSetting(
                value=default_budget,
                source="route_capability_default",
            )

    return effective


def _capability_default(capability: CapabilityValue | None) -> object | None:
    if capability is None:
        return None
    value = capability.value
    if isinstance(value, dict):
        return value.get("default")
    if capability.source == "manual" and isinstance(value, int | float | str | bool):
        return value
    return None
