from __future__ import annotations

import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from graph_agent_gateway.credential_resolver import (
    CredentialResolveError as GatewayCredentialResolveError,
)
from graph_agent_gateway.credential_resolver import (
    CredentialResolveRequest as GatewayCredentialResolveRequest,
)
from graph_agent_gateway.credential_resolver import (
    resolve_credential as gateway_resolve_credential,
)
from graph_agent_gateway.fallback_decision import (
    FallbackDecision as GatewayFallbackDecision,
)
from graph_agent_gateway.fallback_decision import (
    FallbackDecisionRequest as GatewayFallbackDecisionRequest,
)
from graph_agent_gateway.fallback_decision import (
    decide_fallback as gateway_decide_fallback,
)
from graph_agent_gateway.import_draft_store import (
    EVIDENCE_LIBRARY_DRAFT_ID as EVIDENCE_LIBRARY_DRAFT_ID,
)
from graph_agent_gateway.import_draft_store import ImportDraftStore as ImportDraftStore
from graph_agent_gateway.import_draft_store import (
    materialize_import_draft_candidates as materialize_import_draft_candidates,
)
from graph_agent_gateway.import_draft_store import (
    merge_evidence_library as merge_evidence_library,
)
from graph_agent_gateway.import_draft_store import (
    new_evidence_library as new_evidence_library,
)
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
from graph_agent_gateway.registry.schema import VerifiedProfile as VerifiedProfile

# Re-exports from graph_agent_gateway for services isolation
from graph_agent_gateway.resolver import ModelResolver as ModelResolver
from graph_agent_gateway.resolver import ResourceTerminalError as ResourceTerminalError
from graph_agent_gateway.role_materialization import (
    MaterializeRoleRequest as GatewayMaterializeRoleRequest,
)
from graph_agent_gateway.role_materialization import (
    materialize_role as gateway_materialize_role,
)
from graph_agent_gateway.route_handoff import ResolvedRouteChain

# Canonical 6-state route-state projector owned by the gateway package. Studio
# renders gateway facts and must NOT recompute the state vocabulary inline.
from graph_agent_gateway.state_projection import (
    project_route_state as gateway_project_route_state,
)
from graph_agent_gateway.state_projection import (
    project_route_state_from_evidence as gateway_project_route_state_from_evidence,
)

from app.core.adapters.http_transport import HttpTransport, StudioAdapterError

ProviderUiState = Literal["ready", "historical_ready", "untested", "cooling_down", "off", "failed"]
_OPAQUE_SECRET_HANDLE_RE = re.compile(r"^secret-handle://studio-local/[a-f0-9]{32}$")


@dataclass(frozen=True)
class ProviderModelStateProjection:
    ui_state: ProviderUiState
    reason_code: str | None = None
    retry_at: str | None = None
    ui_detail: str | None = None


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
            return ResolvedRouteChain.model_validate(
                self.http_transport.post("/gateway/resolve_routes", _gateway_http_payload(payload))
            )

        # in_process
        role_name = payload["role_name"]
        from app.core import config

        config_store = payload.get("config_store")
        if config_store is not None:
            resolver = ModelResolver(
                config_store=config_store,
                user_id=str(payload.get("user_id") or config.DEFAULT_USER_ID),
            )
            return resolver.resolve_routes(role_name, route_override=payload.get("route_override"))

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

        from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore
        from app.services.llm_credentials import _credentials_payload_for_storage

        temp_dir = Path(tempfile.mkdtemp(prefix="studio-gateway-config-"))
        try:
            config_store = LocalGatewayConfigStore(root=temp_dir)
            _put_config_if_absent(
                config_store,
                config.DEFAULT_USER_ID,
                "credentials",
                _filter_gateway_credentials(_credentials_payload_for_storage(credentials_obj)),
            )
            _put_config_if_absent(
                config_store,
                config.DEFAULT_USER_ID,
                "roles",
                _filter_gateway_roles(roles_obj.model_dump(mode="json")),
            )
            resolver = ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)
            return resolver.resolve_routes(role_name, route_override=payload.get("route_override"))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def materialize_role(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            from app.models.llm_config import RoleEntry

            return RoleEntry.model_validate(
                self.http_transport.post(
                    "/gateway/materialize_role",
                    _gateway_http_payload(payload, exclude_keys={"health_store"}),
                )
            )

        # in_process
        from app.models.llm_config import (
            LLMCredentialsFile,
            RoleEntry,
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

        materialized = gateway_materialize_role(
            GatewayMaterializeRoleRequest(
                role=role,
                credentials=credentials,
                evidence_records=list(payload.get("evidence_records") or []),
                health_store=health_store,
            )
        )

        return role.model_copy(
            update={
                "fallback_chain": materialized.fallback_chain,
                "materialization_report": materialized.materialization_report,
            }
        )

    def materialize_model_bundle(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            from app.models.llm_config import ModelBundle

            return ModelBundle.model_validate(
                self.http_transport.post(
                    "/gateway/materialize_model_bundle",
                    _gateway_http_payload(payload, exclude_keys={"health_store"}),
                )
            )

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
                "evidence_records": payload.get("evidence_records"),
            }
        )
        return bundle.model_copy(
            update={
                "fallback_chain": materialized.fallback_chain,
                "materialization_report": materialized.materialization_report,
            }
        )

    def project_route_state(self, payload: dict[str, Any]) -> ProviderModelStateProjection:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return _provider_projection_from_response(
                self.http_transport.post("/gateway/project_route_state", _gateway_http_payload(payload))
            )

        # in_process — DELEGATE the 6-state vocabulary to the canonical gateway
        # projector. Studio only derives the projector's INPUTS from the stored
        # endpoint/route/circuit facts; it never recomputes ui_state inline.
        endpoint = payload["endpoint"]
        route = payload["route"]
        circuits = payload["circuits"]
        now = payload.get("now")
        current_time = now or datetime.now(UTC)

        credential_available = bool(endpoint.api_key is not None and endpoint.api_key.get_secret_value())
        active_circuit = self._select_active_circuit(endpoint, route, circuits, current_time)
        projector_payload = {
            "route_id": route.route_id,
            "endpoint_status": endpoint.status,
            "route_status": route.status,
            "credential_available": credential_available,
            "circuit_retry_at": active_circuit.retry_at if active_circuit is not None else None,
        }
        evidence_records = list(payload.get("evidence_records") or [])
        if evidence_records:
            gateway_projection = gateway_project_route_state_from_evidence(
                **projector_payload,
                evidence_records=evidence_records,
            )
        else:
            gateway_projection = gateway_project_route_state(
                **projector_payload,
                draft_history=False,
            )

        return self._map_gateway_projection(
            gateway_projection,
            endpoint=endpoint,
            route=route,
            active_circuit=active_circuit,
        )

    def _select_active_circuit(
        self,
        endpoint: Any,
        route: Any,
        circuits: Any,
        current_time: datetime,
    ) -> Any:
        relevant = [
            circuit
            for circuit in circuits
            if circuit.retry_at > current_time and self._circuit_matches(endpoint, route, circuit)
        ]
        if not relevant:
            return None

        def _scope_priority(scope: str) -> int:
            if scope == "route":
                return 0
            if scope == "endpoint":
                return 1
            return 2

        return min(
            relevant,
            key=lambda circuit: (
                -circuit.retry_at.timestamp(),
                _scope_priority(circuit.scope),
            ),
        )

    def _route_draft_history(self, endpoint: Any, route: Any) -> bool:
        # The gateway's historical_ready leg needs a draft_history signal. The
        # probe worker currently stubs this, so no Studio route sets it yet; we
        # read whatever metadata IS available rather than fabricating the signal.
        route_metadata = getattr(route, "metadata", None) or {}
        endpoint_metadata = getattr(endpoint, "metadata", None) or {}
        return bool(route_metadata.get("draft_history") or endpoint_metadata.get("draft_history"))

    def _map_gateway_projection(
        self,
        gateway_projection: Any,
        *,
        endpoint: Any,
        route: Any,
        active_circuit: Any,
    ) -> ProviderModelStateProjection:
        # Map the gateway-decided state into the Studio-facing shape. The gateway
        # owns ui_state + the canonical reason_code; Studio only DECORATES that
        # state with route/circuit facts it already holds (richer reason_code,
        # retry_at as ISO string, ui_detail) — it never overrides the state.
        ui_state = cast(ProviderUiState, gateway_projection.ui_state)
        reason_code = gateway_projection.reason_code

        if ui_state == "cooling_down" and active_circuit is not None:
            return ProviderModelStateProjection(
                ui_state="cooling_down",
                reason_code=active_circuit.reason_code,
                retry_at=active_circuit.retry_at.isoformat(),
                ui_detail=active_circuit.message,
            )

        if ui_state == "failed":
            ui_detail = None
            if endpoint.status == "failed":
                # Prefer Studio's stored failure reason/detail over the canonical
                # fallback the gateway emits for an unreachable endpoint.
                reason_code = str(endpoint.metadata.get("reason_code") or reason_code or "endpoint_unreachable")
                ui_detail = endpoint.last_test_message
            elif route.status == "failed":
                reason_code = str(route.metadata.get("reason_code") or reason_code or "model_failed")
            return ProviderModelStateProjection(
                ui_state="failed",
                reason_code=reason_code,
                ui_detail=ui_detail,
            )

        return ProviderModelStateProjection(ui_state=ui_state)

    def _circuit_matches(self, endpoint: Any, route: Any, circuit: Any) -> bool:
        if circuit.scope == "route":
            return bool(circuit.scope_id == route.route_id)
        if circuit.scope == "endpoint":
            return bool(circuit.scope_id == endpoint.endpoint_id)
        effective_bucket = endpoint.rate_limit_bucket or endpoint.endpoint_id
        return bool(circuit.scope_id == effective_bucket)

    def decide_fallback(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return self.http_transport.post("/gateway/decide_fallback", _gateway_http_payload(payload))

        # in_process
        fallback_chain = payload.get("fallback_chain") or []
        route_ids = [
            route_id
            for route_id in (self._route_id(entry) for entry in fallback_chain)
            if route_id is not None
        ]

        failed_route_ids = [
            route_id
            for route_id in payload.get("failed_route_ids") or []
            if isinstance(route_id, str)
        ]
        raw_current_route_id = payload.get("current_route_id")
        current_route_id = (
            raw_current_route_id
            if isinstance(raw_current_route_id, str)
            else (route_ids[0] if route_ids else "")
        )
        owner_decision = gateway_decide_fallback(
            GatewayFallbackDecisionRequest(
                route_ids=route_ids,
                role=payload.get("role"),
                current_route_id=current_route_id,
                attempt=int(payload.get("attempt") or 1),
                failed_route_ids=failed_route_ids,
                error_context=payload.get("error") or {},
            )
        )
        return _legacy_fallback_decision_response(
            owner_decision,
            route_ids=route_ids,
            failed_route_ids=failed_route_ids,
        )

    def resolve_credential(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return _validate_credential_handle_response(
                self.http_transport.post("/gateway/resolve_credential", _gateway_http_payload(payload))
            )

        # in_process
        from app.models.llm_config import LLMCredentialsFile

        credentials = payload["credentials"]
        if isinstance(credentials, dict):
            credentials = LLMCredentialsFile.model_validate(credentials)
        try:
            owner_response = gateway_resolve_credential(
                GatewayCredentialResolveRequest(
                    user_id=str(payload.get("user_id") or "studio-local"),
                    role=str(payload.get("role") or payload.get("role_name") or ""),
                    credential_ref=payload["credential_ref"],
                    source=payload.get("source") or "local_input",
                    ttl_seconds=int(payload.get("ttl_seconds", 300)),
                    now=payload.get("now"),
                ),
                credential_provider=EndpointCredentialProvider(credentials.provider_endpoints),
            )
        except GatewayCredentialResolveError as exc:
            raise StudioAdapterError(exc.error_code, exc.error_payload) from exc
        owner_payload = owner_response.model_dump() if hasattr(owner_response, "model_dump") else owner_response
        if not isinstance(owner_payload, dict):
            raise StudioAdapterError(
                "credential.invalid_owner_response",
                {"detail": "Credential resolver response must be an object"},
            )
        expires_at = owner_payload.get("expires_at")
        if isinstance(expires_at, datetime):
            owner_payload = dict(owner_payload)
            owner_payload["expires_at"] = expires_at.isoformat()
        return _validate_credential_handle_response(owner_payload)

    def _route_id(self, entry: Any) -> str | None:
        if isinstance(entry, dict):
            route_id = entry.get("route_id")
        else:
            route_id = getattr(entry, "route_id", None)
        return route_id if isinstance(route_id, str) else None


def _gateway_http_payload(
    payload: dict[str, Any],
    *,
    exclude_keys: set[str] | None = None,
) -> dict[str, Any]:
    excluded = exclude_keys or set()
    return {key: _json_compatible(value) for key, value in payload.items() if key not in excluded}


def _json_compatible(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _json_compatible(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _json_compatible(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_compatible(item) for item in value]
    if hasattr(value, "get_secret_value"):
        return "**********"
    if hasattr(value, "__dict__") and value.__class__.__module__ == "types":
        return _json_compatible(vars(value))
    return value


def _put_config_if_absent(
    config_store: Any,
    user_id: str,
    key: str,
    value: dict[str, Any],
) -> str:
    try:
        return str(config_store.get_config(user_id, key).etag)
    except KeyError:
        pass
    except StudioAdapterError as exc:
        if exc.error_code != "config.not_found":
            raise
    return str(config_store.put_config(user_id, key, value, if_none_match="*"))


def _provider_projection_from_response(response: Any) -> ProviderModelStateProjection:
    if isinstance(response, ProviderModelStateProjection):
        return response
    if not isinstance(response, dict):
        raise StudioAdapterError(
            "gateway.invalid_projection_response",
            {"detail": "project_route_state response must be a dict"},
        )
    return ProviderModelStateProjection(
        ui_state=cast(ProviderUiState, response["ui_state"]),
        reason_code=response.get("reason_code"),
        retry_at=response.get("retry_at"),
        ui_detail=response.get("ui_detail"),
    )


def _validate_credential_handle_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise StudioAdapterError("credential.invalid_handle", {"detail": "credential response must be a dict"})
    forbidden = {"raw_secret", "api_key", "secret"}
    leaked = sorted(forbidden.intersection(response))
    secret_handle = response.get("secret_handle")
    expires_at = response.get("expires_at")
    if isinstance(expires_at, str):
        try:
            parsed_expires_at = datetime.fromisoformat(expires_at)
        except ValueError:
            parsed_expires_at = None
    else:
        parsed_expires_at = None
    if parsed_expires_at is not None and parsed_expires_at.tzinfo is None:
        parsed_expires_at = parsed_expires_at.replace(tzinfo=UTC)
    if (
        leaked
        or not isinstance(secret_handle, str)
        or not _OPAQUE_SECRET_HANDLE_RE.fullmatch(secret_handle)
        or parsed_expires_at is None
        or parsed_expires_at <= datetime.now(UTC)
    ):
        raise StudioAdapterError(
            "credential.invalid_handle",
            {
                "detail": "credential response must contain an opaque secret handle and expires_at",
                "forbidden_fields": leaked,
            },
        )
    return _credential_handle_contract_fields(response)


def _credential_handle_contract_fields(response: dict[str, Any]) -> dict[str, Any]:
    contract_fields = ("credential_ref", "secret_handle", "expires_at", "fingerprint", "scope")
    return {field: response[field] for field in contract_fields if field in response}


def _legacy_fallback_decision_response(
    decision: GatewayFallbackDecision,
    *,
    route_ids: list[str],
    failed_route_ids: list[str],
) -> dict[str, Any]:
    if decision.action == "retry_same":
        return {
            "decision": "retry_same",
            "route_id": decision.next_route_id,
            "retry_same": True,
            "give_up": False,
        }
    if decision.action == "switch_route":
        return {
            "decision": "switch_route",
            "route_id": decision.next_route_id,
            "retry_same": False,
            "give_up": False,
        }
    if decision.action == "fail_fast":
        owner_payload = decision.error_payload or {}
        raise StudioAdapterError(
            decision.error_code or "gateway.fail_fast",
            {
                "decision": "fail_fast",
                **owner_payload,
            },
        )

    owner_payload = decision.error_payload or {}
    raise StudioAdapterError(
        decision.error_code or "resource.no_available_route",
        {
            "decision": "give_up",
            "role": owner_payload.get("role"),
            "route_ids": owner_payload.get("route_ids", route_ids),
            "failed_route_ids": owner_payload.get("failed_route_ids", sorted(set(failed_route_ids))),
        },
    )


def _filter_gateway_credentials(credentials: dict[str, Any]) -> dict[str, Any]:
    filtered = {
        "schema_version": credentials.get("schema_version", 3),
    }

    endpoint_keys = {
        "endpoint_id",
        "protocol",
        "base_url",
        "credential_ref",
        "api_key",
        "status",
        "last_test_at",
        "last_test_message",
        "provider_kind",
        "rate_limit_bucket",
        "timeout_seconds",
        "trust_env",
        "proxy_env",
        "metadata",
    }
    route_keys = {
        "route_id",
        "endpoint_id",
        "route_slug",
        "provider_model_id",
        "canonical_id",
        "status",
        "snapshot_version",
        "capabilities",
        "verified_profiles",
        "metadata",
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
    "EVIDENCE_LIBRARY_DRAFT_ID",
    "ImportDraftStore",
    "ProviderImportDraft",
    "RouteCandidate",
    "materialize_import_draft_candidates",
    "merge_evidence_library",
    "new_evidence_library",
    "CapabilitySource",
    "canonicalize_base_url",
    "canonicalize_model",
    "normalize_route_capabilities",
    "build_runtime_setting_descriptors",
    "ProfileSelectionError",
    "select_verified_profile",
    "RegistryResolutionError",
    "ResourceTerminalError",
    "lint_role_routes",
    "RuntimeSettings",
    "VerifiedProfile",
    "ProviderModelStateProjection",
    "GatewayProviderRoute",
    "GatewayRoleEntry",
    "_filter_gateway_credentials",
    "_filter_gateway_roles",
]
