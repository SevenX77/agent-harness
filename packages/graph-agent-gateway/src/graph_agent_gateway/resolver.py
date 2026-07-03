"""Route-backed gateway model resolver."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from graph_agent_gateway.exceptions import GatewayRoleNotConfiguredError
from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.protocol import PredictContext
from graph_agent_gateway.registry.contracts import CredentialProviderProtocol
from graph_agent_gateway.registry.credentials import (
    EndpointCredentialProvider,
    FallbackCredentialProvider,
)
from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role
from graph_agent_gateway.registry.schema import (
    RegistrySnapshot,
    RoleEntry,
    RoleRouteEntry,
    RuntimePolicy,
)
from graph_agent_gateway.route_handoff import (
    ResolvedRouteChain,
    resolved_role_to_route_chain,
)
from graph_agent_gateway.storage_contracts import ConfigTruthStore


class ResourceTerminalError(Exception):
    def __init__(self, error_code: str, error_payload: dict[str, Any]) -> None:
        super().__init__(f"ResourceTerminalError: {error_code} - {error_payload}")
        self.error_code = error_code
        self.error_payload = error_payload



@dataclass
class ModelResolverStats:
    """Runtime statistics for resolver calls."""

    total_resolves: int = 0


class ModelResolver:
    """Resolve registry role/route configuration to a GatewayChatModel."""

    def __init__(
        self,
        *,
        config_store: ConfigTruthStore,
        user_id: str,
        client_manager: Any = None,
        credential_provider: CredentialProviderProtocol | None = None,
    ) -> None:
        credentials = config_store.get_config(user_id, "credentials").value
        roles = config_store.get_config(user_id, "roles").value

        _assert_v4_credentials(credentials, Path("credentials"))
        _assert_supported_roles(roles, Path("roles"))
        roles = _gateway_roles_payload(roles)

        registry_snapshot = RegistrySnapshot(
            provider_endpoints=credentials.get("provider_endpoints") or {},
            provider_routes=credentials.get("provider_routes") or {},
            runtime_policy=RuntimePolicy.model_validate(credentials.get("runtime_policy") or {}),
            model_profiles=roles.get("model_profiles") or {},
            model_bundles=roles.get("model_bundles") or {},
            roles=roles.get("roles") or {},
        )

        self.config_store = config_store
        self.user_id = user_id
        self.registry_snapshot = registry_snapshot
        self.client_manager = client_manager
        endpoint_credential_provider = EndpointCredentialProvider(
            registry_snapshot.provider_endpoints
        )
        self.credential_provider = (
            FallbackCredentialProvider(credential_provider, endpoint_credential_provider)
            if credential_provider is not None
            else endpoint_credential_provider
        )
        self._stats_lock = threading.Lock()
        self.stats = ModelResolverStats()

    def resolve(
        self,
        role_name: str | None = None,
        *,
        thinking_enabled: bool | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
        model_override: str | None = None,
        callbacks: tuple[Any, ...] = (),
        phase_name: str | None = None,
        predict_context: PredictContext | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        # ``thinking_enabled`` / ``max_output_tokens`` / ``temperature`` are optional
        # per-call overrides (used for node-level param overrides): when provided they
        # win over the route-derived effective values; when None the route default is
        # used. Symmetric so the three role params override uniformly.
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
                credential_provider=self.credential_provider,
            )
        except RegistryResolutionError as exc:
            raise ResourceTerminalError(
                error_code="resource.no_available_route",
                error_payload=_route_resolution_error_payload(role_name, exc),
            ) from exc

        if not resolved.routes:
            raise ResourceTerminalError(
                error_code="resource.no_available_route",
                error_payload=resolved_role_to_route_chain(resolved).error_payload or {"role": role_name},
            )

        first_route = resolved.routes[0]
        effective_max_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else _effective_int(first_route, "max_output_tokens", 4096)
        )
        effective_temperature = (
            temperature
            if temperature is not None
            else _effective_float(first_route, "temperature", 0.7)
        )
        effective_thinking_enabled = (
            thinking_enabled
            if thinking_enabled is not None
            else _effective_bool(first_route, "reasoning.enabled", False)
        )
        if predict_context is not None:
            from graph_agent_gateway.predict_interception import PredictGatewayChatModel

            return PredictGatewayChatModel(
                resolved.role_name,
                resolved,
                predict_context=predict_context,
                max_tokens=effective_max_tokens,
                temperature=effective_temperature,
                callbacks=callbacks,
                phase_name=phase_name,
                thinking_enabled=effective_thinking_enabled,
                client_manager=self.client_manager,
                credential_provider=self.credential_provider,
                name=first_route.provider_model_id,
            )
        return GatewayChatModel(
            resolved.role_name,
            resolved,
            max_tokens=effective_max_tokens,
            temperature=effective_temperature,
            callbacks=callbacks,
            phase_name=phase_name,
            thinking_enabled=effective_thinking_enabled,
            client_manager=self.client_manager,
            credential_provider=self.credential_provider,
            name=first_route.provider_model_id,
        )

    def resolve_routes(
        self,
        role_name: str,
        *,
        route_override: str | None = None,
    ) -> ResolvedRouteChain:
        with self._stats_lock:
            self.stats.total_resolves += 1
        try:
            resolved = resolve_role(
                self.registry_snapshot,
                role_name,
                route_override=route_override,
                credential_provider=self.credential_provider,
            )
        except RegistryResolutionError as exc:
            raise ResourceTerminalError(
                error_code="resource.no_available_route",
                error_payload=_route_resolution_error_payload(role_name, exc),
            ) from exc

        if not resolved.routes:
            raise ResourceTerminalError(
                error_code="resource.no_available_route",
                error_payload=resolved_role_to_route_chain(resolved).error_payload or {"role": role_name},
            )
        return resolved_role_to_route_chain(resolved)

    def resolve_temporary_role(
        self,
        role_name: str,
        role: RoleEntry | Mapping[str, Any],
        *,
        route_override: str | None = None,
    ) -> ResolvedRouteChain:
        temporary_role = RoleEntry.model_validate(role)
        temporary_snapshot = self.registry_snapshot.model_copy(
            update={"roles": {**self.registry_snapshot.roles, role_name: temporary_role}}
        )

        try:
            resolved = resolve_role(
                temporary_snapshot,
                role_name,
                route_override=route_override,
                credential_provider=self.credential_provider,
            )
        except RegistryResolutionError as exc:
            raise ResourceTerminalError(
                error_code="resource.no_available_route",
                error_payload=_route_resolution_error_payload(role_name, exc),
            ) from exc

        if not resolved.routes:
            raise ResourceTerminalError(
                error_code="resource.no_available_route",
                error_payload=resolved_role_to_route_chain(resolved).error_payload or {"role": role_name},
            )
        return resolved_role_to_route_chain(resolved)

    def resolve_temporary_roles(
        self,
        roles: Mapping[str, RoleEntry | Mapping[str, Any]],
    ) -> dict[str, ResolvedRouteChain]:
        return {
            role_name: self.resolve_temporary_role(role_name, role)
            for role_name, role in roles.items()
        }

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
                    "_manual_mark_down": RoleEntry(
                        fallback_chain=[RoleRouteEntry(route_id=route_id)]
                    )
                },
            ),
            "_manual_mark_down",
            credential_provider=self.credential_provider,
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


def _route_resolution_error_payload(
    role_name: str,
    exc: RegistryResolutionError,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": role_name}
    skipped = getattr(exc, "skipped_diagnostics", None)
    if skipped:
        payload["skipped"] = [
            {
                "route_id": item.route_id,
                "reason_code": item.reason_code,
                "message": item.message,
                "from_override": item.from_override,
            }
            for item in skipped
        ]
    return payload


def _assert_v4_credentials(payload: dict[str, Any], path: Path) -> None:
    schema_version = payload.get("schema_version")
    if schema_version not in {4, 5}:
        raise ValueError(
            f"credentials file must use schema_version 4 or 5: {path}; "
            "legacy provider credentials are rejected at the v4/v5 cutover boundary"
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
        "bundle_id",
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
        "model_bundles": _gateway_model_bundles_payload(payload),
        "roles": gateway_roles,
    }


def _gateway_model_bundles_payload(payload: dict[str, Any]) -> dict[str, Any]:
    bundles = payload.get("model_bundles") or {}
    if not isinstance(bundles, dict):
        return {}

    gateway_bundles: dict[str, Any] = {}
    gateway_bundle_keys = {"bundle_id", "fallback_chain", "lint_requirements"}
    for bundle_id, bundle in bundles.items():
        if not isinstance(bundle, dict):
            gateway_bundles[bundle_id] = bundle
            continue
        gateway_bundle = {key: value for key, value in bundle.items() if key in gateway_bundle_keys}
        gateway_bundle["bundle_id"] = (
            gateway_bundle.get("bundle_id")
            or bundle.get("model_profile_id")
            or bundle_id
        )
        gateway_bundle["fallback_chain"] = bundle.get("fallback_chain") or []
        gateway_bundle["lint_requirements"] = bundle.get("lint_requirements") or {}
        gateway_bundles[bundle_id] = gateway_bundle
    return gateway_bundles


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
