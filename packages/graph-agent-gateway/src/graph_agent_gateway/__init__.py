"""GraphAgent Gateway public package."""

from __future__ import annotations

from graph_agent_gateway.credential_resolver import (
    CredentialResolveError,
    CredentialResolveRequest,
    CredentialResolveResponse,
)
from graph_agent_gateway.events import LLMRouteDecisionEvent, RouteDecision
from graph_agent_gateway.exceptions import (
    AllProvidersFailedError,
    GatewayResolverMissingError,
    GatewayRoleNotConfiguredError,
)
from graph_agent_gateway.fallback_decision import (
    FallbackDecision,
    FallbackDecisionRequest,
    decide_fallback,
)
from graph_agent_gateway.gateway_chat_model import (
    ANSWER_RESTARTED,
    GatewayChatModel,
    answer_restarts_here,
)
from graph_agent_gateway.probe_catalog import (
    MaterializedProbeCatalogCandidates,
    ProbeCatalogStore,
    PromotableRouteUpdate,
    known_model_ids_for_endpoint,
    known_verified_capabilities,
    materialize_probe_catalog_candidates,
    merge_evidence_library,
    probe_priority,
    promotable_route_update,
)
from graph_agent_gateway.protocol import ModelResolverProtocol
from graph_agent_gateway.registry.schema import ResolvedRole, ResolvedRoute
from graph_agent_gateway.resolver import ModelResolver
from graph_agent_gateway.role_materialization import (
    MaterializedRoleResult,
    MaterializeRoleRequest,
    materialize_role,
)
from graph_agent_gateway.route_handoff import ResolvedRouteChain, RouteSkipDiagnostic
from graph_agent_gateway.state_projection import (
    ProviderModelStateProjection,
    project_route_state,
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
    "MaterializedRoleResult",
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
