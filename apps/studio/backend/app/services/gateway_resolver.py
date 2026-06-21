"""Studio wiring for the graph-agent gateway model resolver.

底座一 (single source of truth, no cache of changing config truth): the config
truth is the on-disk ``llm_credentials.json`` + ``llm_roles.yaml``. Every resolver
build reads that truth fresh into a throwaway ``InMemoryConfigTruthStore`` — there
is NO persistent gateway snapshot to seed-then-go-stale, so a credential/role edit
is visible on the very next build with zero staleness. This mirrors the same
pattern already used by ``GatewayAdapter.resolve_routes``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.adapters.gateway import (
    CredentialProviderProtocol,
    InMemoryConfigTruthStore,
    ModelResolver,
    ResolvedRoute,
    _filter_gateway_credentials,
    _filter_gateway_roles,
)
from app.core.adapters.transport_factory import build_gateway_adapter
from app.models.llm_config import RolesData
from app.services.llm_credentials import load_credentials
from app.services.llm_roles import load_roles_file
from app.services.llm_roles import roles_path as default_roles_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GatewayRouteRuntime:
    routes: list[ResolvedRoute]
    credential_provider: CredentialProviderProtocol
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None


def _fresh_config_store(roles_path: Path) -> Any:
    """Build a fresh in-memory ConfigTruthStore from the on-disk single truth.

    Reads the current ``llm_credentials.json`` / ``llm_roles.yaml`` into a
    throwaway ``InMemoryConfigTruthStore`` populated via create-if-absent. The
    store is per-call and never persisted, so the resolver always sees the
    latest on-disk truth — no refresh hook needed.
    """
    from app.core import config
    from app.services.llm_credentials import _credentials_payload_for_storage

    credentials = load_credentials()
    roles = load_roles_file(roles_path) if roles_path.exists() else RolesData()

    config_store = InMemoryConfigTruthStore()
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "credentials",
        _filter_gateway_credentials(_credentials_payload_for_storage(credentials)),
        if_none_match="*",
    )
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "roles",
        _filter_gateway_roles(roles.model_dump(mode="json")),
        if_none_match="*",
    )
    return config_store


def build_gateway_model_resolver(roles_path: Path | None = None) -> ModelResolver:
    """Build a fresh resolver from the live Studio-owned v4/v2 registry truth."""
    from app.core import config

    active_roles_path = roles_path or default_roles_path()
    config_store = _fresh_config_store(active_roles_path)
    return ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)


def build_gateway_route_runtime(
    role_name: str,
    *,
    route_override: str | None = None,
    roles_path: Path | None = None,
) -> GatewayRouteRuntime:
    """Resolve runtime routes through the configured GatewayAdapter (live truth)."""
    from app.core import config

    active_roles_path = roles_path or default_roles_path()
    adapter = build_gateway_adapter()
    config_store = _fresh_config_store(active_roles_path)

    if adapter.transport == "in_process":
        resolver = ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)
        resolved = resolver.resolve_routes(role_name, route_override=route_override)
        return GatewayRouteRuntime(
            routes=list(resolved.routes),
            credential_provider=resolver.credential_provider,
            error_code=resolved.error_code,
            error_payload=resolved.error_payload,
        )

    # http_loopback: the remote gateway resolves; hand it the fresh truth payloads.
    credentials_record = config_store.get_config(config.DEFAULT_USER_ID, "credentials")
    roles_record = config_store.get_config(config.DEFAULT_USER_ID, "roles")
    payload: dict[str, Any] = {
        "role_name": role_name,
        "route_override": route_override,
        "credentials": dict(credentials_record.value),
        "roles": dict(roles_record.value),
    }
    resolved = adapter.resolve_routes(payload)
    resolver = ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)
    return GatewayRouteRuntime(
        routes=list(resolved.routes),
        credential_provider=resolver.credential_provider,
        error_code=resolved.error_code,
        error_payload=resolved.error_payload,
    )
