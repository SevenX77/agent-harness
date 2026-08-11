"""GraphAgent Gateway public package."""

from __future__ import annotations

from graph_agent_gateway.call import (
    ANSWER_RESTARTED,
    GatewayChatModel,
    ModelResolver,
    ModelResolverProtocol,
    answer_restarts_here,
)
from graph_agent_gateway.errors import (
    AllProvidersFailedError,
    GatewayResolverMissingError,
    GatewayRoleNotConfiguredError,
)
from graph_agent_gateway.events import LLMRouteDecisionEvent, RouteDecision
from graph_agent_gateway.registry import (
    CredentialResolveError,
    CredentialResolveRequest,
    CredentialResolveResponse,
    MaterializedProbeCatalogCandidates,
    ProbeCatalogStore,
    PromotableRouteUpdate,
    ProviderModelStateProjection,
    ResolvedRole,
    ResolvedRoute,
    known_model_ids_for_endpoint,
    known_verified_capabilities,
    materialize_probe_catalog_candidates,
    merge_evidence_library,
    probe_priority,
    project_route_state,
    promotable_route_update,
)
from graph_agent_gateway.resolve import (
    FallbackDecision,
    FallbackDecisionRequest,
    ResolvedRouteChain,
    RouteSkipDiagnostic,
    decide_fallback,
)
from graph_agent_gateway.role import (
    MaterializedRole,
    MaterializeRoleRequest,
    materialize_role,
)

__all__ = [
    "AllProvidersFailedError",
    "CredentialResolveError",
    "CredentialResolveRequest",
    "CredentialResolveResponse",
    "FallbackDecision",
    "FallbackDecisionRequest",
    "ANSWER_RESTARTED",
    "GatewayChatModel",
    "answer_restarts_here",
    "GatewayResolverMissingError",
    "GatewayRoleNotConfiguredError",
    "LLMRouteDecisionEvent",
    "RouteDecision",
    "MaterializeRoleRequest",
    "MaterializedProbeCatalogCandidates",
    "MaterializedRole",
    "ModelResolver",
    "ModelResolverProtocol",
    "ProbeCatalogStore",
    "ProviderModelStateProjection",
    "PromotableRouteUpdate",
    "ResolvedRole",
    "ResolvedRoute",
    "ResolvedRouteChain",
    "RouteSkipDiagnostic",
    "decide_fallback",
    "known_model_ids_for_endpoint",
    "known_verified_capabilities",
    "materialize_probe_catalog_candidates",
    "materialize_role",
    "merge_evidence_library",
    "probe_priority",
    "project_route_state",
    "promotable_route_update",
]
