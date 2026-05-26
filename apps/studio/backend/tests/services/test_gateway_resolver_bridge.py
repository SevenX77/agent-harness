from __future__ import annotations

from pathlib import Path

from app.core import config
from app.models.llm_config import LLMCredentialsFile, RolesData
from app.services.gateway_resolver import build_gateway_model_resolver
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import save_roles_file
from graph_agent_gateway.registry.schema import (
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
)


def test_gateway_resolver_bridge_builds_snapshot_without_env_patch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "anthropic-official": ProviderEndpoint(
                    endpoint_id="anthropic-official",
                    display_name="Anthropic",
                    protocol="anthropic_compatible",
                    base_url="https://api.anthropic.example",
                    api_key="secret",
                )
            },
            provider_routes={
                "anthropic-official:claude-sonnet": ProviderRoute(
                    route_id="anthropic-official:claude-sonnet",
                    endpoint_id="anthropic-official",
                    route_slug="claude-sonnet",
                    provider_model_id="claude-sonnet",
                    canonical_id="claude-sonnet",
                    display_name="Claude Sonnet",
                    status="verified",
                )
            },
        )
    )
    save_roles_file(
        roles_path,
        RolesData(
            roles={
                "graph_agent": RoleEntry(
                    fallback_chain=[
                        RoleRouteEntry(route_id="anthropic-official:claude-sonnet")
                    ],
                )
            }
        ),
        known_route_ids={"anthropic-official:claude-sonnet"},
    )

    resolver = build_gateway_model_resolver(roles_path)

    snapshot = resolver.registry_snapshot
    assert set(snapshot.provider_endpoints) == {"anthropic-official"}
    assert snapshot.roles["graph_agent"].fallback_chain[0].route_id == (
        "anthropic-official:claude-sonnet"
    )


def test_gateway_resolver_bridge_allows_missing_credentials_first_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    save_roles_file(roles_path, RolesData())

    resolver = build_gateway_model_resolver(roles_path)

    assert resolver.registry_snapshot.provider_endpoints == {}
    assert resolver.registry_snapshot.provider_routes == {}
