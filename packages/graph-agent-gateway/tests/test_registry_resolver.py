"""Deterministic registry resolver tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr


def _snapshot():
    from graph_agent_gateway.registry.schema import (
        CapabilityValue,
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    return RegistrySnapshot(
        provider_endpoints={
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.com",
                api_key=SecretStr("anthropic-secret"),
            ),
            "openrouter-prod": ProviderEndpoint(
                endpoint_id="openrouter-prod",
                protocol="openai_compatible",
                base_url="https://openrouter.ai/api/v1",
                credential_ref="cred:openrouter-prod",
                api_key=SecretStr("openrouter-secret"),
            ),
        },
        provider_routes={
            "anthropic-official:claude": ProviderRoute(
                route_id="anthropic-official:claude",
                endpoint_id="anthropic-official",
                route_slug="claude",
                provider_model_id="claude",
                canonical_id="claude",
                status="verified",
                capabilities={
                    "thinking_protocol": CapabilityValue(value=True, source="manual"),
                },
            ),
            "openrouter-prod:anthropic.claude": ProviderRoute(
                route_id="openrouter-prod:anthropic.claude",
                endpoint_id="openrouter-prod",
                route_slug="anthropic.claude",
                provider_model_id="anthropic/claude",
                canonical_id="claude",
                status="unverified_manual",
            ),
        },
        roles={
            "graph_agent": RoleEntry(
                system_prompt_prefix="prefix",
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="anthropic-official:claude",
                        runtime_settings={
                            "temperature": 0.2,
                            "max_output_tokens": 8192,
                            "reasoning": {"enabled": True, "budget_tokens": 4096},
                        },
                    ),
                    RoleRouteEntry(route_id="openrouter-prod:anthropic.claude"),
                ],
            )
        },
    )


def _snapshot_with_stale_provider_route(
    *,
    capabilities: dict[str, object] | None = None,
    verified_profiles: list[object] | None = None,
    route_runtime_settings: dict[str, object] | None = None,
):
    from graph_agent_gateway.registry.contracts import SnapshotVersion
    from graph_agent_gateway.registry.schema import (
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    old_version = SnapshotVersion(
        registry_version="registry-1",
        client_id="graph_agent",
        client_route_profile_version="profile-1",
    )
    current_version = SnapshotVersion(
        registry_version="registry-2",
        client_id="graph_agent",
        client_route_profile_version="profile-2",
    )
    route_kwargs: dict[str, object] = {
        "route_id": "provider:model",
        "endpoint_id": "provider",
        "route_slug": "model",
        "provider_model_id": "model",
        "canonical_id": "model",
        "status": "verified",
        "snapshot_version": old_version,
    }
    if capabilities is not None:
        route_kwargs["capabilities"] = capabilities
    if verified_profiles is not None:
        route_kwargs["verified_profiles"] = verified_profiles

    fallback_kwargs: dict[str, object] = {"route_id": "provider:model"}
    if route_runtime_settings is not None:
        fallback_kwargs["runtime_settings"] = route_runtime_settings

    return RegistrySnapshot(
        snapshot_version=current_version,
        provider_endpoints={
            "provider": ProviderEndpoint(
                endpoint_id="provider",
                protocol="openai_compatible",
                base_url="https://provider.example/v1",
                api_key=SecretStr("secret"),
            ),
        },
        provider_routes={"provider:model": ProviderRoute(**route_kwargs)},
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[RoleRouteEntry(**fallback_kwargs)],
            )
        },
    ), current_version


def test_resolver_preserves_declared_route_order_and_role_metadata() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role

    resolved = resolve_role(_snapshot(), "graph_agent")

    assert resolved.role_name == "graph_agent"
    assert resolved.system_prompt_prefix == "prefix"
    assert [route.route_id for route in resolved.routes] == [
        "anthropic-official:claude",
        "openrouter-prod:anthropic.claude",
    ]
    assert resolved.routes[0].provider_model_id == "claude"
    assert resolved.routes[0].runtime_settings.temperature == 0.2
    assert resolved.routes[0].effective_runtime_settings["max_output_tokens"].value == 8192
    assert resolved.routes[0].effective_runtime_settings["reasoning.enabled"].value is True
    assert resolved.routes[0].effective_runtime_settings["reasoning.budget_tokens"].value == 4096
    assert resolved.routes[0].credential_ref == "endpoint:anthropic-official"
    assert resolved.routes[1].credential_ref == "cred:openrouter-prod"
    assert "api_key" not in resolved.routes[0].model_dump(mode="json")
    assert "api_key" not in resolved.routes[1].model_dump(mode="json")
    assert resolved.runtime_policy.provider_down_ttl_seconds == 60


def test_resolver_materializes_bundle_reference_with_role_delta_settings() -> None:
    from graph_agent_gateway.registry.resolver import materialize_role_entry, resolve_role
    from graph_agent_gateway.registry.schema import (
        CapabilityValue,
        ModelBundle,
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
            ),
            "anthropic": ProviderEndpoint(
                endpoint_id="anthropic",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.example",
                api_key=SecretStr("secret"),
            ),
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status="verified",
                capabilities={
                    "thinking_protocol": CapabilityValue(value=True, source="manual"),
                },
            ),
            "anthropic:claude": ProviderRoute(
                route_id="anthropic:claude",
                endpoint_id="anthropic",
                route_slug="claude",
                provider_model_id="claude",
                canonical_id="claude",
                status="verified",
            ),
        },
        model_bundles={
            "analysis": ModelBundle(
                bundle_id="analysis",
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="openai:gpt-5",
                        runtime_settings={
                            "temperature": 0.2,
                            "reasoning": {"enabled": True, "budget_tokens": 4096},
                        },
                    ),
                    RoleRouteEntry(
                        route_id="anthropic:claude",
                        runtime_settings={"temperature": 0.4},
                    ),
                ],
                lint_requirements={"thinking": "warn"},
            )
        },
        roles={
            "graph_agent": RoleEntry(
                bundle_id="analysis",
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="openai:gpt-5",
                        runtime_settings={
                            "max_output_tokens": 8192,
                            "reasoning": {"budget_tokens": 2048},
                        },
                    ),
                    RoleRouteEntry(
                        route_id="ghost:model",
                        runtime_settings={"temperature": 1.0},
                    ),
                ],
                lint_requirements={"tool_calling": "off"},
            )
        },
    )

    materialized = materialize_role_entry(
        snapshot,
        "graph_agent",
        snapshot.roles["graph_agent"],
    )
    resolved = resolve_role(snapshot, "graph_agent")

    assert [entry.route_id for entry in materialized.fallback_chain] == [
        "openai:gpt-5",
        "anthropic:claude",
    ]
    assert materialized.lint_requirements == {
        "thinking": "warn",
        "tool_calling": "off",
    }
    assert materialized.fallback_chain[0].runtime_settings.temperature == 0.2
    assert materialized.fallback_chain[0].runtime_settings.max_output_tokens == 8192
    assert materialized.fallback_chain[0].runtime_settings.reasoning.enabled is True
    assert materialized.fallback_chain[0].runtime_settings.reasoning.budget_tokens == 2048
    assert [route.route_id for route in resolved.routes] == [
        "openai:gpt-5",
        "anthropic:claude",
    ]
    assert resolved.routes[0].runtime_settings.temperature == 0.2
    assert resolved.routes[0].runtime_settings.max_output_tokens == 8192
    assert resolved.routes[0].runtime_settings.reasoning.enabled is True
    assert resolved.routes[0].runtime_settings.reasoning.budget_tokens == 2048
    assert "ghost:model" not in [item.route_id for item in materialized.fallback_chain]


def test_resolver_propagates_snapshot_version_to_resolved_routes() -> None:
    from graph_agent_gateway.registry.contracts import SnapshotVersion
    from graph_agent_gateway.registry.resolver import resolve_role

    snapshot = _snapshot()
    snapshot.snapshot_version = SnapshotVersion(
        registry_version="registry-2",
        client_id="graph_agent",
        client_route_profile_version="profile-2",
    )
    for route in snapshot.provider_routes.values():
        route.snapshot_version = snapshot.snapshot_version

    resolved = resolve_role(snapshot, "graph_agent")

    assert [route.snapshot_version for route in resolved.routes] == [
        snapshot.snapshot_version,
        snapshot.snapshot_version,
    ]


def test_snapshot_version_mismatch_keeps_verified_profile_historical_not_live_ready() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role
    from graph_agent_gateway.registry.schema import VerifiedProfile

    snapshot, current_version = _snapshot_with_stale_provider_route(
        verified_profiles=[
            VerifiedProfile(
                profile_id="text",
                capability="text_chat",
                method_id="openai_chat_completions",
                request_mapper_id="openai_chat_text",
                status="ready",
                default=True,
            )
        ],
    )

    resolved = resolve_role(snapshot, "graph_agent")

    assert resolved.routes[0].snapshot_version == current_version
    assert resolved.routes[0].selected_profile_id is None
    assert resolved.routes[0].call_method_id is None
    assert resolved.routes[0].request_mapper_id is None


def test_snapshot_version_mismatch_ignores_stale_capability_runtime_defaults() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role
    from graph_agent_gateway.registry.schema import CapabilityValue

    snapshot, current_version = _snapshot_with_stale_provider_route(
        capabilities={
            "max_output_tokens": CapabilityValue(
                value={"default": 12000, "max": 16000},
                source="manual",
            ),
        },
    )

    resolved = resolve_role(snapshot, "graph_agent")

    route = resolved.routes[0]
    assert route.snapshot_version == current_version
    assert route.capabilities == {}
    assert route.effective_runtime_settings["max_output_tokens"].value == 4096
    assert route.effective_runtime_settings["max_output_tokens"].source == "studio_default"


def test_snapshot_version_mismatch_ignores_stale_capability_blocking_lint() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role
    from graph_agent_gateway.registry.schema import CapabilityValue

    snapshot, _current_version = _snapshot_with_stale_provider_route(
        capabilities={
            "max_output_tokens": CapabilityValue(
                value={"max": 1000},
                source="manual",
            ),
        },
        route_runtime_settings={"max_output_tokens": 2000},
    )

    resolved = resolve_role(snapshot, "graph_agent")

    route = resolved.routes[0]
    assert route.capabilities == {}
    assert route.effective_runtime_settings["max_output_tokens"].value == 2000
    assert route.effective_runtime_settings["max_output_tokens"].source == "route_setting"
    assert [
        item
        for item in resolved.lint_results
        if item.blocking and item.capability == "max_output_tokens"
    ] == []
    assert resolved.skipped_diagnostics == []


def test_resolved_role_accepts_structured_skipped_diagnostics() -> None:
    from graph_agent_gateway.registry.schema import ResolvedRole

    resolved = ResolvedRole(
        role_name="graph_agent",
        skipped_diagnostics=[
            {
                "route_id": "missing:model",
                "reason_code": "route_missing",
                "message": "route is not configured: missing:model",
                "from_override": False,
            }
        ],
    )

    skipped = resolved.skipped_diagnostics[0]
    assert skipped.route_id == "missing:model"
    assert skipped.reason_code == "route_missing"
    assert skipped.message == "route is not configured: missing:model"
    assert skipped.from_override is False


def test_fallback_chain_skips_each_unusable_reason_and_keeps_later_route() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role
    from graph_agent_gateway.registry.schema import (
        CapabilityValue,
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
        VerifiedProfile,
    )

    def endpoint(endpoint_id: str, *, api_key: str | None = "secret") -> ProviderEndpoint:
        return ProviderEndpoint(
            endpoint_id=endpoint_id,
            protocol="openai_compatible",
            base_url=f"https://{endpoint_id}.example/v1",
            api_key=SecretStr(api_key) if api_key is not None else None,
        )

    def route(
        endpoint_id: str,
        route_slug: str,
        *,
        status: str = "verified",
        capabilities: dict[str, CapabilityValue] | None = None,
        verified_profiles: list[VerifiedProfile] | None = None,
    ) -> ProviderRoute:
        return ProviderRoute(
            route_id=f"{endpoint_id}:{route_slug}",
            endpoint_id=endpoint_id,
            route_slug=route_slug,
            provider_model_id=route_slug,
            canonical_id=route_slug,
            status=status,
            capabilities=capabilities or {},
            verified_profiles=verified_profiles or [],
        )

    thinking_capability = CapabilityValue(value=True, source="manual")
    snapshot = RegistrySnapshot(
        provider_endpoints={
            "disabled": endpoint("disabled"),
            "no-credential": endpoint("no-credential", api_key=None),
            "profile": endpoint("profile"),
            "lint": endpoint("lint"),
            "good": endpoint("good"),
        },
        provider_routes={
            "disabled:model": route("disabled", "model", status="failed"),
            "ghost:model": route("ghost", "model"),
            "no-credential:model": route("no-credential", "model"),
            "profile:model": route(
                "profile",
                "model",
                capabilities={"thinking_protocol": thinking_capability},
                verified_profiles=[
                    VerifiedProfile(
                        profile_id="text",
                        capability="text_chat",
                        method_id="openai_chat_completions",
                        request_mapper_id="openai_chat_text",
                        default=True,
                    )
                ],
            ),
            "lint:model": route("lint", "model"),
            "good:model": route(
                "good",
                "model",
                capabilities={"thinking_protocol": thinking_capability},
            ),
        },
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(route_id="missing:model"),
                    RoleRouteEntry(route_id="disabled:model"),
                    RoleRouteEntry(route_id="ghost:model"),
                    RoleRouteEntry(route_id="no-credential:model"),
                    RoleRouteEntry(
                        route_id="profile:model",
                        runtime_settings={"reasoning": {"enabled": True}},
                    ),
                    RoleRouteEntry(route_id="lint:model"),
                    RoleRouteEntry(route_id="good:model"),
                ],
                lint_requirements={"thinking": "error"},
            )
        },
    )

    resolved = resolve_role(snapshot, "graph_agent")

    assert [route.route_id for route in resolved.routes] == ["good:model"]
    diagnostics = {item.route_id: item for item in resolved.skipped_diagnostics}
    assert {route_id: item.reason_code for route_id, item in diagnostics.items()} == {
        "missing:model": "route_missing",
        "disabled:model": "route_not_executable",
        "ghost:model": "endpoint_missing",
        "no-credential:model": "credential_missing",
        "profile:model": "profile_unavailable",
        "lint:model": "lint_blocked",
    }
    assert all(item.from_override is False for item in diagnostics.values())
    assert all(item.message for item in diagnostics.values())
    assert {
        item.route_id
        for item in resolved.lint_results
        if item.blocking and item.capability == "thinking"
    } == {"lint:model"}


def test_resolve_role_raises_registry_error_with_skipped_summary_when_all_routes_skip() -> None:
    from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role
    from graph_agent_gateway.registry.schema import (
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "failed": ProviderEndpoint(
                endpoint_id="failed",
                protocol="openai_compatible",
                base_url="https://failed.example/v1",
                api_key=SecretStr("secret"),
            ),
        },
        provider_routes={
            "failed:model": ProviderRoute(
                route_id="failed:model",
                endpoint_id="failed",
                route_slug="model",
                provider_model_id="model",
                canonical_id="model",
                status="failed",
            )
        },
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(route_id="missing:model"),
                    RoleRouteEntry(route_id="failed:model"),
                ],
            )
        },
    )

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolve_role(snapshot, "graph_agent")

    message = str(exc_info.value)
    assert "skipped" in message.lower()
    assert "missing:model" in message
    assert "route_missing" in message
    assert "failed:model" in message
    assert "route_not_executable" in message


def test_resolve_role_rejects_empty_fallback_chain_in_registry_layer() -> None:
    from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role
    from graph_agent_gateway.registry.schema import RegistrySnapshot, RoleEntry

    snapshot = RegistrySnapshot(roles={"graph_agent": RoleEntry(fallback_chain=[])})

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolve_role(snapshot, "graph_agent")

    assert "empty" in str(exc_info.value).lower() or "no executable" in str(exc_info.value).lower()


def test_route_override_bad_route_fails_fast_without_fallback_skip() -> None:
    from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role
    from graph_agent_gateway.registry.schema import (
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "failed": ProviderEndpoint(
                endpoint_id="failed",
                protocol="openai_compatible",
                base_url="https://failed.example/v1",
                api_key=SecretStr("secret"),
            ),
            "good": ProviderEndpoint(
                endpoint_id="good",
                protocol="openai_compatible",
                base_url="https://good.example/v1",
                api_key=SecretStr("secret"),
            ),
        },
        provider_routes={
            "failed:model": ProviderRoute(
                route_id="failed:model",
                endpoint_id="failed",
                route_slug="model",
                provider_model_id="model",
                canonical_id="model",
                status="failed",
            ),
            "good:model": ProviderRoute(
                route_id="good:model",
                endpoint_id="good",
                route_slug="model",
                provider_model_id="model",
                canonical_id="model",
                status="verified",
            ),
        },
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="good:model")],
            )
        },
    )

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolve_role(snapshot, "graph_agent", route_override="failed:model")

    message = str(exc_info.value)
    assert "failed:model" in message
    assert "good:model" not in message
    assert "skipped" not in message.lower()


def test_route_override_lint_blocked_route_fails_fast() -> None:
    from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role
    from graph_agent_gateway.registry.schema import (
        CapabilityValue,
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "lint": ProviderEndpoint(
                endpoint_id="lint",
                protocol="openai_compatible",
                base_url="https://lint.example/v1",
                api_key=SecretStr("secret"),
            ),
            "good": ProviderEndpoint(
                endpoint_id="good",
                protocol="openai_compatible",
                base_url="https://good.example/v1",
                api_key=SecretStr("secret"),
            ),
        },
        provider_routes={
            "lint:model": ProviderRoute(
                route_id="lint:model",
                endpoint_id="lint",
                route_slug="model",
                provider_model_id="model",
                canonical_id="model",
                status="verified",
            ),
            "good:model": ProviderRoute(
                route_id="good:model",
                endpoint_id="good",
                route_slug="model",
                provider_model_id="model",
                canonical_id="model",
                status="verified",
                capabilities={
                    "thinking_protocol": CapabilityValue(value=True, source="manual"),
                },
            ),
        },
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="good:model")],
                lint_requirements={"thinking": "error"},
            )
        },
    )

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolve_role(snapshot, "graph_agent", route_override="lint:model")

    assert "lint:model" in str(exc_info.value)
    assert "lint" in str(exc_info.value).lower()


def test_resolver_rejects_missing_or_disabled_routes_without_dynamic_matching() -> None:
    from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role
    from graph_agent_gateway.registry.schema import RoleEntry, RoleRouteEntry

    snapshot = _snapshot()
    snapshot.roles["broken"] = RoleEntry(
        fallback_chain=[RoleRouteEntry(route_id="anthropic-official:not-real")],
    )

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolve_role(snapshot, "broken")

    assert "anthropic-official:not-real" in str(exc_info.value)


def test_route_override_must_be_exact_route_id() -> None:
    from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role

    resolved = resolve_role(
        _snapshot(),
        "graph_agent",
        route_override="openrouter-prod:anthropic.claude",
    )

    assert [route.route_id for route in resolved.routes] == ["openrouter-prod:anthropic.claude"]

    with pytest.raises(RegistryResolutionError):
        resolve_role(_snapshot(), "graph_agent", route_override="claude")


def test_resolver_accepts_credential_ref_only_for_future_no_secret_snapshots() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role
    from graph_agent_gateway.registry.schema import (
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.com",
                credential_ref="cred:anthropic-prod",
            ),
        },
        provider_routes={
            "anthropic-official:claude": ProviderRoute(
                route_id="anthropic-official:claude",
                endpoint_id="anthropic-official",
                route_slug="claude",
                provider_model_id="claude",
                canonical_id="claude",
                status="verified",
            ),
        },
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="anthropic-official:claude")],
            )
        },
    )

    resolved = resolve_role(snapshot, "graph_agent")

    assert resolved.routes[0].credential_ref == "cred:anthropic-prod"
    assert "api_key" not in resolved.routes[0].model_dump(mode="json")
