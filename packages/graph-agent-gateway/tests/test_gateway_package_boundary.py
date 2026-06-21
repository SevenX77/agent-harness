"""Gateway package boundary tests for Provider Intelligence V2 phase 1."""

from __future__ import annotations

from pathlib import Path

GATEWAY_SRC = Path(__file__).resolve().parents[1] / "src" / "graph_agent_gateway"
FALLBACK_EVENT_CODE = "[F-v3-gateway-llm-fallback]"


def test_gateway_owns_llm_fallback_event_schema() -> None:
    from graph_agent_gateway.events import LLMFallbackEvent
    from graph_agent_gateway.tracing import build_llm_fallback_event

    event = build_llm_fallback_event(
        phase_name="draft",
        from_provider="openai/gpt-5",
        to_provider="anthropic/claude-opus",
        reason="RateLimitError: quota exceeded",
        context={"role_name": "balanced"},
    )

    assert isinstance(event, LLMFallbackEvent)
    assert event.phase_name == "draft"
    assert event.from_provider == "openai/gpt-5"
    assert event.to_provider == "anthropic/claude-opus"
    assert event.reason == "RateLimitError: quota exceeded"
    assert event.code == FALLBACK_EVENT_CODE
    assert event.context == {"role_name": "balanced"}


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
    from graph_agent_gateway.import_draft_store import (
        ImportDraftStore,
        MaterializedImportDraftCandidates,
        materialize_import_draft_candidates,
        merge_evidence_library,
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
        project_route_state_from_evidence,
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
        "project_route_state_from_evidence": project_route_state_from_evidence,
        "MaterializeRoleRequest": MaterializeRoleRequest,
        "MaterializedRoleResult": MaterializedRoleResult,
        "materialize_role": materialize_role,
        "ImportDraftStore": ImportDraftStore,
        "MaterializedImportDraftCandidates": MaterializedImportDraftCandidates,
        "materialize_import_draft_candidates": materialize_import_draft_candidates,
        "merge_evidence_library": merge_evidence_library,
    }

    for public_name, expected_symbol in expected_exports.items():
        assert getattr(gw, public_name) is expected_symbol
        assert public_name in gw.__all__


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
