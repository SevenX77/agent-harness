"""Deterministic registry resolver tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr


def _snapshot():
    from graph_agent_gateway.registry.schema import (
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
                display_name="Anthropic",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.com",
                api_key=SecretStr("anthropic-secret"),
            ),
            "openrouter-prod": ProviderEndpoint(
                endpoint_id="openrouter-prod",
                display_name="OpenRouter",
                protocol="openai_compatible",
                base_url="https://openrouter.ai/api/v1",
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
                display_name="Claude",
                status="verified",
            ),
            "openrouter-prod:anthropic.claude": ProviderRoute(
                route_id="openrouter-prod:anthropic.claude",
                endpoint_id="openrouter-prod",
                route_slug="anthropic.claude",
                provider_model_id="anthropic/claude",
                canonical_id="claude",
                display_name="Claude via OpenRouter",
                status="unverified_manual",
            ),
        },
        roles={
            "graph_agent": RoleEntry(
                system_prompt_prefix="prefix",
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="anthropic-official:claude",
                        temperature=0.2,
                        max_output_tokens=8192,
                    ),
                    RoleRouteEntry(route_id="openrouter-prod:anthropic.claude"),
                ],
            )
        },
    )


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
    assert resolved.routes[0].temperature == 0.2
    assert resolved.routes[0].max_output_tokens == 8192
    assert resolved.runtime_policy.provider_down_ttl_seconds == 60


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
