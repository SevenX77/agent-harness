"""Studio Role authoring to gateway fallback-chain materialization."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.llm_config import (
    LLMCredentialsFile,
    ModelBundle,
    ProviderRoute,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
    RoleRouteEntry,
    RoleTokenIntent,
    TokenIntent,
)
from app.services.llm_health_store import SqliteLlmHealthStore
from app.services.llm_route_capabilities import route_thinking_capability
from app.services.llm_state_projection import (
    ProviderModelStateProjection,
    project_provider_model_state,
)


def materialize_role(
    role: RoleEntry,
    credentials: LLMCredentialsFile,
    health_store: SqliteLlmHealthStore,
) -> RoleEntry:
    """Generate a gateway-compatible fallback chain and report from Role authoring."""
    fallback_chain: list[RoleRouteEntry] = []
    report: dict[str, Any] = {
        "entries": [],
        "warnings": [],
        "skipped_provider_details": [],
    }
    groups = role.model_groups if role.model_fallback_enabled else role.model_groups[:1]
    for group in groups:
        for provider_model in _ordered_provider_models(group):
            route = credentials.provider_routes.get(provider_model.route_id)
            if route is None:
                continue
            endpoint = credentials.provider_endpoints.get(route.endpoint_id)
            if endpoint is None:
                continue
            projection = _projection(route.route_id, credentials, health_store)
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


def materialize_model_bundle(
    bundle: ModelBundle,
    credentials: LLMCredentialsFile,
    health_store: SqliteLlmHealthStore,
) -> ModelBundle:
    """Generate a flat route chain for a user-authored model bundle."""
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
    materialized = materialize_role(role_like_bundle, credentials, health_store)
    return bundle.model_copy(
        update={
            "fallback_chain": materialized.fallback_chain,
            "materialization_report": materialized.materialization_report,
        }
    )


def _ordered_provider_models(
    group: RoleModelGroup,
) -> list[RoleProviderModel]:
    return list(group.provider_models)


def _projection(
    route_id: str,
    credentials: LLMCredentialsFile,
    health_store: SqliteLlmHealthStore,
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
    return project_provider_model_state(
        endpoint=endpoint,
        route=route,
        circuits=circuits,
        now=now,
    )


def _apply_intent(
    entry_report: dict[str, Any],
    role: RoleEntry,
    group: RoleModelGroup,
    route: ProviderRoute,
) -> str:
    role_fit = "using"
    thinking = group.intent.thinking
    if thinking == "inherit":
        thinking = role.intent.thinking
    if thinking == "preferred":
        capability = route_thinking_capability(route)
        if capability is None or capability.value is not True:
            warning = {
                "code": "thinking_not_enabled",
                "route_id": route.route_id,
                "message": "Thinking was preferred but is not enabled for this provider model.",
            }
            entry_report["warnings"].append(warning)
            role_fit = "downgraded"
        else:
            _enable_reasoning(entry_report)
    elif thinking == "required":
        capability = route_thinking_capability(route)
        if capability is None:
            _enable_reasoning(entry_report)
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
        _enable_reasoning(entry_report)
    token_intent = _effective_output_token_intent(role, group)
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


def _effective_output_token_intent(
    role: RoleEntry,
    group: RoleModelGroup,
) -> TokenIntent | RoleTokenIntent | None:
    group_intent = group.intent.target_output_tokens
    if group_intent is not None and group_intent.mode != "inherit":
        return group_intent
    return role.intent.target_output_tokens


def _apply_output_token_intent(
    entry_report: dict[str, Any],
    token_intent: TokenIntent | RoleTokenIntent,
    route: ProviderRoute,
) -> str:
    if token_intent.mode == "maximum_available":
        max_tokens = _max_output_tokens(route)
        if max_tokens is not None:
            entry_report["resolved_settings"]["max_output_tokens"] = max_tokens
        return "using"
    if token_intent.mode != "target" or token_intent.value is None:
        return "using"
    max_tokens = _max_output_tokens(route)
    if max_tokens is None or token_intent.value <= max_tokens:
        entry_report["resolved_settings"]["max_output_tokens"] = token_intent.value
        return "using"
    if token_intent.downgrade == "block":
        warning = {
            "code": "token_cap_blocked",
            "route_id": route.route_id,
            "message": (
                f"Requested {token_intent.value} output tokens exceeds this route limit "
                f"of {max_tokens}."
            ),
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


def _max_output_tokens(route: ProviderRoute) -> int | None:
    capability = route.capabilities.get("max_output_tokens")
    if capability is None or not isinstance(capability.value, dict):
        return None
    max_value = capability.value.get("max")
    return int(max_value) if isinstance(max_value, int | float) else None
