"""Capability linting for explicit route chains."""

from __future__ import annotations

from graph_agent_gateway.registry.schema import LintResult, ProviderRoute, RoleEntry

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
