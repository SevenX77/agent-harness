"""Route-backed gateway model resolver."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from langchain_core.language_models.chat_models import BaseChatModel

from graph_agent_gateway.exceptions import (
    AllProvidersFailedError,
    GatewayRoleNotConfiguredError,
)
from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role
from graph_agent_gateway.registry.schema import RegistrySnapshot


@dataclass
class ModelResolverStats:
    """Runtime statistics for resolver calls."""

    total_resolves: int = 0


class ModelResolver:
    """Resolve registry role/route configuration to a GatewayChatModel."""

    def __init__(
        self,
        *,
        registry_snapshot: RegistrySnapshot | None = None,
        credentials_path: str | Path | None = None,
        roles_path: str | Path | None = None,
        client_manager: Any = None,
    ) -> None:
        if registry_snapshot is None:
            if credentials_path is None or roles_path is None:
                raise ValueError(
                    "ModelResolver requires registry_snapshot or explicit "
                    "credentials_path and roles_path"
                )
            registry_snapshot = load_registry_snapshot(credentials_path, roles_path)
        self.registry_snapshot = registry_snapshot
        self.client_manager = client_manager
        self._stats_lock = threading.Lock()
        self.stats = ModelResolverStats()

    def resolve(
        self,
        role_name: str | None = None,
        *,
        thinking_enabled: bool | None = None,
        model_override: str | None = None,
        callbacks: tuple[Any, ...] = (),
        phase_name: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        del kwargs
        with self._stats_lock:
            self.stats.total_resolves += 1
        if role_name is None:
            raise GatewayRoleNotConfiguredError(
                role_name=None,
                model_override=model_override,
            )
        try:
            resolved = resolve_role(
                self.registry_snapshot,
                role_name,
                route_override=model_override,
            )
        except RegistryResolutionError as exc:
            raise GatewayRoleNotConfiguredError(
                role_name=role_name,
                model_override=model_override,
            ) from exc
        if not resolved.routes:
            raise AllProvidersFailedError(
                resolved.role_name,
                [],
                phase_name=phase_name or "<gateway>",
            )

        first_route = resolved.routes[0]
        max_tokens = _effective_int(first_route, "max_output_tokens", 4096)
        temperature = _effective_float(first_route, "temperature", 0.7)
        effective_thinking_enabled = (
            thinking_enabled
            if thinking_enabled is not None
            else _effective_bool(first_route, "reasoning.enabled", False)
        )
        mock_strategy = getattr(self, "_graph_agent_predict_mock_strategy", None)
        if mock_strategy is not None:
            from graph_agent_gateway.predict_interception import PredictGatewayChatModel

            return PredictGatewayChatModel(
                resolved.role_name,
                resolved,
                mock_strategy=mock_strategy,
                max_tokens=max_tokens,
                temperature=temperature,
                callbacks=callbacks,
                phase_name=phase_name,
                thinking_enabled=effective_thinking_enabled,
                client_manager=self.client_manager,
                name=first_route.provider_model_id,
            )
        return GatewayChatModel(
            resolved.role_name,
            resolved,
            max_tokens=max_tokens,
            temperature=temperature,
            callbacks=callbacks,
            phase_name=phase_name,
            thinking_enabled=effective_thinking_enabled,
            client_manager=self.client_manager,
            name=first_route.provider_model_id,
        )

    def mark_provider_down(self, route_id: str) -> None:
        """Manually mark a route down in the shared gateway cache."""
        route = next(
            (
                item
                for item in self.registry_snapshot.provider_routes.values()
                if item.route_id == route_id
            ),
            None,
        )
        if route is None:
            raise GatewayRoleNotConfiguredError(role_name=None, model_override=route_id)
        role = resolve_role(
            RegistrySnapshot(
                provider_endpoints=self.registry_snapshot.provider_endpoints,
                provider_routes=self.registry_snapshot.provider_routes,
                runtime_policy=self.registry_snapshot.runtime_policy,
                roles={
                    "_manual_mark_down": {
                        "fallback_chain": [{"route_id": route_id}],
                    }
                },
            ),
            "_manual_mark_down",
        )
        manager = (
            self.client_manager
            if self.client_manager is not None
            else _default_client_manager()
        )
        manager.mark_provider_down(
            role.routes[0],
            RuntimeError("manual mark down"),
            role.runtime_policy,
        )


def load_registry_snapshot(
    credentials_path: str | Path,
    roles_path: str | Path,
) -> RegistrySnapshot:
    """Load a v4 credentials file and v2 roles file into one snapshot."""
    credentials = _load_json_object(Path(credentials_path))
    roles = _load_yaml_object(Path(roles_path))
    _assert_v4_credentials(credentials, Path(credentials_path))
    _assert_supported_roles(roles, Path(roles_path))
    roles = _gateway_roles_payload(roles)
    return RegistrySnapshot(
        provider_endpoints=credentials.get("provider_endpoints") or {},
        provider_routes=credentials.get("provider_routes") or {},
        runtime_policy=credentials.get("runtime_policy") or {},
        model_profiles=roles.get("model_profiles") or {},
        roles=roles.get("roles") or {},
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing v4 credentials file: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"credentials file must contain a JSON object: {path}")
    return value


def _load_yaml_object(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing v2 roles file: {path}") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"roles file must contain a YAML object: {path}")
    return value


def _assert_v4_credentials(payload: dict[str, Any], path: Path) -> None:
    schema_version = payload.get("schema_version")
    if schema_version != 4:
        raise ValueError(
            f"credentials file must use schema_version 4: {path}; "
            "legacy provider credentials are rejected at the v4 cutover boundary"
        )
    forbidden = {"providers", "provider_credentials"}
    present = sorted(forbidden.intersection(payload))
    if present:
        raise ValueError(f"legacy credentials fields are not supported: {present}")


def _assert_supported_roles(payload: dict[str, Any], path: Path) -> None:
    schema_version = payload.get("schema_version")
    if schema_version not in {2, 3}:
        raise ValueError(
            f"roles file must use schema_version 2 or 3: {path}; "
            "legacy models/providers/active_model schema is rejected at the v2 cutover boundary"
        )
    forbidden = {
        "models",
        "providers",
        "single_model_roles",
        "peer_model_groups",
        "circuit_breaker",
    }
    present = sorted(forbidden.intersection(payload))
    if present:
        raise ValueError(f"legacy roles fields are not supported: {present}")
    roles = payload.get("roles")
    if isinstance(roles, dict):
        for role_name, role in roles.items():
            if isinstance(role, dict) and ("active_model" in role or "models" in role):
                raise ValueError(f"legacy role schema is not supported for role: {role_name}")


def _gateway_roles_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != 3:
        return payload
    gateway_role_keys = {
        "system_prompt_prefix",
        "source_profile_id",
        "source_profile_snapshot",
        "fallback_chain",
        "lint_requirements",
    }
    roles = payload.get("roles") or {}
    if not isinstance(roles, dict):
        return payload
    gateway_roles = {
        role_name: (
            {key: value for key, value in role.items() if key in gateway_role_keys}
            if isinstance(role, dict)
            else role
        )
        for role_name, role in roles.items()
    }
    return {
        **payload,
        "model_profiles": payload.get("model_profiles") or {},
        "roles": gateway_roles,
    }


def _default_client_manager() -> Any:
    from graph_agent_gateway.client_manager import LLMClientManager

    return LLMClientManager


def _effective_int(route: Any, key: str, default: int) -> int:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return int(value) if isinstance(value, int | float) and value > 0 else default


def _effective_float(route: Any, key: str, default: float) -> float:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return float(value) if isinstance(value, int | float) else default


def _effective_bool(route: Any, key: str, default: bool) -> bool:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return value if isinstance(value, bool) else default
