"""Which route this role's request actually goes down, and what happens when it fails.

This package is the resolve domain's whole public contract: role entry
resolution, capability linting, verified-profile selection, the route handoff
DTOs, runtime error classification and the fallback decision that reads it.
Reaching past it into one of its files couples the caller to where a definition
happens to live today.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
"""

from __future__ import annotations

from graph_agent_gateway.resolve.error_classification import (
    ErrorActionClassification,
    ErrorContext,
    StreamPhase,
    classify_error_context,
    classify_exception,
)
from graph_agent_gateway.resolve.fallback import (
    FallbackDecision,
    FallbackDecisionRequest,
    decide_fallback,
)
from graph_agent_gateway.resolve.handoff import (
    ResolvedRouteChain,
    RouteSkipDiagnostic,
    resolved_role_to_route_chain,
)
from graph_agent_gateway.resolve.lint import capability_key_for_lint, lint_role_routes
from graph_agent_gateway.resolve.profile_selector import (
    ProfileSelectionError,
    select_verified_profile,
)
from graph_agent_gateway.resolve.resolver import (
    RegistryResolutionError,
    materialize_role_entry,
    resolve_role,
)

__all__ = [
    "ErrorActionClassification",
    "ErrorContext",
    "FallbackDecision",
    "FallbackDecisionRequest",
    "ProfileSelectionError",
    "RegistryResolutionError",
    "ResolvedRouteChain",
    "RouteSkipDiagnostic",
    "StreamPhase",
    "capability_key_for_lint",
    "classify_error_context",
    "classify_exception",
    "decide_fallback",
    "lint_role_routes",
    "materialize_role_entry",
    "resolve_role",
    "resolved_role_to_route_chain",
    "select_verified_profile",
]
