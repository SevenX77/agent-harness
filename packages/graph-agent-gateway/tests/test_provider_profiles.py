"""Provider profile init-kwargs registry contract tests."""

from __future__ import annotations

from typing import Any


def _route(*, endpoint_id: str, provider_model_id: str):
    from graph_agent_gateway.registry.schema import ResolvedRoute

    route_slug = provider_model_id.lower().replace("/", ".")
    return ResolvedRoute(
        role_name="graph_agent",
        route_id=f"{endpoint_id}:{route_slug}",
        endpoint_id=endpoint_id,
        protocol="openai_compatible",
        base_url="https://provider.example/v1",
        credential_ref=f"endpoint:{endpoint_id}",
        credential_fingerprint="fingerprint-a",
        provider_model_id=provider_model_id,
        canonical_id=provider_model_id,
    )


def test_provider_profile_merge_order_exact_factory_and_caller_wins() -> None:
    from graph_agent_gateway.provider_profiles import (
        ProviderProfile,
        apply_provider_profile,
        register_provider_profile,
    )

    route = _route(
        endpoint_id="profile-provider",
        provider_model_id="claude-sonnet-4-6",
    )
    pre_init_calls: list[str] = []

    def pre_init(route_arg: Any) -> dict[str, object]:
        pre_init_calls.append(route_arg.route_id)
        return {
            "temperature": 0.05,
            "pre_init_route_id": route_arg.route_id,
        }

    def dynamic_kwargs(route_arg: Any) -> dict[str, object]:
        return {
            "factory_model_id": route_arg.provider_model_id,
            "temperature": 0.4,
        }

    register_provider_profile(
        "profile-provider",
        ProviderProfile(
            init_kwargs={
                "profile_scope": "provider",
                "stream_usage": True,
                "temperature": 0.1,
            },
            pre_init=pre_init,
        ),
    )
    register_provider_profile(
        "profile-provider:claude-sonnet-4-6",
        ProviderProfile(
            init_kwargs={
                "profile_scope": "exact",
                "default_headers": {"x-model-profile": "claude-sonnet-4-6"},
            },
            init_kwargs_factory=dynamic_kwargs,
        ),
    )

    merged = apply_provider_profile(
        "profile-provider:claude-sonnet-4-6",
        route=route,
        temperature=0.9,
        caller_only="yes",
    )

    assert pre_init_calls == ["profile-provider:claude-sonnet-4-6"]
    assert merged == {
        "temperature": 0.9,
        "pre_init_route_id": "profile-provider:claude-sonnet-4-6",
        "profile_scope": "exact",
        "stream_usage": True,
        "default_headers": {"x-model-profile": "claude-sonnet-4-6"},
        "factory_model_id": "claude-sonnet-4-6",
        "caller_only": "yes",
    }


def test_provider_profile_registration_is_additive() -> None:
    from graph_agent_gateway.provider_profiles import (
        ProviderProfile,
        apply_provider_profile,
        register_provider_profile,
    )

    register_provider_profile(
        "profile-additive",
        ProviderProfile(init_kwargs={"stream_usage": True}),
    )
    register_provider_profile(
        "profile-additive",
        ProviderProfile(init_kwargs={"default_headers": {"x-gateway": "on"}}),
    )

    assert apply_provider_profile("profile-additive") == {
        "stream_usage": True,
        "default_headers": {"x-gateway": "on"},
    }
