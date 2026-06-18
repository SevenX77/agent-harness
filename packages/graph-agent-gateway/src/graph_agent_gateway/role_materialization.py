from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from graph_agent_gateway.registry.schema import CapabilityValue, RoleRouteEntry
from graph_agent_gateway.state_projection import project_route_state_from_evidence


@dataclass(frozen=True)
class MaterializeRoleRequest:
    role: Any
    credentials: Any
    evidence_records: list[Any] | None = None
    health_store: Any | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class MaterializedRoleResult:
    fallback_chain: list[RoleRouteEntry]
    materialization_report: dict[str, Any]


@dataclass(frozen=True)
class _ProjectionFacts:
    ui_state: str
    reason_code: str | None = None
    retry_at: str | None = None
    ui_detail: str | None = None


def materialize_role(request: MaterializeRoleRequest) -> MaterializedRoleResult:
    role = request.role
    credentials = request.credentials
    health_store = request.health_store
    current_time = request.now or datetime.now(UTC)
    fallback_chain: list[RoleRouteEntry] = []
    report: dict[str, Any] = {
        "entries": [],
        "warnings": [],
        "skipped_provider_details": [],
    }

    groups = list(_value(role, "model_groups", []))
    if not _value(role, "model_fallback_enabled", True):
        groups = groups[:1]

    for group in groups:
        for provider_model in list(_value(group, "provider_models", [])):
            route_id = _value(provider_model, "route_id")
            if not isinstance(route_id, str):
                continue
            route = _mapping_get(_value(credentials, "provider_routes", {}), route_id)
            if route is None:
                continue
            endpoint = _mapping_get(_value(credentials, "provider_endpoints", {}), _value(route, "endpoint_id"))
            if endpoint is None:
                continue

            projection = _materialization_projection(
                endpoint,
                route,
                health_store,
                current_time,
                evidence_records=list(request.evidence_records or []),
            )
            if projection.ui_state in {"failed", "off"}:
                report["skipped_provider_details"].append(
                    {
                        "route_id": route_id,
                        "ui_state": projection.ui_state,
                        "reason_code": projection.reason_code,
                    }
                )
                continue

            entry_report: dict[str, Any] = {
                "canonical_id": _value(group, "canonical_id"),
                "route_id": route_id,
                "requested": {},
                "resolved_settings": {},
                "warnings": [],
                "role_fit": "using",
            }
            if projection.ui_state == "cooling_down":
                warning = {
                    "code": "cooling_down",
                    "route_id": route_id,
                    "retry_at": projection.retry_at,
                    "message": projection.ui_detail,
                }
                entry_report["warnings"].append(warning)
                report["warnings"].append(warning)

            role_fit = _apply_intent(entry_report, role, group, route)
            entry_report["role_fit"] = role_fit
            for warning in entry_report["warnings"]:
                if warning not in report["warnings"]:
                    report["warnings"].append(warning)
            report["entries"].append(entry_report)
            if role_fit in {"needs_test", "not_fit"}:
                continue
            fallback_chain.append(
                RoleRouteEntry(
                    route_id=route_id,
                    runtime_settings=entry_report["resolved_settings"],
                )
            )

    return MaterializedRoleResult(
        fallback_chain=fallback_chain,
        materialization_report=report,
    )


def _materialization_projection(
    endpoint: Any,
    route: Any,
    health_store: Any | None,
    current_time: datetime,
    *,
    evidence_records: list[Any],
) -> _ProjectionFacts:
    active_circuit = _select_active_circuit(
        endpoint,
        route,
        _active_circuits(endpoint, route, health_store, current_time),
        current_time,
    )
    gateway_projection = project_route_state_from_evidence(
        route_id=_value(route, "route_id"),
        endpoint_status=_value(endpoint, "status"),
        route_status=_value(route, "status"),
        credential_available=_credential_available(endpoint),
        circuit_retry_at=_value(active_circuit, "retry_at") if active_circuit is not None else None,
        evidence_records=evidence_records,
    )

    ui_state = gateway_projection.ui_state
    reason_code = gateway_projection.reason_code
    if ui_state == "cooling_down" and active_circuit is not None:
        return _ProjectionFacts(
            ui_state="cooling_down",
            reason_code=_value(active_circuit, "reason_code"),
            retry_at=_value(active_circuit, "retry_at").isoformat(),
            ui_detail=_value(active_circuit, "message"),
        )

    if ui_state == "failed":
        endpoint_status = _value(endpoint, "status")
        route_status = _value(route, "status")
        if endpoint_status == "failed":
            reason_code = str(
                (_value(endpoint, "metadata", {}) or {}).get("reason_code")
                or reason_code
                or "endpoint_unreachable"
            )
        elif route_status == "failed":
            reason_code = str(
                (_value(route, "metadata", {}) or {}).get("reason_code")
                or reason_code
                or "model_failed"
            )
        return _ProjectionFacts(ui_state="failed", reason_code=reason_code)

    return _ProjectionFacts(ui_state=ui_state)


def _active_circuits(
    endpoint: Any,
    route: Any,
    health_store: Any | None,
    current_time: datetime,
) -> list[Any]:
    if health_store is None:
        return []
    return list(
        health_store.get_active_circuits(
            route_id=_value(route, "route_id"),
            endpoint_id=_value(endpoint, "endpoint_id"),
            rate_limit_bucket=_value(endpoint, "rate_limit_bucket")
            or _value(endpoint, "endpoint_id"),
            now=current_time,
        )
    )


def _select_active_circuit(
    endpoint: Any,
    route: Any,
    circuits: list[Any],
    current_time: datetime,
) -> Any | None:
    relevant = [
        circuit
        for circuit in circuits
        if _value(circuit, "retry_at") > current_time and _circuit_matches(endpoint, route, circuit)
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
            -_value(circuit, "retry_at").timestamp(),
            _scope_priority(_value(circuit, "scope")),
        ),
    )


def _circuit_matches(endpoint: Any, route: Any, circuit: Any) -> bool:
    if _value(circuit, "scope") == "route":
        return bool(_value(circuit, "scope_id") == _value(route, "route_id"))
    if _value(circuit, "scope") == "endpoint":
        return bool(_value(circuit, "scope_id") == _value(endpoint, "endpoint_id"))
    effective_bucket = _value(endpoint, "rate_limit_bucket") or _value(endpoint, "endpoint_id")
    return bool(_value(circuit, "scope_id") == effective_bucket)


def _credential_available(endpoint: Any) -> bool:
    credential_ref = _value(endpoint, "credential_ref")
    if isinstance(credential_ref, str) and credential_ref:
        return True
    secret_handle = _value(endpoint, "secret_handle")
    if isinstance(secret_handle, str) and secret_handle:
        return True
    api_key = _value(endpoint, "api_key")
    if api_key is None:
        return False
    if hasattr(api_key, "get_secret_value"):
        return bool(api_key.get_secret_value())
    return bool(api_key)


def _route_draft_history(endpoint: Any, route: Any) -> bool:
    route_metadata = _value(route, "metadata", {}) or {}
    endpoint_metadata = _value(endpoint, "metadata", {}) or {}
    return bool(route_metadata.get("draft_history") or endpoint_metadata.get("draft_history"))


def _apply_intent(
    entry_report: dict[str, Any],
    role: Any,
    group: Any,
    route: Any,
) -> str:
    role_fit = "using"
    group_intent = _value(group, "intent")
    role_intent = _value(role, "intent")
    thinking = _value(group_intent, "thinking", "inherit")
    if thinking == "inherit":
        thinking = _value(role_intent, "thinking", "off")
    if thinking == "preferred":
        capability = _route_thinking_capability(route)
        if capability is None or _capability_value(capability) is not True:
            warning = {
                "code": "thinking_not_enabled",
                "route_id": _value(route, "route_id"),
                "message": "Thinking was preferred but is not enabled for this provider model.",
            }
            entry_report["warnings"].append(warning)
            role_fit = "downgraded"
        else:
            _enable_reasoning(entry_report)
    elif thinking == "required":
        capability = _route_thinking_capability(route)
        if capability is None:
            _enable_reasoning(entry_report)
            entry_report["warnings"].append(
                {
                    "code": "thinking_capability_unknown",
                    "route_id": _value(route, "route_id"),
                    "message": "Thinking is required but capability is unknown.",
                }
            )
            return "needs_test"
        if _capability_value(capability) is not True:
            entry_report["warnings"].append(
                {
                    "code": "thinking_unsupported",
                    "route_id": _value(route, "route_id"),
                    "message": "Thinking is required but unsupported.",
                }
            )
            return "not_fit"
        _enable_reasoning(entry_report)

    token_intent = None
    group_token_intent = _value(group_intent, "target_output_tokens")
    if group_token_intent is not None and _value(group_token_intent, "mode") != "inherit":
        token_intent = group_token_intent
    else:
        token_intent = _value(role_intent, "target_output_tokens")

    if token_intent is not None:
        token_fit = _apply_output_token_intent(entry_report, token_intent, route)
        if token_fit == "not_fit":
            return "not_fit"
        if token_fit == "downgraded":
            role_fit = "downgraded"
    return role_fit


def _enable_reasoning(entry_report: dict[str, Any]) -> None:
    reasoning = entry_report["resolved_settings"].setdefault("reasoning", {})
    reasoning["enabled"] = True


def _apply_output_token_intent(
    entry_report: dict[str, Any],
    token_intent: Any,
    route: Any,
) -> str:
    mode = _value(token_intent, "mode")
    if mode == "maximum_available":
        max_tokens = _max_output_tokens(route)
        if max_tokens is not None:
            entry_report["resolved_settings"]["max_output_tokens"] = max_tokens
        return "using"
    if mode != "target" or _value(token_intent, "value") is None:
        return "using"
    token_value = _value(token_intent, "value")
    max_tokens = _max_output_tokens(route)
    if max_tokens is None or token_value <= max_tokens:
        entry_report["resolved_settings"]["max_output_tokens"] = token_value
        return "using"
    if _value(token_intent, "downgrade") == "block":
        warning = {
            "code": "token_cap_blocked",
            "route_id": _value(route, "route_id"),
            "message": f"Requested {token_value} output tokens exceeds this route limit of {max_tokens}.",
        }
        entry_report["warnings"].append(warning)
        return "not_fit"
    entry_report["resolved_settings"]["max_output_tokens"] = max_tokens
    if _value(token_intent, "downgrade") == "allow_with_warning":
        warning = {
            "code": "token_downgraded",
            "route_id": _value(route, "route_id"),
            "message": f"Requested {token_value} output tokens, using {max_tokens}.",
        }
        entry_report["warnings"].append(warning)
    return "downgraded"


def _max_output_tokens(route: Any) -> int | None:
    capability = (_value(route, "capabilities", {}) or {}).get("max_output_tokens")
    if capability is None or not isinstance(_capability_value(capability), dict):
        return None
    max_value = _capability_value(capability).get("max")
    return int(max_value) if isinstance(max_value, int | float) else None


def _route_thinking_capability(route: Any) -> Any | None:
    return _route_effective_capabilities(route).get("thinking_protocol")


def _route_effective_capabilities(route: Any) -> dict[str, Any]:
    return {
        **(_value(route, "capabilities", {}) or {}),
        **_verified_profile_route_capabilities(_value(route, "verified_profiles", [])),
    }


def _verified_profile_route_capabilities(profiles: list[Any]) -> dict[str, CapabilityValue]:
    ready_profiles = [profile for profile in profiles if _value(profile, "status") == "ready"]
    if not ready_profiles:
        return {}

    input_modalities = sorted(
        {
            modality
            for profile in ready_profiles
            for modality in (_value(profile, "input_modalities", []) or [])
        }
    )
    output_modalities = sorted(
        {
            modality
            for profile in ready_profiles
            for modality in (_value(profile, "output_modalities", []) or [])
        }
    )
    capabilities: dict[str, CapabilityValue] = {
        "verified_methods": CapabilityValue(
            value=sorted({_value(profile, "method_id") for profile in ready_profiles}),
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
    if any(_profile_supports_reasoning(profile) for profile in ready_profiles):
        capabilities["thinking_protocol"] = CapabilityValue(
            value=True,
            source="probed_verified",
        )
    return capabilities


def _profile_supports_reasoning(profile: Any) -> bool:
    haystack = " ".join(
        [
            str(_value(profile, "capability", "")),
            str(_value(profile, "profile_id", "")),
            str(_value(profile, "request_mapper_id", "")),
        ]
    ).lower()
    return "thinking" in haystack or "reasoning" in haystack


def _capability_value(capability: Any) -> Any:
    if isinstance(capability, dict):
        return capability.get("value")
    return _value(capability, "value")


def _mapping_get(mapping: Any, key: Any) -> Any:
    if not isinstance(key, str):
        return None
    if isinstance(mapping, dict):
        return mapping.get(key)
    return None


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)
