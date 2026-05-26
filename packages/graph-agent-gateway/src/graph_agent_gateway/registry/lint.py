"""Capability linting for explicit route chains."""

from __future__ import annotations

from typing import Any

from graph_agent_gateway.registry.schema import LintResult, ProviderRoute, RoleEntry, RoleRouteEntry

LINT_TO_CAPABILITY = {
    "thinking": "thinking_protocol",
    "tool_calling": "tool_protocol",
    "structured_output": "structured_output_protocol",
    "vision": "vision",
    "max_input_tokens": "max_input_tokens",
    "max_output_tokens": "max_output_tokens",
}


def capability_key_for_lint(lint_key: str) -> str:
    """Return the normalized capability key for a lint requirement key."""
    try:
        return LINT_TO_CAPABILITY[lint_key]
    except KeyError as exc:
        raise ValueError(f"unknown lint requirement: {lint_key}") from exc


def lint_role_routes(
    role_name: str,
    role: RoleEntry,
    routes: list[ProviderRoute],
) -> list[LintResult]:
    """Evaluate role lint requirements against concrete routes."""
    results: list[LintResult] = []
    route_by_id = {route.route_id: route for route in routes}
    for entry in role.fallback_chain:
        route = route_by_id.get(entry.route_id)
        if route is not None:
            results.extend(_lint_runtime_settings(role_name, entry, route))
    for lint_key, severity in role.lint_requirements.items():
        if severity == "off":
            continue
        capability_key = capability_key_for_lint(lint_key)
        for route in routes:
            capability = route.capabilities.get(capability_key)
            if capability is None:
                blocking = severity == "error"
                results.append(
                    LintResult(
                        role_name=role_name,
                        route_id=route.route_id,
                        severity=severity,
                        capability=lint_key,
                        message=f"Route has no {capability_key} capability",
                        source="requires_probe" if blocking else "missing",
                        blocking=blocking,
                        code="requires_probe" if blocking else None,
                    )
                )
                continue
            if not capability.value:
                results.append(
                    LintResult(
                        role_name=role_name,
                        route_id=route.route_id,
                        severity=severity,
                        capability=lint_key,
                        message=f"Route capability {capability_key} is incompatible",
                        source=capability.source,
                        blocking=severity == "error",
                        code="incompatible" if severity == "error" else None,
                    )
                )
                continue
            if severity == "error" and capability.source not in {"manual", "probed_verified"}:
                results.append(
                    LintResult(
                        role_name=role_name,
                        route_id=route.route_id,
                        severity=severity,
                        capability=lint_key,
                        message=f"Route capability {capability_key} requires verification",
                        source="requires_probe",
                        blocking=True,
                        code="requires_probe",
                    )
                )
    return results


def _lint_runtime_settings(
    role_name: str,
    entry: RoleRouteEntry,
    route: ProviderRoute,
) -> list[LintResult]:
    results: list[LintResult] = []
    settings = entry.runtime_settings
    if settings.temperature is not None:
        results.extend(
            _lint_numeric_runtime_setting(
                role_name,
                route,
                "temperature",
                settings.temperature,
            )
        )
    if settings.top_p is not None:
        results.extend(
            _lint_numeric_runtime_setting(
                role_name,
                route,
                "top_p",
                settings.top_p,
            )
        )
    if settings.max_output_tokens is not None:
        min_output = _capability_min(route, "min_output_tokens")
        max_output = _capability_max(route, "max_output_tokens")
        if min_output is not None and settings.max_output_tokens < min_output:
            results.append(
                _runtime_error(
                    role_name,
                    route.route_id,
                    "max_output_tokens",
                    f"Route max_output_tokens must be at least {min_output}",
                    "runtime_setting_invalid",
                )
            )
        if max_output is not None and settings.max_output_tokens > max_output:
            results.append(
                _runtime_error(
                    role_name,
                    route.route_id,
                    "max_output_tokens",
                    f"Route max_output_tokens must be no more than {max_output}",
                    "runtime_setting_invalid",
                )
            )

    if settings.seed is not None and not _capability_supported(route, "seed"):
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                "seed",
                "Route runtime setting configures seed, but this route does not support seed",
                "runtime_setting_unsupported",
            )
        )

    if settings.stop_sequences and _capability_known_unsupported(route, "stop_sequences"):
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                "stop_sequences",
                "Route runtime setting configures stop sequences, "
                "but this route does not support them",
                "runtime_setting_unsupported",
            )
        )

    if settings.tool_choice is not None and _capability_known_unsupported(route, "tool_choice"):
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                "tool_choice",
                "Route runtime setting configures tool_choice, but this route does not support it",
                "runtime_setting_unsupported",
            )
        )
    elif (
        isinstance(settings.tool_choice, str)
        and _capability_allowed_values(route, "tool_choice")
        and settings.tool_choice not in _capability_allowed_values(route, "tool_choice")
    ):
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                "tool_choice",
                "Route runtime setting configures an unsupported tool_choice value",
                "runtime_setting_invalid",
            )
        )

    if settings.parallel_tool_calls is not None and _capability_known_unsupported(
        route,
        "parallel_tool_calls",
    ):
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                "parallel_tool_calls",
                "Route runtime setting configures parallel_tool_calls, "
                "but this route does not support it",
                "runtime_setting_unsupported",
            )
        )

    if settings.reasoning.effort is not None:
        allowed_efforts = _capability_allowed_values(route, "reasoning_effort")
        if _capability_known_unsupported(route, "reasoning_effort"):
            results.append(
                _runtime_error(
                    role_name,
                    route.route_id,
                    "reasoning.effort",
                    "Route runtime setting configures reasoning effort, "
                    "but this route does not support it",
                    "runtime_setting_unsupported",
                )
            )
        elif allowed_efforts and settings.reasoning.effort not in allowed_efforts:
            results.append(
                _runtime_error(
                    role_name,
                    route.route_id,
                    "reasoning.effort",
                    "Route runtime setting configures an unsupported reasoning effort value",
                    "runtime_setting_invalid",
                )
            )

    if (
        settings.structured_output is not None
        and settings.structured_output.mode != "none"
        and not _capability_supported(route, "structured_output_protocol")
    ):
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                "structured_output",
                "Route runtime setting configures structured output, "
                "but this route does not support it",
                "runtime_setting_unsupported",
            )
        )

    if settings.reasoning.enabled is not True:
        return results

    thinking = route.capabilities.get("thinking_protocol")
    if thinking is None or not thinking.value:
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                "thinking",
                "Route runtime setting enables thinking, but the route has "
                "no compatible thinking_protocol capability",
                "runtime_setting_unsupported",
            )
        )
        return results

    if settings.reasoning.budget_tokens is not None and _capability_value(
        route,
        "manual_thinking_budget_supported",
    ) is False:
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                "reasoning.budget_tokens",
                "Route runtime setting configures a manual thinking budget, "
                "but this route only supports adaptive thinking",
                "runtime_setting_unsupported",
            )
        )
        return results

    if settings.reasoning.budget_tokens is None:
        if _bool_capability(route, "adaptive_thinking"):
            return results
        if _capability_value(route, "manual_thinking_budget_supported") is False:
            results.append(
                _runtime_error(
                    role_name,
                    route.route_id,
                    "thinking",
                    "Route runtime setting enables thinking, but the route "
                    "supports neither adaptive thinking nor manual thinking "
                    "budgets",
                    "runtime_setting_unsupported",
                )
            )
            return results

    min_budget = _capability_min(route, "reasoning_budget_tokens")
    if min_budget is None:
        min_budget = _capability_min(route, "min_thinking_budget_tokens")
    if min_budget is not None:
        budget = settings.reasoning.budget_tokens
        if budget is None:
            budget = _capability_default(route, "reasoning_budget_tokens")
        if budget is None:
            budget = _capability_default(
                route,
                "default_thinking_budget_tokens",
            )
        if budget is not None and budget < min_budget:
            results.append(
                _runtime_error(
                    role_name,
                    route.route_id,
                    "reasoning.budget_tokens",
                    f"Thinking budget must be at least {min_budget}",
                    "runtime_setting_invalid",
                )
            )
        if (
            settings.max_output_tokens is not None
            and (
                settings.max_output_tokens <= (budget or min_budget)
                or settings.max_output_tokens <= min_budget
            )
            and _bool_capability(route, "requires_thinking_budget_lt_max_output")
        ):
            results.append(
                _runtime_error(
                    role_name,
                    route.route_id,
                    "max_output_tokens",
                    "max_output_tokens must be greater than the thinking budget",
                    "runtime_setting_invalid",
                )
            )

    return results


def _runtime_error(
    role_name: str,
    route_id: str,
    capability: str,
    message: str,
    code: str,
) -> LintResult:
    return LintResult(
        role_name=role_name,
        route_id=route_id,
        severity="error",
        capability=capability,
        message=message,
        source="runtime_settings",
        blocking=True,
        code=code,
    )


def _lint_numeric_runtime_setting(
    role_name: str,
    route: ProviderRoute,
    capability: str,
    value: float,
) -> list[LintResult]:
    results: list[LintResult] = []
    minimum = _capability_numeric_min(route, capability)
    maximum = _capability_numeric_max(route, capability)
    if minimum is not None and value < minimum:
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                capability,
                f"Route {capability} must be at least {minimum:g}",
                "runtime_setting_invalid",
            )
        )
    if maximum is not None and value > maximum:
        results.append(
            _runtime_error(
                role_name,
                route.route_id,
                capability,
                f"Route {capability} must be no more than {maximum:g}",
                "runtime_setting_invalid",
            )
        )
    return results


def _int_capability(route: ProviderRoute, key: str) -> int | None:
    value = _capability_value(route, key)
    return value if isinstance(value, int) and value >= 0 else None


def _capability_supported(route: ProviderRoute, key: str) -> bool:
    capability = route.capabilities.get(key)
    if capability is None:
        return False
    value = capability.value
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        supported = value.get("supported")
        return bool(supported) if isinstance(supported, bool) else True
    return bool(value)


def _capability_known_unsupported(route: ProviderRoute, key: str) -> bool:
    capability = route.capabilities.get(key)
    if capability is None:
        return False
    value = capability.value
    if isinstance(value, bool):
        return not value
    if isinstance(value, dict):
        supported = value.get("supported")
        return supported is False
    return False


def _capability_numeric_min(route: ProviderRoute, key: str) -> float | None:
    capability = route.capabilities.get(key)
    if capability is None:
        return None
    value = capability.value
    if isinstance(value, dict):
        raw = value.get("min")
        return float(raw) if isinstance(raw, int | float) else None
    return None


def _capability_numeric_max(route: ProviderRoute, key: str) -> float | None:
    capability = route.capabilities.get(key)
    if capability is None:
        return None
    value = capability.value
    if isinstance(value, dict):
        raw = value.get("max")
        return float(raw) if isinstance(raw, int | float) else None
    return None


def _capability_allowed_values(route: ProviderRoute, key: str) -> list[str]:
    capability = route.capabilities.get(key)
    if capability is None or not isinstance(capability.value, dict):
        return []
    values = capability.value.get("values")
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, str)]


def _capability_min(route: ProviderRoute, key: str) -> int | None:
    capability = route.capabilities.get(key)
    if capability is None:
        return None
    value = capability.value
    if isinstance(value, dict):
        raw = value.get("min")
        return raw if isinstance(raw, int) and raw >= 0 else None
    return _int_capability(route, key)


def _capability_max(route: ProviderRoute, key: str) -> int | None:
    capability = route.capabilities.get(key)
    if capability is None:
        return None
    value = capability.value
    if isinstance(value, dict):
        raw = value.get("max")
        return raw if isinstance(raw, int) and raw >= 0 else None
    return _int_capability(route, key)


def _capability_default(route: ProviderRoute, key: str) -> int | None:
    capability = route.capabilities.get(key)
    if capability is None:
        return None
    value = capability.value
    if isinstance(value, dict):
        raw = value.get("default")
        return raw if isinstance(raw, int) and raw >= 0 else None
    return _int_capability(route, key)


def _bool_capability(route: ProviderRoute, key: str) -> bool:
    return bool(_capability_value(route, key))


def _capability_value(route: ProviderRoute, key: str) -> Any:
    capability = route.capabilities.get(key)
    return capability.value if capability is not None else None
