"""Pure deterministic registry resolver."""

from __future__ import annotations

from pydantic import ValidationError

from graph_agent_gateway.registry.contracts import CredentialDescriptor, CredentialProviderProtocol
from graph_agent_gateway.registry.fingerprint import compute_credential_fingerprint
from graph_agent_gateway.registry.lint import lint_role_routes
from graph_agent_gateway.registry.profile_selector import (
    ProfileSelectionError,
    select_verified_profile,
)
from graph_agent_gateway.registry.schema import (
    CapabilityValue,
    EffectiveRuntimeSetting,
    ModelBundle,
    ProviderEndpoint,
    ProviderRoute,
    RegistrySnapshot,
    ResolvedRole,
    ResolvedRoute,
    RoleEntry,
    RoleRouteEntry,
    RuntimeSettings,
    SkippedRoute,
    VerifiedProfile,
)

EXECUTABLE_ROUTE_STATUSES = {"verified", "unverified_manual"}


class RegistryResolutionError(ValueError):
    """Registry resolution failed before any provider call."""

    skipped_diagnostics: list[SkippedRoute]


def resolve_role(
    snapshot: RegistrySnapshot,
    role_name: str,
    *,
    route_override: str | None = None,
    credential_provider: CredentialProviderProtocol | None = None,
) -> ResolvedRole:
    """Resolve one role to an ordered route chain without dynamic matching."""
    role = snapshot.roles.get(role_name)
    if role is None:
        raise RegistryResolutionError(f"role is not configured: {role_name}")
    role = materialize_role_entry(snapshot, role_name, role)

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
    skipped_diagnostics = []
    from_override = route_override is not None

    for entry in entries:
        route_id = entry.route_id
        route = snapshot.provider_routes.get(route_id)
        if route is None:
            msg = f"route is not configured: {route_id}"
            if from_override:
                raise RegistryResolutionError(msg)
            skipped_diagnostics.append(
                SkippedRoute(
                    route_id=route_id,
                    reason_code="route_missing",
                    message=msg,
                    from_override=False,
                )
            )
            continue

        if route.status not in EXECUTABLE_ROUTE_STATUSES:
            msg = f"route is not executable: {route_id}"
            if from_override:
                raise RegistryResolutionError(msg)
            skipped_diagnostics.append(
                SkippedRoute(
                    route_id=route_id,
                    reason_code="route_not_executable",
                    message=msg,
                    from_override=False,
                )
            )
            continue

        endpoint = snapshot.provider_endpoints.get(route.endpoint_id)
        if endpoint is None:
            msg = f"endpoint is not configured: {route.endpoint_id}"
            if from_override:
                raise RegistryResolutionError(msg)
            skipped_diagnostics.append(
                SkippedRoute(
                    route_id=route_id,
                    reason_code="endpoint_missing",
                    message=msg,
                    from_override=False,
                )
            )
            continue

        credential_ref = endpoint.credential_ref or f"endpoint:{endpoint.endpoint_id}"
        credential_descriptor = _describe_credential(credential_provider, credential_ref)
        if (
            endpoint.api_key is None or not endpoint.api_key.get_secret_value()
        ) and not endpoint.credential_ref and not (
            credential_descriptor is not None and credential_descriptor.exists
        ):
            msg = f"endpoint has no credential: {route.endpoint_id}"
            if from_override:
                raise RegistryResolutionError(msg)
            skipped_diagnostics.append(
                SkippedRoute(
                    route_id=route_id,
                    reason_code="credential_missing",
                    message=msg,
                    from_override=False,
                )
            )
            continue

        live_route = _route_with_live_snapshot_evidence(snapshot, route)

        try:
            selected_profile = select_verified_profile(live_route, entry.runtime_settings)
        except ProfileSelectionError as exc:
            msg = str(exc)
            if from_override:
                raise RegistryResolutionError(msg) from exc
            skipped_diagnostics.append(
                SkippedRoute(
                    route_id=route_id,
                    reason_code="profile_unavailable",
                    message=msg,
                    from_override=False,
                )
            )
            continue

        provider_routes.append(live_route)
        resolved_routes.append(
            ResolvedRoute(
                role_name=role_name,
                route_id=route.route_id,
                endpoint_id=route.endpoint_id,
                protocol=endpoint.protocol,
                base_url=endpoint.base_url,
                credential_ref=credential_ref,
                credential_fingerprint=_credential_fingerprint(
                    endpoint,
                    credential_descriptor,
                ),
                timeout_seconds=endpoint.timeout_seconds,
                trust_env=endpoint.trust_env,
                proxy_env=endpoint.proxy_env,
                provider_model_id=route.provider_model_id,
                canonical_id=route.canonical_id,
                selected_profile_id=(
                    selected_profile.profile_id if selected_profile is not None else None
                ),
                selected_profile_capability=(
                    selected_profile.capability if selected_profile is not None else None
                ),
                call_method_id=selected_profile.method_id if selected_profile is not None else None,
                request_mapper_id=(
                    selected_profile.request_mapper_id if selected_profile is not None else None
                ),
                capabilities=live_route.capabilities,
                runtime_settings=entry.runtime_settings,
                snapshot_version=snapshot.snapshot_version,
                effective_runtime_settings=_effective_runtime_settings(
                    entry,
                    entry.runtime_settings,
                    live_route.capabilities,
                    endpoint.protocol,
                    selected_profile,
                ),
            )
        )

    lints = lint_role_routes(role_name, role, provider_routes)
    blocking = [item for item in lints if item.blocking]
    if blocking:
        if from_override:
            first = blocking[0]
            raise RegistryResolutionError(
                f"route {first.route_id} blocked by lint {first.capability}: {first.message}"
            )
        else:
            blocked_route_ids = {item.route_id for item in blocking}
            new_resolved_routes = []
            new_provider_routes = []
            for r_route, p_route in zip(resolved_routes, provider_routes, strict=True):
                if r_route.route_id in blocked_route_ids:
                    lint_msgs = [item.message for item in blocking if item.route_id == r_route.route_id]
                    msg = f"route {r_route.route_id} blocked by lint: " + "; ".join(lint_msgs)
                    skipped_diagnostics.append(
                        SkippedRoute(
                            route_id=r_route.route_id,
                            reason_code="lint_blocked",
                            message=msg,
                            from_override=False,
                        )
                    )
                else:
                    new_resolved_routes.append(r_route)
                    new_provider_routes.append(p_route)
            resolved_routes = new_resolved_routes
            provider_routes = new_provider_routes

    if not resolved_routes:
        if not skipped_diagnostics:
            raise RegistryResolutionError(f"role '{role_name}' has an empty fallback chain.")
        else:
            summary = "; ".join(f"{item.route_id} ({item.reason_code}): {item.message}" for item in skipped_diagnostics)
            error = RegistryResolutionError(
                f"Registry resolution failed for role '{role_name}'. All routes were skipped: {summary}"
            )
            error.skipped_diagnostics = skipped_diagnostics
            raise error

    return ResolvedRole(
        role_name=role_name,
        system_prompt_prefix=role.system_prompt_prefix,
        runtime_policy=snapshot.runtime_policy,
        routes=resolved_routes,
        lint_results=lints,
        skipped_diagnostics=skipped_diagnostics,
        source_profile_id=role.source_profile_id,
        source_profile_snapshot=role.source_profile_snapshot,
    )


def materialize_role_entry(
    snapshot: RegistrySnapshot,
    role_name: str,
    role: RoleEntry | None = None,
) -> RoleEntry:
    """Materialize a role's bundle reference into an executable route chain."""
    role = role or snapshot.roles.get(role_name)
    if role is None:
        raise RegistryResolutionError(f"role is not configured: {role_name}")
    if role.bundle_id is None:
        return role

    bundle = snapshot.model_bundles.get(role.bundle_id)
    if bundle is None:
        raise RegistryResolutionError(
            f"model bundle is not configured for role '{role_name}': {role.bundle_id}"
        )

    return role.model_copy(
        update={
            "fallback_chain": _materialize_bundle_chain(bundle, role.fallback_chain),
            "lint_requirements": {
                **bundle.lint_requirements,
                **role.lint_requirements,
            },
        }
    )


def _materialize_bundle_chain(
    bundle: ModelBundle,
    role_delta_chain: list[RoleRouteEntry],
) -> list[RoleRouteEntry]:
    overrides = {entry.route_id: entry for entry in role_delta_chain}
    materialized: list[RoleRouteEntry] = []

    for bundle_entry in bundle.fallback_chain:
        override = overrides.get(bundle_entry.route_id)
        if override is None:
            materialized.append(bundle_entry)
            continue
        materialized.append(_merge_role_route_entry(bundle_entry, override))

    return materialized


def _merge_role_route_entry(
    base: RoleRouteEntry,
    delta: RoleRouteEntry,
) -> RoleRouteEntry:
    return RoleRouteEntry(
        route_id=base.route_id,
        runtime_settings_source=delta.runtime_settings_source,
        runtime_settings=_merge_runtime_settings(base.runtime_settings, delta.runtime_settings),
    )


def _merge_runtime_settings(base: RuntimeSettings, delta: RuntimeSettings) -> RuntimeSettings:
    base_payload = base.model_dump(mode="python", exclude_none=True)
    delta_payload = delta.model_dump(mode="python", exclude_none=True)
    return RuntimeSettings.model_validate(_deep_merge(base_payload, delta_payload))


def _deep_merge(base: dict[str, object], delta: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in delta.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        elif value != {}:
            merged[key] = value
    return merged


def _describe_credential(
    credential_provider: CredentialProviderProtocol | None,
    credential_ref: str,
) -> CredentialDescriptor | None:
    if credential_provider is None:
        return None
    try:
        return credential_provider.describe(credential_ref)
    except Exception:
        return None


def _credential_fingerprint(
    endpoint: ProviderEndpoint,
    credential_descriptor: CredentialDescriptor | None,
) -> str:
    if credential_descriptor is not None and credential_descriptor.fingerprint:
        return credential_descriptor.fingerprint
    return compute_credential_fingerprint(endpoint)


def _route_with_live_snapshot_evidence(
    snapshot: RegistrySnapshot,
    route: ProviderRoute,
) -> ProviderRoute:
    if snapshot.snapshot_version is None or route.snapshot_version == snapshot.snapshot_version:
        return route
    return route.model_copy(update={"capabilities": {}, "verified_profiles": []})


def _effective_runtime_settings(
    entry: RoleRouteEntry,
    settings: RuntimeSettings,
    capabilities: dict[str, CapabilityValue],
    protocol: str,
    selected_profile: VerifiedProfile | None = None,
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

    if selected_profile is not None:
        _apply_profile_runtime_overrides(effective, settings, selected_profile)

    return effective


def _apply_profile_runtime_overrides(
    effective: dict[str, EffectiveRuntimeSetting],
    settings: RuntimeSettings,
    selected_profile: VerifiedProfile,
) -> None:
    reasoning = selected_profile.runtime_overrides.get("reasoning")
    if not isinstance(reasoning, dict):
        return

    if settings.reasoning.enabled is None and "enabled" in reasoning:
        effective["reasoning.enabled"] = EffectiveRuntimeSetting(
            value=reasoning["enabled"],
            source="profile_default",
        )
    if settings.reasoning.effort is None and "effort" in reasoning:
        effective["reasoning.effort"] = EffectiveRuntimeSetting(
            value=reasoning["effort"],
            source="profile_default",
        )
    if settings.reasoning.budget_tokens is None and "budget_tokens" in reasoning:
        effective["reasoning.budget_tokens"] = EffectiveRuntimeSetting(
            value=reasoning["budget_tokens"],
            source="profile_default",
        )


def _capability_default(capability: CapabilityValue | None) -> object | None:
    if capability is None:
        return None
    value = capability.value
    if isinstance(value, dict):
        return value.get("default")
    if capability.source == "manual" and isinstance(value, int | float | str | bool):
        return value
    return None
