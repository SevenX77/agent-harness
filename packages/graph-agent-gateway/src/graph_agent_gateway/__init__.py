"""GraphAgent Gateway public package."""

from __future__ import annotations

from graph_agent_gateway.credential_resolver import (
    CredentialResolveError,
    CredentialResolveRequest,
    CredentialResolveResponse,
)
from graph_agent_gateway.events import LLMFallbackEvent
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
from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.import_draft_store import (
    ImportDraftStore,
    MaterializedImportDraftCandidates,
    materialize_import_draft_candidates,
    merge_evidence_library,
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
    project_route_state_from_evidence,
)

__all__ = [
    "AllProvidersFailedError",
    "CredentialResolveError",
    "CredentialResolveRequest",
    "CredentialResolveResponse",
    "FallbackDecision",
    "FallbackDecisionRequest",
    "GatewayChatModel",
    "GatewayResolverMissingError",
    "GatewayRoleNotConfiguredError",
    "ImportDraftStore",
    "LLMFallbackEvent",
    "MaterializeRoleRequest",
    "MaterializedImportDraftCandidates",
    "MaterializedRoleResult",
    "ModelResolver",
    "ModelResolverProtocol",
    "ProviderModelStateProjection",
    "ResolvedRole",
    "ResolvedRoute",
    "ResolvedRouteChain",
    "RouteSkipDiagnostic",
    "decide_fallback",
    "materialize_import_draft_candidates",
    "materialize_role",
    "merge_evidence_library",
    "project_route_state",
    "project_route_state_from_evidence",
]
