"""Temporary role resolution for P8 model comparison."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr


def _snapshot():
    from graph_agent_gateway.registry.schema import (
        ModelBundle,
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    return RegistrySnapshot(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("openai-secret"),
            ),
            "anthropic": ProviderEndpoint(
                endpoint_id="anthropic",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.example",
                api_key=SecretStr("anthropic-secret"),
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
                        runtime_settings={"temperature": 0.2},
                    ),
                    RoleRouteEntry(route_id="anthropic:claude"),
                ],
            )
        },
        roles={
            "persisted_analysis": RoleEntry(
                bundle_id="analysis",
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="openai:gpt-5",
                        runtime_settings={"max_output_tokens": 2048},
                    )
                ],
            )
        },
    )


def _resolver_from_snapshot(snapshot: Any, *, store: Any | None = None) -> Any:
    from graph_agent_gateway.resolver import ModelResolver
    from graph_agent_gateway.storage_contracts import InMemoryConfigTruthStore

    payload = snapshot.model_dump(mode="json")
    config_store = store or InMemoryConfigTruthStore()
    user_id = "user-a"
    config_store.put_config(
        user_id,
        "credentials",
        {
            "schema_version": 4,
            "provider_endpoints": payload["provider_endpoints"],
            "provider_routes": payload["provider_routes"],
            "runtime_policy": payload["runtime_policy"],
        },
    )
    config_store.put_config(
        user_id,
        "roles",
        {
            "schema_version": 3,
            "model_bundles": payload["model_bundles"],
            "roles": payload["roles"],
        },
    )
    return ModelResolver(config_store=config_store, user_id=user_id)


def _runtime_payload(chain: Any) -> list[dict[str, Any]]:
    payload = []
    for route in chain.routes:
        dumped = route.model_dump(mode="json")
        dumped.pop("role_name")
        payload.append(dumped)
    return payload


def test_temporary_role_materializes_like_equivalent_persisted_role() -> None:
    from graph_agent_gateway.registry.schema import RoleEntry, RoleRouteEntry

    resolver = _resolver_from_snapshot(_snapshot())
    temporary_role = RoleEntry(
        bundle_id="analysis",
        fallback_chain=[
            RoleRouteEntry(
                route_id="openai:gpt-5",
                runtime_settings={"max_output_tokens": 2048},
            )
        ],
    )

    persisted = resolver.resolve_routes("persisted_analysis")
    temporary = resolver.resolve_temporary_role("temp_analysis", temporary_role)

    assert _runtime_payload(temporary) == _runtime_payload(persisted)


def test_temporary_role_resolution_does_not_write_config_truth() -> None:
    from graph_agent_gateway.registry.schema import RoleEntry
    from graph_agent_gateway.storage_contracts import InMemoryConfigTruthStore

    class RecordingConfigTruthStore(InMemoryConfigTruthStore):
        def __init__(self) -> None:
            super().__init__()
            self.put_calls: list[tuple[str, str, dict[str, Any]]] = []

        def put_config(
            self,
            user_id: str,
            key: str,
            value: dict[str, Any],
            *,
            if_match: str | None = None,
            if_none_match: str | None = None,
        ) -> str:
            self.put_calls.append((user_id, key, value))
            return super().put_config(
                user_id,
                key,
                value,
                if_match=if_match,
                if_none_match=if_none_match,
            )

    store = RecordingConfigTruthStore()
    resolver = _resolver_from_snapshot(_snapshot(), store=store)
    store.put_calls.clear()

    resolved = resolver.resolve_temporary_role(
        "temp_analysis",
        RoleEntry(bundle_id="analysis"),
    )

    assert [route.route_id for route in resolved.routes] == [
        "openai:gpt-5",
        "anthropic:claude",
    ]
    assert store.put_calls == []


def test_resolver_resolves_multiple_temporary_roles_for_model_comparison() -> None:
    from graph_agent_gateway.registry.schema import RoleEntry, RoleRouteEntry

    resolver = _resolver_from_snapshot(_snapshot())

    resolved = resolver.resolve_temporary_roles(
        {
            "compare_openai": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="openai:gpt-5")]
            ),
            "compare_bundle": RoleEntry(bundle_id="analysis"),
        }
    )

    assert list(resolved) == ["compare_openai", "compare_bundle"]
    assert [route.route_id for route in resolved["compare_openai"].routes] == [
        "openai:gpt-5"
    ]
    assert [route.route_id for route in resolved["compare_bundle"].routes] == [
        "openai:gpt-5",
        "anthropic:claude",
    ]
