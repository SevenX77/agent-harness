"""R-F1 — gateway snapshot strong-refresh tests.

Distinct from ``test_gateway_resolver_bridge.py`` which tests the read-side
build helpers (ensure-only, do not overwrite truth store). This file tests
the write-side ``_refresh_gateway_config_store`` /
``refresh_default_gateway_config_store`` flow that PUT/DELETE roles
endpoints invoke to keep the in-process gateway snapshot consistent with
the yaml on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
    RolesData,
)
from app.services.gateway_resolver import (
    _refresh_gateway_config_store,
    refresh_default_gateway_config_store,
)
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import save_roles_file


def _seed_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    role_id: str = "copilot_custom_test",
    route_id: str = "anthropic-official:claude-3-5-haiku",
) -> tuple[Path, Path]:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.delenv("STUDIO_LLM_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_ROLES_PATH", raising=False)
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
                route_id: ProviderRoute(
                    route_id=route_id,
                    endpoint_id="anthropic-official",
                    route_slug="claude-3-5-haiku",
                    provider_model_id="claude-3-5-haiku",
                    canonical_id="claude-3-5-haiku",
                    display_name="Claude 3.5 Haiku",
                    status="verified",
                )
            },
        )
    )
    save_roles_file(
        roles_path,
        RolesData(
            roles={
                role_id: RoleEntry(
                    fallback_chain=[RoleRouteEntry(route_id=route_id)],
                )
            }
        ),
        known_route_ids={route_id},
    )
    return settings_dir, roles_path


def test_refresh_seeds_snapshot_when_config_store_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_dir, roles_path = _seed_disk(tmp_path, monkeypatch)
    config_store = LocalGatewayConfigStore(root=settings_dir)

    _refresh_gateway_config_store(
        config_store,
        config.DEFAULT_USER_ID,
        roles_path,
    )

    roles_record = config_store.get_config(config.DEFAULT_USER_ID, "roles")
    creds_record = config_store.get_config(config.DEFAULT_USER_ID, "credentials")
    assert "copilot_custom_test" in roles_record.value["roles"]
    assert set(creds_record.value["provider_routes"]) == {
        "anthropic-official:claude-3-5-haiku"
    }


def test_refresh_overwrites_stale_snapshot_with_disk_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-F1.1 — after a PUT roles writes the yaml, refresh must rewrite the
    in-process snapshot with if_match so the resolver no longer sees stale
    roles. This is the regression that makes ``test-sdk`` fail with
    ``no_available_route``.
    """
    settings_dir, roles_path = _seed_disk(tmp_path, monkeypatch)
    config_store = LocalGatewayConfigStore(root=settings_dir)

    # Pre-seed the snapshot with an older role set that does NOT contain
    # copilot_custom_test (simulating a snapshot taken before the user
    # added a new copilot role).
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "roles",
        {"schema_version": 2, "roles": {"old_role": {"fallback_chain": []}}},
        if_none_match="*",
    )
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "credentials",
        {"schema_version": 4, "provider_endpoints": {}, "provider_routes": {}},
        if_none_match="*",
    )

    _refresh_gateway_config_store(
        config_store,
        config.DEFAULT_USER_ID,
        roles_path,
    )

    roles_record = config_store.get_config(config.DEFAULT_USER_ID, "roles")
    creds_record = config_store.get_config(config.DEFAULT_USER_ID, "credentials")
    # The snapshot must now reflect what the disk yaml contains.
    assert "copilot_custom_test" in roles_record.value["roles"]
    assert "old_role" not in roles_record.value["roles"]
    assert "anthropic-official:claude-3-5-haiku" in creds_record.value[
        "provider_routes"
    ]


def test_refresh_default_helper_uses_app_settings_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_dir, roles_path = _seed_disk(tmp_path, monkeypatch)

    refresh_default_gateway_config_store(roles_path)

    config_store = LocalGatewayConfigStore(root=settings_dir)
    roles_record = config_store.get_config(config.DEFAULT_USER_ID, "roles")
    assert "copilot_custom_test" in roles_record.value["roles"]
