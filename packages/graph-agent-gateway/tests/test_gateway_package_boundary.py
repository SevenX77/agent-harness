"""Gateway package boundary tests for Provider Intelligence V2 phase 1."""

from __future__ import annotations

from pathlib import Path

GATEWAY_SRC = Path(__file__).resolve().parents[1] / "src" / "graph_agent_gateway"
ROUTE_DECISION_EVENT_CODE = "[F-v3-gateway-llm-route-decision]"


def test_gateway_owns_route_decision_event_schema() -> None:
    from graph_agent_gateway.events import LLMRouteDecisionEvent
    from graph_agent_gateway.registry.schema import ResolvedRoute
    from graph_agent_gateway.tracing import build_route_decision_event

    route = ResolvedRoute(
        role_name="balanced",
        route_id="openai:gpt-5",
        endpoint_id="openai",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        credential_ref="endpoint:openai",
        credential_fingerprint="fp",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
    )

    event = build_route_decision_event(
        phase_name="draft",
        decision="fell_back",
        route=route,
        reason="RateLimitError: quota exceeded",
        next_route_id="anthropic:claude-opus",
    )

    assert isinstance(event, LLMRouteDecisionEvent)
    assert event.phase_name == "draft"
    assert event.decision == "fell_back"
    assert event.route_id == "openai:gpt-5"
    assert event.endpoint_id == "openai"
    assert event.provider_model_id == "gpt-5"
    assert event.next_route_id == "anthropic:claude-opus"
    assert event.reason == "RateLimitError: quota exceeded"
    assert event.code == ROUTE_DECISION_EVENT_CODE


def test_gateway_errors_do_not_inherit_engine_execution_error() -> None:
    from graph_agent_gateway.exceptions import GatewayError

    assert "ExecutionError" not in {base.__name__ for base in GatewayError.__mro__}


def test_gateway_runtime_surface_does_not_export_factory() -> None:
    import graph_agent_gateway

    assert not hasattr(graph_agent_gateway, "factory")
    assert "factory" not in graph_agent_gateway.__all__


def test_gateway_runtime_surface_exports_route_handoff_dtos() -> None:
    import graph_agent_gateway
    from graph_agent_gateway.registry.schema import ResolvedRole, ResolvedRoute

    assert graph_agent_gateway.ResolvedRole is ResolvedRole
    assert graph_agent_gateway.ResolvedRoute is ResolvedRoute
    assert "ResolvedRole" in graph_agent_gateway.__all__
    assert "ResolvedRoute" in graph_agent_gateway.__all__


def test_gateway_public_facade_exports_mvp1_owner_api() -> None:
    import graph_agent_gateway as gw
    from graph_agent_gateway.credential_resolver import (
        CredentialResolveError,
        CredentialResolveRequest,
        CredentialResolveResponse,
    )
    from graph_agent_gateway.fallback_decision import (
        FallbackDecision,
        FallbackDecisionRequest,
        decide_fallback,
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

    expected_exports = {
        "ResolvedRouteChain": ResolvedRouteChain,
        "RouteSkipDiagnostic": RouteSkipDiagnostic,
        "FallbackDecision": FallbackDecision,
        "FallbackDecisionRequest": FallbackDecisionRequest,
        "decide_fallback": decide_fallback,
        "CredentialResolveRequest": CredentialResolveRequest,
        "CredentialResolveResponse": CredentialResolveResponse,
        "CredentialResolveError": CredentialResolveError,
        "ProviderModelStateProjection": ProviderModelStateProjection,
        "project_route_state": project_route_state,
        "MaterializeRoleRequest": MaterializeRoleRequest,
        "MaterializedRoleResult": MaterializedRoleResult,
        "materialize_role": materialize_role,
        "ProbeCatalogStore": ProbeCatalogStore,
        "MaterializedProbeCatalogCandidates": MaterializedProbeCatalogCandidates,
        "PromotableRouteUpdate": PromotableRouteUpdate,
        "materialize_probe_catalog_candidates": materialize_probe_catalog_candidates,
        "merge_evidence_library": merge_evidence_library,
        "known_model_ids_for_endpoint": known_model_ids_for_endpoint,
        "known_verified_capabilities": known_verified_capabilities,
        "probe_priority": probe_priority,
        "promotable_route_update": promotable_route_update,
    }

    for public_name, expected_symbol in expected_exports.items():
        assert getattr(gw, public_name) is expected_symbol
        assert public_name in gw.__all__

    assert not hasattr(gw, "project_route_state_from_evidence")


def test_registry_surface_exports_skipped_route_diagnostics() -> None:
    import graph_agent_gateway.registry as registry
    from graph_agent_gateway.registry.schema import SkippedRoute

    assert registry.SkippedRoute is SkippedRoute
    assert "SkippedRoute" in registry.__all__


def test_gateway_phase1_has_no_engine_internal_imports() -> None:
    forbidden = {
        "exceptions.py": "graph_agent.core.exceptions",
        "tracing.py": "graph_agent.callbacks.events",
        "resolver.py": "graph_agent.core._predict_internal",
        "__init__.py": "from graph_agent_gateway import factory",
    }

    for relative_path, forbidden_text in forbidden.items():
        source = (GATEWAY_SRC / relative_path).read_text(encoding="utf-8")
        assert forbidden_text not in source
