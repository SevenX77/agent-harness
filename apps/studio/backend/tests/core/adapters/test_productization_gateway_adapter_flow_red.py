from __future__ import annotations

from app.core import config


def _gateway_credentials(route_slug: str) -> dict[str, object]:
    route_id = f"openai:{route_slug}"
    return {
        "schema_version": 4,
        "provider_endpoints": {
            "openai": {
                "endpoint_id": "openai",
                "protocol": "openai_compatible",
                "base_url": "https://api.openai.example/v1",
                "api_key": "secret",
                "status": "verified",
            }
        },
        "provider_routes": {
            route_id: {
                "route_id": route_id,
                "endpoint_id": "openai",
                "route_slug": route_slug,
                "provider_model_id": route_slug,
                "canonical_id": route_slug,
                "status": "verified",
            }
        },
        "runtime_policy": {},
    }


def _gateway_roles(route_slug: str) -> dict[str, object]:
    return {
        "schema_version": 2,
        "roles": {
            "graph_agent": {
                "fallback_chain": [
                    {
                        "route_id": f"openai:{route_slug}",
                    }
                ],
            }
        },
    }


def test_gateway_adapter_resolve_routes_does_not_seed_temp_truth_store_without_create_guard() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import (
        LLMCredentialsFile,
        ProviderEndpoint,
        ProviderRoute,
        RoleEntry,
        RoleRouteEntry,
        RolesData,
    )
    from graph_agent_gateway.registry import InMemoryConfigTruthStore

    store = InMemoryConfigTruthStore()
    store.put_config(
        config.DEFAULT_USER_ID,
        "credentials",
        _gateway_credentials("truth-model"),
        if_none_match="*",
    )
    store.put_config(
        config.DEFAULT_USER_ID,
        "roles",
        _gateway_roles("truth-model"),
        if_none_match="*",
    )

    snapshot_credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key="snapshot-secret",
                status="verified",
            )
        },
        provider_routes={
            "openai:snapshot-model": ProviderRoute(
                route_id="openai:snapshot-model",
                endpoint_id="openai",
                route_slug="snapshot-model",
                provider_model_id="snapshot-model",
                canonical_id="snapshot-model",
                display_name="Snapshot Model",
                status="verified",
            )
        },
    )
    snapshot_roles = RolesData(
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(route_id="openai:snapshot-model"),
                ]
            )
        }
    )

    chain = GatewayAdapter(transport="in_process").resolve_routes(
        {
            "role_name": "graph_agent",
            "credentials": snapshot_credentials,
            "roles": snapshot_roles,
            "config_store": store,
            "user_id": config.DEFAULT_USER_ID,
        }
    )

    assert [route.route_id for route in chain.routes] == ["openai:truth-model"]
