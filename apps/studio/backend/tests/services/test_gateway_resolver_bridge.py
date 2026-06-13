from __future__ import annotations

from pathlib import Path

from app.core import config
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
    RolesData,
)
from app.services import gateway_resolver as gateway_resolver_module
from app.services.gateway_resolver import build_gateway_model_resolver
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import save_roles_file


class _Step4OnlyModelResolver:
    def __init__(self, **kwargs):
        if "registry_snapshot" in kwargs:
            raise AssertionError(
                "Studio must not build Gateway ModelResolver with registry_snapshot; "
                "pass config_store and user_id instead."
            )
        self.config_store = kwargs["config_store"]
        self.user_id = kwargs["user_id"]


def test_gateway_resolver_bridge_uses_config_truth_store_instead_of_registry_snapshot(
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
    monkeypatch.setattr(gateway_resolver_module, "ModelResolver", _Step4OnlyModelResolver)

    resolver = build_gateway_model_resolver(roles_path)

    assert resolver.user_id == config.DEFAULT_USER_ID
    credentials_record = resolver.config_store.get_config(config.DEFAULT_USER_ID, "credentials")
    roles_record = resolver.config_store.get_config(config.DEFAULT_USER_ID, "roles")
    assert set(credentials_record.value["provider_endpoints"]) == {"anthropic-official"}
    assert roles_record.value["roles"]["graph_agent"]["fallback_chain"][0]["route_id"] == (
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
    monkeypatch.setattr(gateway_resolver_module, "ModelResolver", _Step4OnlyModelResolver)

    resolver = build_gateway_model_resolver(roles_path)

    assert resolver.user_id == config.DEFAULT_USER_ID
    credentials_record = resolver.config_store.get_config(config.DEFAULT_USER_ID, "credentials")
    roles_record = resolver.config_store.get_config(config.DEFAULT_USER_ID, "roles")
    assert credentials_record.value["provider_endpoints"] == {}
    assert credentials_record.value["provider_routes"] == {}
    assert roles_record.value["roles"] == {}
