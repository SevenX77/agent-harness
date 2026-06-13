"""Studio wiring for the graph-agent gateway model resolver."""

from __future__ import annotations

from pathlib import Path

from app.core.adapters.gateway import ModelResolver
from app.models.llm_config import RolesData
from app.services.llm_credentials import load_credentials
from app.services.llm_roles import load_roles_file
from app.services.llm_roles import roles_path as default_roles_path


def build_gateway_model_resolver(roles_path: Path | None = None) -> ModelResolver:
    """Build a fresh resolver from Studio-owned v4/v2 registry data."""
    from app.core import config
    from app.core.adapters.gateway import _filter_gateway_credentials, _filter_gateway_roles
    from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore
    from app.services.llm_credentials import _credentials_payload_for_storage

    active_roles_path = roles_path or default_roles_path()
    credentials = load_credentials()
    roles = load_roles_file(active_roles_path) if active_roles_path.exists() else RolesData()

    config_store = LocalGatewayConfigStore(root=config.APP_SETTINGS_DIR)
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "credentials",
        _filter_gateway_credentials(_credentials_payload_for_storage(credentials)),
    )
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "roles",
        _filter_gateway_roles(roles.model_dump(mode="json")),
    )
    return ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)
