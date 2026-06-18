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


def _truth_credentials_payload() -> dict[str, object]:
    return {
        "schema_version": 4,
        "provider_endpoints": {
            "openai": {
                "endpoint_id": "openai",
                "protocol": "openai_compatible",
                "base_url": "https://api.openai.example/v1",
                "api_key": "truth-secret",
                "status": "verified",
            }
        },
        "provider_routes": {
            "openai:gpt-5": {
                "route_id": "openai:gpt-5",
                "endpoint_id": "openai",
                "route_slug": "gpt-5",
                "provider_model_id": "gpt-5",
                "canonical_id": "gpt-5",
                "status": "verified",
            }
        },
        "runtime_policy": {},
    }


def _truth_roles_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "roles": {
            "graph_agent": {
                "fallback_chain": [
                    {
                        "route_id": "openai:gpt-5",
                    }
                ],
            }
        },
    }


def _snapshot_credentials() -> LLMCredentialsFile:
    return LLMCredentialsFile(
        provider_endpoints={
            "anthropic": ProviderEndpoint(
                endpoint_id="anthropic",
                display_name="Anthropic",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.example",
                api_key="snapshot-secret",
                status="verified",
            )
        },
        provider_routes={
            "anthropic:claude-sonnet": ProviderRoute(
                route_id="anthropic:claude-sonnet",
                endpoint_id="anthropic",
                route_slug="claude-sonnet",
                provider_model_id="claude-sonnet",
                canonical_id="claude-sonnet",
                display_name="Claude Sonnet",
                status="verified",
            )
        },
    )


def _snapshot_roles() -> RolesData:
    return RolesData(
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(route_id="anthropic:claude-sonnet"),
                ],
            )
        }
    )


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


def test_gateway_resolver_does_not_overwrite_config_truth_without_etag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.delenv("STUDIO_LLM_CREDENTIALS_PATH", raising=False)
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    config_store = LocalGatewayConfigStore(root=settings_dir)
    truth_credentials = {
        "schema_version": 4,
        "provider_endpoints": {
            "openai": {
                "endpoint_id": "openai",
                "protocol": "openai_compatible",
                "base_url": "https://api.openai.example/v1",
                "api_key": "truth-secret",
                "status": "verified",
            }
        },
        "provider_routes": {
            "openai:gpt-5": {
                "route_id": "openai:gpt-5",
                "endpoint_id": "openai",
                "route_slug": "gpt-5",
                "provider_model_id": "gpt-5",
                "canonical_id": "gpt-5",
                "status": "verified",
            }
        },
        "runtime_policy": {},
    }
    truth_roles = {
        "schema_version": 2,
        "roles": {
            "graph_agent": {
                "fallback_chain": [
                    {
                        "route_id": "openai:gpt-5",
                    }
                ],
            }
        },
    }
    credentials_etag = config_store.put_config(
        config.DEFAULT_USER_ID,
        "credentials",
        truth_credentials,
        if_none_match="*",
    )
    roles_etag = config_store.put_config(
        config.DEFAULT_USER_ID,
        "roles",
        truth_roles,
        if_none_match="*",
    )

    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "anthropic": ProviderEndpoint(
                    endpoint_id="anthropic",
                    display_name="Anthropic",
                    protocol="anthropic_compatible",
                    base_url="https://api.anthropic.example",
                    api_key="snapshot-secret",
                    status="verified",
                )
            },
            provider_routes={
                "anthropic:claude-sonnet": ProviderRoute(
                    route_id="anthropic:claude-sonnet",
                    endpoint_id="anthropic",
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
                        RoleRouteEntry(route_id="anthropic:claude-sonnet")
                    ],
                )
            }
        ),
        known_route_ids={"anthropic:claude-sonnet"},
    )

    resolver = build_gateway_model_resolver(roles_path)

    credentials_record = resolver.config_store.get_config(config.DEFAULT_USER_ID, "credentials")
    roles_record = resolver.config_store.get_config(config.DEFAULT_USER_ID, "roles")
    assert credentials_record.etag == credentials_etag
    assert roles_record.etag == roles_etag
    assert credentials_record.value == truth_credentials
    assert roles_record.value == truth_roles
    assert set(resolver.registry_snapshot.provider_routes) == {"openai:gpt-5"}


def test_gateway_route_runtime_uses_truth_store_for_routes_and_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore
    from app.core.backends import clear_backend_caches

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.setenv("STUDIO_GATEWAY_TRANSPORT", "in_process")
    clear_backend_caches()
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    config_store = LocalGatewayConfigStore(root=settings_dir)
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "credentials",
        _truth_credentials_payload(),
        if_none_match="*",
    )
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "roles",
        _truth_roles_payload(),
        if_none_match="*",
    )
    save_credentials(_snapshot_credentials())
    save_roles_file(
        roles_path,
        _snapshot_roles(),
        known_route_ids={"anthropic:claude-sonnet"},
    )

    runtime = build_gateway_route_runtime("graph_agent", roles_path=roles_path)

    assert [route.route_id for route in runtime.routes] == ["openai:gpt-5"]
    truth_secret = runtime.credential_provider.get(runtime.routes[0].credential_ref)
    assert truth_secret.get_secret_value() == "truth-secret"
    assert runtime.credential_provider.get("endpoint:openai").get_secret_value() == "truth-secret"
    try:
        runtime.credential_provider.get("endpoint:anthropic")
    except KeyError:
        pass
    else:
        raise AssertionError("runtime credential_provider must not expose snapshot anthropic credentials")
    clear_backend_caches()


def test_gateway_resolver_and_runtime_ignore_malformed_snapshot_when_truth_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore
    from app.core.backends import clear_backend_caches

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.setenv("STUDIO_GATEWAY_TRANSPORT", "in_process")
    clear_backend_caches()
    llm_dir = settings_dir / "llm"
    roles_path = llm_dir / "llm_roles.yaml"
    llm_dir.mkdir(parents=True, exist_ok=True)
    (llm_dir / "llm_credentials.json").write_text('{"schema_version": 3, "providers": {}}', encoding="utf-8")
    roles_path.write_text("schema_version: 1\nmodels: {}\n", encoding="utf-8")

    config_store = LocalGatewayConfigStore(root=settings_dir)
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "credentials",
        _truth_credentials_payload(),
        if_none_match="*",
    )
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "roles",
        _truth_roles_payload(),
        if_none_match="*",
    )

    resolver = build_gateway_model_resolver(roles_path)
    runtime = build_gateway_route_runtime("graph_agent", roles_path=roles_path)

    assert set(resolver.registry_snapshot.provider_routes) == {"openai:gpt-5"}
    assert [route.route_id for route in runtime.routes] == ["openai:gpt-5"]
    assert runtime.credential_provider.get("endpoint:openai").get_secret_value() == "truth-secret"
    clear_backend_caches()


def test_engine_gateway_model_resolver_bridge_preserves_truth_store(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.core.adapters.engine import _private_build_gateway_model_resolver
    from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.delenv("STUDIO_LLM_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_ROLES_PATH", raising=False)
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    config_store = LocalGatewayConfigStore(root=settings_dir)
    credentials_etag = config_store.put_config(
        config.DEFAULT_USER_ID,
        "credentials",
        _truth_credentials_payload(),
        if_none_match="*",
    )
    roles_etag = config_store.put_config(
        config.DEFAULT_USER_ID,
        "roles",
        _truth_roles_payload(),
        if_none_match="*",
    )
    save_credentials(_snapshot_credentials())
    save_roles_file(
        roles_path,
        _snapshot_roles(),
        known_route_ids={"anthropic:claude-sonnet"},
    )

    resolver = _private_build_gateway_model_resolver()

    credentials_record = resolver.config_store.get_config(config.DEFAULT_USER_ID, "credentials")
    roles_record = resolver.config_store.get_config(config.DEFAULT_USER_ID, "roles")
    assert credentials_record.etag == credentials_etag
    assert roles_record.etag == roles_etag
    assert credentials_record.value == _truth_credentials_payload()
    assert roles_record.value == _truth_roles_payload()
    assert set(resolver.registry_snapshot.provider_routes) == {"openai:gpt-5"}
