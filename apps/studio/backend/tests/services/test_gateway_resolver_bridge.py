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
from app.services.gateway_resolver import build_gateway_model_resolver, build_gateway_route_runtime
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


def _save_single_route_truth(
    roles_path: Path,
    *,
    route_id: str,
    endpoint_id: str = "ep",
    api_key: str = "secret",
) -> None:
    """Write the on-disk single config truth (A): one endpoint + one route + a
    ``graph_agent`` role pointing at it, via the real ``save_credentials`` /
    ``save_roles_file`` write path. Calling it again fully replaces A (simulates a
    Settings edit)."""
    slug = route_id.split(":")[-1]
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                endpoint_id: ProviderEndpoint(
                    endpoint_id=endpoint_id,
                    display_name=endpoint_id,
                    protocol="anthropic_compatible",
                    base_url=f"https://{endpoint_id}.example",
                    api_key=api_key,
                    status="verified",
                )
            },
            provider_routes={
                route_id: ProviderRoute(
                    route_id=route_id,
                    endpoint_id=endpoint_id,
                    route_slug=slug,
                    provider_model_id=slug,
                    canonical_id=slug,
                    display_name=route_id,
                    status="verified",
                )
            },
        )
    )
    save_roles_file(
        roles_path,
        RolesData(
            roles={"graph_agent": RoleEntry(fallback_chain=[RoleRouteEntry(route_id=route_id)])}
        ),
        known_route_ids={route_id},
    )


# ── The resolver consumes the on-disk config truth via a ConfigTruthStore ──


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


# ── 底座一 regression: every resolver build reads the on-disk truth FRESH, so an
#    edit to A is visible on the next build with no persistent snapshot to go stale ──


def test_model_resolver_reflects_truth_edits_with_no_stale_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.delenv("STUDIO_LLM_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_ROLES_PATH", raising=False)
    roles_path = settings_dir / "llm" / "llm_roles.yaml"

    _save_single_route_truth(roles_path, route_id="ep:v1")
    first = build_gateway_model_resolver(roles_path)
    assert set(first.registry_snapshot.provider_routes) == {"ep:v1"}

    # Edit the on-disk truth; the next build must reflect it (no stale snapshot).
    _save_single_route_truth(roles_path, route_id="ep:v2")
    second = build_gateway_model_resolver(roles_path)
    assert set(second.registry_snapshot.provider_routes) == {"ep:v2"}


def test_route_runtime_reflects_truth_edits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.core.backends import clear_backend_caches

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.setenv("STUDIO_GATEWAY_TRANSPORT", "in_process")
    monkeypatch.delenv("STUDIO_LLM_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_ROLES_PATH", raising=False)
    clear_backend_caches()
    roles_path = settings_dir / "llm" / "llm_roles.yaml"

    _save_single_route_truth(roles_path, route_id="ep:v1")
    first = build_gateway_route_runtime("graph_agent", roles_path=roles_path)
    assert [route.route_id for route in first.routes] == ["ep:v1"]

    _save_single_route_truth(roles_path, route_id="ep:v2")
    second = build_gateway_route_runtime("graph_agent", roles_path=roles_path)
    assert [route.route_id for route in second.routes] == ["ep:v2"]
    clear_backend_caches()


def test_engine_private_resolver_reads_live_truth(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.core.adapters.engine import _private_build_gateway_model_resolver

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.delenv("STUDIO_LLM_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_ROLES_PATH", raising=False)
    roles_path = settings_dir / "llm" / "llm_roles.yaml"

    _save_single_route_truth(roles_path, route_id="ep:v1")
    first = _private_build_gateway_model_resolver()
    assert set(first.registry_snapshot.provider_routes) == {"ep:v1"}

    _save_single_route_truth(roles_path, route_id="ep:v2")
    second = _private_build_gateway_model_resolver()
    assert set(second.registry_snapshot.provider_routes) == {"ep:v2"}
