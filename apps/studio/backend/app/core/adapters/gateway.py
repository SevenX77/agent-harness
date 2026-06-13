from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from graph_agent_gateway.registry.base_url import (
    canonicalize_base_url as canonicalize_base_url,
)
from graph_agent_gateway.registry.canonical import (
    canonicalize_model as canonicalize_model,
)
from graph_agent_gateway.registry.capabilities import (
    build_runtime_setting_descriptors as build_runtime_setting_descriptors,
)
from graph_agent_gateway.registry.capabilities import (
    normalize_route_capabilities as normalize_route_capabilities,
)
from graph_agent_gateway.registry.contracts import CredentialProviderProtocol as CredentialProviderProtocol
from graph_agent_gateway.registry.credentials import EndpointCredentialProvider as EndpointCredentialProvider
from graph_agent_gateway.registry.lint import lint_role_routes as lint_role_routes
from graph_agent_gateway.registry.profile_selector import (
    ProfileSelectionError as ProfileSelectionError,
)
from graph_agent_gateway.registry.profile_selector import (
    select_verified_profile as select_verified_profile,
)
from graph_agent_gateway.registry.resolver import RegistryResolutionError as RegistryResolutionError
from graph_agent_gateway.registry.schema import (
    CapabilitySource as CapabilitySource,
)
from graph_agent_gateway.registry.schema import (
    CapabilityValue,
)
from graph_agent_gateway.registry.schema import (
    EvidenceRecord as EvidenceRecord,
)
from graph_agent_gateway.registry.schema import (
    ProviderImportDraft as ProviderImportDraft,
)
from graph_agent_gateway.registry.schema import (
    ProviderRoute as GatewayProviderRoute,
)
from graph_agent_gateway.registry.schema import (
    ProviderRoute as ProviderRoute,
)
from graph_agent_gateway.registry.schema import ResolvedRoute as ResolvedRoute
from graph_agent_gateway.registry.schema import (
    RoleEntry as GatewayRoleEntry,
)
from graph_agent_gateway.registry.schema import (
    RouteCandidate as RouteCandidate,
)
from graph_agent_gateway.registry.schema import (
    RuntimeSettings as RuntimeSettings,
)
from graph_agent_gateway.registry.schema import (
    VerifiedProfile as VerifiedProfile,
)

# Re-exports from graph_agent_gateway for services isolation
from graph_agent_gateway.resolver import ModelResolver as ModelResolver

from app.core.adapters.http_transport import HttpTransport, StudioAdapterError

ProviderUiState = Literal["ready", "untested", "cooling_down", "needs_setup", "off", "failed"]


@dataclass(frozen=True)
class ProviderModelStateProjection:
    ui_state: ProviderUiState
    reason_code: str | None = None
    retry_at: str | None = None
    ui_detail: str | None = None


def _private_profile_supports_reasoning(profile: VerifiedProfile) -> bool:
    haystack = " ".join(
        [
            profile.capability,
            profile.profile_id,
            profile.request_mapper_id,
        ]
    ).lower()
    return "thinking" in haystack or "reasoning" in haystack


def _private_verified_profile_route_capabilities(
    profiles: list[VerifiedProfile],
) -> dict[str, CapabilityValue]:
    ready_profiles = [profile for profile in profiles if profile.status == "ready"]
    if not ready_profiles:
        return {}

    input_modalities = sorted({modality for profile in ready_profiles for modality in (profile.input_modalities or [])})
    output_modalities = sorted(
        {modality for profile in ready_profiles for modality in (profile.output_modalities or [])}
    )
    capabilities: dict[str, CapabilityValue] = {
        "verified_methods": CapabilityValue(
            value=sorted({profile.method_id for profile in ready_profiles}),
            source="probed_verified",
        ),
    }
    if input_modalities:
        capabilities["input_modalities"] = CapabilityValue(
            value=input_modalities,
            source="probed_verified",
        )
    if output_modalities:
        capabilities["output_modalities"] = CapabilityValue(
            value=output_modalities,
            source="probed_verified",
        )
    if any(_private_profile_supports_reasoning(profile) for profile in ready_profiles):
        capabilities["thinking_protocol"] = CapabilityValue(
            value=True,
            source="probed_verified",
        )
    return capabilities


def _private_route_effective_capabilities(route: ProviderRoute) -> dict[str, CapabilityValue]:
    return {
        **route.capabilities,
        **_private_verified_profile_route_capabilities(route.verified_profiles),
    }


def _private_route_thinking_capability(route: ProviderRoute) -> CapabilityValue | None:
    return _private_route_effective_capabilities(route).get("thinking_protocol")


class GatewayAdapter:
    def __init__(
        self,
        transport: Literal["in_process", "http_loopback"],
        http_transport: HttpTransport | None = None,
    ):
        if transport not in ("in_process", "http_loopback"):
            raise ValueError(f"Unknown transport: {transport}")
        self.transport = transport
        self.http_transport = http_transport

    def resolve_routes(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return self.http_transport.post("/gateway/resolve_routes", payload)

        # in_process
        role_name = payload["role_name"]
        credentials = payload["credentials"]
        roles = payload["roles"]

        from app.models.llm_config import LLMCredentialsFile, RolesData
        if isinstance(credentials, dict):
            credentials_obj = LLMCredentialsFile.model_validate(credentials)
        else:
            credentials_obj = credentials

        if isinstance(roles, dict):
            roles_obj = RolesData.model_validate(roles)
        else:
            roles_obj = roles

        import shutil
        import tempfile
        from pathlib import Path

        from app.core import config
        from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore
        from app.services.llm_credentials import _credentials_payload_for_storage

        temp_dir = Path(tempfile.mkdtemp(prefix="studio-gateway-config-"))
        try:
            config_store = LocalGatewayConfigStore(root=temp_dir)
            config_store.put_config(
                config.DEFAULT_USER_ID,
                "credentials",
                _filter_gateway_credentials(_credentials_payload_for_storage(credentials_obj)),
            )
            config_store.put_config(
                config.DEFAULT_USER_ID,
                "roles",
                _filter_gateway_roles(roles_obj.model_dump(mode="json")),
            )
            resolver = ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)
            return resolver.resolve_routes(role_name)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def materialize_role(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return self.http_transport.post("/gateway/materialize_role", payload)

        # in_process
        from app.models.llm_config import (
            LLMCredentialsFile,
            RoleEntry,
            RoleRouteEntry,
        )

        role = payload["role"]
        if isinstance(role, dict):
            role = RoleEntry.model_validate(role)
        credentials = payload["credentials"]
        if isinstance(credentials, dict):
            credentials = LLMCredentialsFile.model_validate(credentials)

        health_store = payload.get("health_store")
        if health_store is None:
            from app.services.llm_credentials import credentials_path
            from app.services.llm_health_store import SqliteLlmHealthStore

            db_path = credentials_path().with_name("llm_health.sqlite")
            health_store = SqliteLlmHealthStore(db_path)

        fallback_chain: list[RoleRouteEntry] = []
        report: dict[str, Any] = {
            "entries": [],
            "warnings": [],
            "skipped_provider_details": [],
        }
        groups = role.model_groups if role.model_fallback_enabled else role.model_groups[:1]
        for group in groups:
            provider_models = list(group.provider_models)
            for provider_model in provider_models:
                route = credentials.provider_routes.get(provider_model.route_id)
                if route is None:
                    continue
                endpoint = credentials.provider_endpoints.get(route.endpoint_id)
                if endpoint is None:
                    continue

                projection = self._private_projection(route.route_id, credentials, health_store)
                if projection is None:
                    continue
                if projection.ui_state in {"needs_setup", "off"}:
                    report["skipped_provider_details"].append(
                        {
                            "route_id": route.route_id,
                            "ui_state": projection.ui_state,
                            "reason_code": projection.reason_code,
                        }
                    )
                    continue
                entry_report: dict[str, Any] = {
                    "canonical_id": group.canonical_id,
                    "route_id": route.route_id,
                    "requested": {},
                    "resolved_settings": {},
                    "warnings": [],
                    "role_fit": "using",
                }
                if projection.ui_state == "cooling_down":
                    warning = {
                        "code": "cooling_down",
                        "route_id": route.route_id,
                        "retry_at": projection.retry_at,
                        "message": projection.ui_detail,
                    }
                    entry_report["warnings"].append(warning)
                    report["warnings"].append(warning)

                role_fit = self._private_apply_intent(entry_report, role, group, route)
                entry_report["role_fit"] = role_fit
                for warning in entry_report["warnings"]:
                    if warning not in report["warnings"]:
                        report["warnings"].append(warning)
                report["entries"].append(entry_report)
                if role_fit in {"needs_test", "not_fit"}:
                    continue
                fallback_chain.append(
                    RoleRouteEntry(
                        route_id=route.route_id,
                        runtime_settings=entry_report["resolved_settings"],
                    )
                )

        return role.model_copy(
            update={
                "fallback_chain": fallback_chain,
                "materialization_report": report,
            }
        )

    def materialize_model_bundle(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return self.http_transport.post("/gateway/materialize_model_bundle", payload)

        # in_process
        from app.models.llm_config import LLMCredentialsFile, ModelBundle, RoleEntry

        bundle = payload["bundle"]
        if isinstance(bundle, dict):
            bundle = ModelBundle.model_validate(bundle)
        credentials = payload["credentials"]
        if isinstance(credentials, dict):
            credentials = LLMCredentialsFile.model_validate(credentials)

        if not bundle.model_groups:
            return bundle

        role_like_bundle = RoleEntry(
            system_prompt_prefix="",
            model_fallback_enabled=bundle.model_fallback_enabled,
            intent=bundle.intent,
            model_groups=bundle.model_groups,
            fallback_chain=bundle.fallback_chain,
            lint_requirements=bundle.lint_requirements,
        )

        materialized = self.materialize_role(
            {
                "role": role_like_bundle,
                "credentials": credentials,
                "health_store": payload.get("health_store"),
            }
        )
        return bundle.model_copy(
            update={
                "fallback_chain": materialized.fallback_chain,
                "materialization_report": materialized.materialization_report,
            }
        )

    def project_route_state(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return self.http_transport.post("/gateway/project_route_state", payload)

        # in_process
        endpoint = payload["endpoint"]
        route = payload["route"]
        circuits = payload["circuits"]
        now = payload.get("now")
        current_time = now or datetime.now(UTC)

        if endpoint.status == "disabled" or route.status == "disabled":
            return ProviderModelStateProjection(ui_state="off")

        if endpoint.status == "failed":
            return ProviderModelStateProjection(
                ui_state="failed",
                reason_code=str(endpoint.metadata.get("reason_code") or "endpoint_unreachable"),
                ui_detail=endpoint.last_test_message,
            )
        if route.status == "failed":
            return ProviderModelStateProjection(
                ui_state="failed",
                reason_code=str(route.metadata.get("reason_code") or "model_failed"),
            )

        if endpoint.api_key is None or not endpoint.api_key.get_secret_value():
            return ProviderModelStateProjection(ui_state="needs_setup", reason_code="missing_key")

        relevant = [
            circuit
            for circuit in circuits
            if circuit.retry_at > current_time and self._circuit_matches(endpoint, route, circuit)
        ]
        active_circuit = None
        if relevant:

            def _scope_priority(scope: str) -> int:
                if scope == "route":
                    return 0
                if scope == "endpoint":
                    return 1
                return 2

            active_circuit = min(
                relevant,
                key=lambda circuit: (
                    -circuit.retry_at.timestamp(),
                    _scope_priority(circuit.scope),
                ),
            )

        if active_circuit is not None:
            return ProviderModelStateProjection(
                ui_state="cooling_down",
                reason_code=active_circuit.reason_code,
                retry_at=active_circuit.retry_at.isoformat(),
                ui_detail=active_circuit.message,
            )
        if endpoint.status == "verified" and route.status == "verified":
            return ProviderModelStateProjection(ui_state="ready")
        return ProviderModelStateProjection(ui_state="untested")

    def _circuit_matches(self, endpoint: Any, route: Any, circuit: Any) -> bool:
        if circuit.scope == "route":
            return circuit.scope_id == route.route_id
        if circuit.scope == "endpoint":
            return circuit.scope_id == endpoint.endpoint_id
        effective_bucket = endpoint.rate_limit_bucket or endpoint.endpoint_id
        return circuit.scope_id == effective_bucket

    def _private_projection(
        self,
        route_id: str,
        credentials: Any,
        health_store: Any,
    ) -> ProviderModelStateProjection | None:
        route = credentials.provider_routes.get(route_id)
        if route is None:
            return None
        endpoint = credentials.provider_endpoints.get(route.endpoint_id)
        if endpoint is None:
            return None
        now = datetime.now(UTC)
        circuits = health_store.get_active_circuits(
            route_id=route.route_id,
            endpoint_id=endpoint.endpoint_id,
            rate_limit_bucket=endpoint.rate_limit_bucket or endpoint.endpoint_id,
            now=now,
        )
        return self.project_route_state(
            {
                "endpoint": endpoint,
                "route": route,
                "circuits": circuits,
                "now": now,
            }
        )

    def _private_apply_intent(
        self,
        entry_report: dict[str, Any],
        role: Any,
        group: Any,
        route: Any,
    ) -> str:
        role_fit = "using"
        thinking = group.intent.thinking
        if thinking == "inherit":
            thinking = role.intent.thinking
        if thinking == "preferred":
            capability = _private_route_thinking_capability(route)
            if capability is None or capability.value is not True:
                warning = {
                    "code": "thinking_not_enabled",
                    "route_id": route.route_id,
                    "message": "Thinking was preferred but is not enabled for this provider model.",
                }
                entry_report["warnings"].append(warning)
                role_fit = "downgraded"
            else:
                self._private_enable_reasoning(entry_report)
        elif thinking == "required":
            capability = _private_route_thinking_capability(route)
            if capability is None:
                self._private_enable_reasoning(entry_report)
                entry_report["warnings"].append(
                    {
                        "code": "thinking_capability_unknown",
                        "route_id": route.route_id,
                        "message": "Thinking is required but capability is unknown.",
                    }
                )
                return "needs_test"
            if capability.value is not True:
                entry_report["warnings"].append(
                    {
                        "code": "thinking_unsupported",
                        "route_id": route.route_id,
                        "message": "Thinking is required but unsupported.",
                    }
                )
                return "not_fit"
            self._private_enable_reasoning(entry_report)

        token_intent = None
        group_intent = group.intent.target_output_tokens
        if group_intent is not None and group_intent.mode != "inherit":
            token_intent = group_intent
        else:
            token_intent = role.intent.target_output_tokens

        if token_intent is not None:
            token_fit = self._private_apply_output_token_intent(entry_report, token_intent, route)
            if token_fit == "not_fit":
                return "not_fit"
            if token_fit == "downgraded":
                role_fit = "downgraded"
        return role_fit

    def _private_enable_reasoning(self, entry_report: dict[str, Any]) -> None:
        reasoning = entry_report["resolved_settings"].setdefault("reasoning", {})
        reasoning["enabled"] = True

    def _private_apply_output_token_intent(
        self,
        entry_report: dict[str, Any],
        token_intent: Any,
        route: Any,
    ) -> str:
        if token_intent.mode == "maximum_available":
            max_tokens = self._private_max_output_tokens(route)
            if max_tokens is not None:
                entry_report["resolved_settings"]["max_output_tokens"] = max_tokens
            return "using"
        if token_intent.mode != "target" or token_intent.value is None:
            return "using"
        max_tokens = self._private_max_output_tokens(route)
        if max_tokens is None or token_intent.value <= max_tokens:
            entry_report["resolved_settings"]["max_output_tokens"] = token_intent.value
            return "using"
        if token_intent.downgrade == "block":
            warning = {
                "code": "token_cap_blocked",
                "route_id": route.route_id,
                "message": (f"Requested {token_intent.value} output tokens exceeds this route limit of {max_tokens}."),
            }
            entry_report["warnings"].append(warning)
            return "not_fit"
        entry_report["resolved_settings"]["max_output_tokens"] = max_tokens
        if token_intent.downgrade == "allow_with_warning":
            warning = {
                "code": "token_downgraded",
                "route_id": route.route_id,
                "message": f"Requested {token_intent.value} output tokens, using {max_tokens}.",
            }
            entry_report["warnings"].append(warning)
        return "downgraded"

    def _private_max_output_tokens(self, route: Any) -> int | None:
        capability = route.capabilities.get("max_output_tokens")
        if capability is None or not isinstance(capability.value, dict):
            return None
        max_value = capability.value.get("max")
        return int(max_value) if isinstance(max_value, int | float) else None

    def decide_fallback(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return self.http_transport.post("/gateway/decide_fallback", payload)

        # in_process
        fallback_chain = payload.get("fallback_chain") or []
        route_ids = [self._route_id(entry) for entry in fallback_chain]
        route_ids = [route_id for route_id in route_ids if route_id]
        if not route_ids:
            raise StudioAdapterError("gateway.empty_fallback_chain", {"detail": "fallback_chain is empty"})

        failed_route_ids = set(payload.get("failed_route_ids") or [])
        current_route_id = payload.get("current_route_id") or route_ids[0]
        status_code = (payload.get("error") or {}).get("status_code")

        if current_route_id not in failed_route_ids and status_code in {429, 500, 502, 503, 504, 529}:
            return {
                "decision": "retry_same",
                "route_id": current_route_id,
                "retry_same": True,
                "give_up": False,
            }

        for route_id in route_ids:
            if route_id not in failed_route_ids and route_id != current_route_id:
                return {
                    "decision": "switch_route",
                    "route_id": route_id,
                    "retry_same": False,
                    "give_up": False,
                }

        raise StudioAdapterError(
            "gateway.fallback_exhausted",
            {
                "decision": "give_up",
                "route_ids": route_ids,
                "failed_route_ids": sorted(failed_route_ids),
            },
        )

    def resolve_credential(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return self.http_transport.post("/gateway/resolve_credential", payload)

        # in_process
        from app.models.llm_config import LLMCredentialsFile

        credentials = payload["credentials"]
        if isinstance(credentials, dict):
            credentials = LLMCredentialsFile.model_validate(credentials)
        credential_ref = payload["credential_ref"]
        ttl_seconds = int(payload.get("ttl_seconds") or 300)
        now = payload.get("now") or datetime.now(UTC)

        provider = EndpointCredentialProvider(credentials.provider_endpoints)
        descriptor = provider.describe(credential_ref)
        if not descriptor.exists:
            raise StudioAdapterError(
                "gateway.credential_missing",
                {"credential_ref": credential_ref, "status": descriptor.status},
            )
        secret = provider.get(credential_ref)
        secret_value = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
        return {
            "credential_ref": credential_ref,
            "secret_handle": secret_value,
            "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            "fingerprint": descriptor.fingerprint,
            "scope": descriptor.scope,
        }

    def _route_id(self, entry: Any) -> str | None:
        if isinstance(entry, dict):
            route_id = entry.get("route_id")
        else:
            route_id = getattr(entry, "route_id", None)
        return route_id if isinstance(route_id, str) else None


def _filter_gateway_credentials(credentials: dict[str, Any]) -> dict[str, Any]:
    filtered = {
        "schema_version": credentials.get("schema_version", 3),
    }

    endpoint_keys = {
        "endpoint_id",
        "protocol",
        "base_url",
        "api_key",
    }
    route_keys = {
        "route_id",
        "endpoint_id",
        "route_slug",
        "provider_model_id",
        "canonical_id",
        "status",
        "capabilities",
        "verified_profiles",
    }

    if "provider_endpoints" in credentials:
        filtered_endpoints = {}
        for ep_id, ep in credentials["provider_endpoints"].items():
            if isinstance(ep, dict):
                filtered_endpoints[ep_id] = {k: v for k, v in ep.items() if k in endpoint_keys}
        filtered["provider_endpoints"] = filtered_endpoints

    if "provider_routes" in credentials:
        filtered_routes = {}
        for r_id, r in credentials["provider_routes"].items():
            if isinstance(r, dict):
                filtered_routes[r_id] = {k: v for k, v in r.items() if k in route_keys}
        filtered["provider_routes"] = filtered_routes

    return filtered


def _filter_gateway_roles(roles: dict[str, Any]) -> dict[str, Any]:
    filtered = {
        "schema_version": roles.get("schema_version", 3),
    }
    
    role_keys = {
        "system_prompt_prefix",
        "source_profile_id",
        "source_profile_snapshot",
        "fallback_chain",
        "lint_requirements",
    }
    
    route_entry_keys = {
        "route_id",
        "runtime_settings_source",
        "runtime_settings",
    }

    if "roles" in roles:
        filtered_roles = {}
        for role_name, r in roles["roles"].items():
            if isinstance(r, dict):
                filtered_r = {k: v for k, v in r.items() if k in role_keys}
                if "fallback_chain" in filtered_r and isinstance(filtered_r["fallback_chain"], list):
                    filtered_chain = []
                    for entry in filtered_r["fallback_chain"]:
                        if isinstance(entry, dict):
                            filtered_chain.append({k: v for k, v in entry.items() if k in route_entry_keys})
                        else:
                            filtered_chain.append(entry)
                    filtered_r["fallback_chain"] = filtered_chain
                filtered_roles[role_name] = filtered_r
        filtered["roles"] = filtered_roles

    profile_keys = {
        "model_profile_id",
        "canonical_id",
        "tags",
        "fallback_chain",
        "lint_requirements",
    }

    if "model_profiles" in roles:
        filtered_profiles = {}
        for p_id, p in roles["model_profiles"].items():
            if isinstance(p, dict):
                filtered_profiles[p_id] = {k: v for k, v in p.items() if k in profile_keys}
        filtered["model_profiles"] = filtered_profiles

    return filtered


__all__ = [
    "GatewayAdapter",
    "ModelResolver",
    "ResolvedRoute",
    "CredentialProviderProtocol",
    "EndpointCredentialProvider",
    "EvidenceRecord",
    "ProviderImportDraft",
    "RouteCandidate",
    "CapabilitySource",
    "canonicalize_base_url",
    "canonicalize_model",
    "normalize_route_capabilities",
    "build_runtime_setting_descriptors",
    "ProfileSelectionError",
    "select_verified_profile",
    "RegistryResolutionError",
    "lint_role_routes",
    "RuntimeSettings",
    "VerifiedProfile",
    "ProviderModelStateProjection",
    "GatewayProviderRoute",
    "GatewayRoleEntry",
    "_filter_gateway_credentials",
    "_filter_gateway_roles",
]
