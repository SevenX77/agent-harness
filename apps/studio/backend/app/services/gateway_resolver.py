"""Studio wiring for the graph-agent gateway model resolver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.adapters.gateway import (
    CredentialProviderProtocol,
    ModelResolver,
    ResolvedRoute,
    _filter_gateway_credentials,
    _filter_gateway_roles,
    _put_config_if_absent,
)
from app.core.adapters.transport_factory import build_gateway_adapter
from app.models.llm_config import LLMCredentialsFile, RolesData
from app.services.llm_credentials import load_credentials
from app.services.llm_roles import load_roles_file
from app.services.llm_roles import roles_path as default_roles_path


@dataclass(frozen=True)
class GatewayRouteRuntime:
    routes: list[ResolvedRoute]
    credential_provider: CredentialProviderProtocol
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None


def build_gateway_model_resolver(roles_path: Path | None = None) -> ModelResolver:
    """Build a fresh resolver from Studio-owned v4/v2 registry data."""
    from app.core import config
    from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore

    active_roles_path = roles_path or default_roles_path()
    config_store = LocalGatewayConfigStore(root=config.APP_SETTINGS_DIR)
    _ensure_gateway_config_store(config_store, config.DEFAULT_USER_ID, active_roles_path)
    return ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)


def build_gateway_route_runtime(
    role_name: str,
    *,
    route_override: str | None = None,
    roles_path: Path | None = None,
) -> GatewayRouteRuntime:
    """Resolve runtime routes through the configured GatewayAdapter."""
    from app.core import config
    from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore

    active_roles_path = roles_path or default_roles_path()
    adapter = build_gateway_adapter()
    config_store = LocalGatewayConfigStore(root=config.APP_SETTINGS_DIR)
    credentials_payload, roles_payload = _ensure_gateway_config_store(
        config_store,
        config.DEFAULT_USER_ID,
        active_roles_path,
    )
    payload: dict[str, Any] = {
        "role_name": role_name,
        "route_override": route_override,
        "credentials": credentials_payload,
        "roles": roles_payload,
    }
    if adapter.transport == "in_process":
        payload["config_store"] = config_store
        payload["user_id"] = config.DEFAULT_USER_ID
        resolver = ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)
        resolved = resolver.resolve_routes(role_name, route_override=route_override)
        return GatewayRouteRuntime(
            routes=list(resolved.routes),
            credential_provider=resolver.credential_provider,
            error_code=resolved.error_code,
            error_payload=resolved.error_payload,
        )
    resolved = adapter.resolve_routes(payload)
    resolver = ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)
    return GatewayRouteRuntime(
        routes=list(resolved.routes),
        credential_provider=resolver.credential_provider,
        error_code=resolved.error_code,
        error_payload=resolved.error_payload,
    )


def _bootstrap_gateway_config_store(
    config_store: Any,
    user_id: str,
    credentials: LLMCredentialsFile,
    roles: RolesData,
) -> None:
    from app.services.llm_credentials import _credentials_payload_for_storage

    _put_config_if_absent(
        config_store,
        user_id,
        "credentials",
        _filter_gateway_credentials(_credentials_payload_for_storage(credentials)),
    )
    _put_config_if_absent(
        config_store,
        user_id,
        "roles",
        _filter_gateway_roles(roles.model_dump(mode="json")),
    )


def _ensure_gateway_config_store(
    config_store: Any,
    user_id: str,
    roles_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    credentials_record = _get_config_if_present(config_store, user_id, "credentials")
    if credentials_record is None:
        credentials = load_credentials()
        _put_config_if_absent(
            config_store,
            user_id,
            "credentials",
            _filter_gateway_credentials(_credentials_payload(credentials)),
        )
        credentials_record = config_store.get_config(user_id, "credentials")

    roles_record = _get_config_if_present(config_store, user_id, "roles")
    if roles_record is None:
        roles = load_roles_file(roles_path) if roles_path.exists() else RolesData()
        _put_config_if_absent(
            config_store,
            user_id,
            "roles",
            _filter_gateway_roles(roles.model_dump(mode="json")),
        )
        roles_record = config_store.get_config(user_id, "roles")

    return dict(credentials_record.value), dict(roles_record.value)


def _get_config_if_present(config_store: Any, user_id: str, key: str) -> Any | None:
    from app.core.adapters.http_transport import StudioAdapterError

    try:
        return config_store.get_config(user_id, key)
    except KeyError:
        return None
    except StudioAdapterError as exc:
        if exc.error_code == "config.not_found":
            return None
        raise


def _credentials_payload(credentials: LLMCredentialsFile) -> dict[str, Any]:
    from app.services.llm_credentials import _credentials_payload_for_storage

    return _credentials_payload_for_storage(credentials)
