"""Gateway package boundary tests for Provider Intelligence V2 phase 1."""

from __future__ import annotations

from pathlib import Path

GATEWAY_SRC = Path(__file__).resolve().parents[1] / "src" / "graph_agent_gateway"
ROUTE_DECISION_EVENT_CODE = "[F-v3-gateway-llm-route-decision]"


def test_gateway_owns_route_decision_event_schema() -> None:
    from graph_agent_gateway.call import build_route_decision_event
    from graph_agent_gateway.events import LLMRouteDecisionEvent
    from graph_agent_gateway.registry import ResolvedRoute

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
    from graph_agent_gateway.errors import GatewayError

    assert "ExecutionError" not in {base.__name__ for base in GatewayError.__mro__}


def test_gateway_runtime_surface_does_not_export_factory() -> None:
    import graph_agent_gateway

    assert not hasattr(graph_agent_gateway, "factory")
    assert "factory" not in graph_agent_gateway.__all__


def test_gateway_runtime_surface_exports_route_handoff_dtos() -> None:
    import graph_agent_gateway
    from graph_agent_gateway.registry import ResolvedRole, ResolvedRoute

    assert graph_agent_gateway.ResolvedRole is ResolvedRole
    assert graph_agent_gateway.ResolvedRoute is ResolvedRoute
    assert "ResolvedRole" in graph_agent_gateway.__all__
    assert "ResolvedRoute" in graph_agent_gateway.__all__


def test_gateway_public_facade_exports_mvp1_owner_api() -> None:
    import graph_agent_gateway as gw
    from graph_agent_gateway.registry import (
        CredentialResolveError,
        CredentialResolveRequest,
        CredentialResolveResponse,
        MaterializedProbeCatalogCandidates,
        ProbeCatalogStore,
        PromotableRouteUpdate,
        ProviderModelStateProjection,
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
        "MaterializedRole": MaterializedRole,
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
    from graph_agent_gateway.registry import SkippedRoute

    assert registry.SkippedRoute is SkippedRoute
    assert "SkippedRoute" in registry.__all__


def test_gateway_phase1_has_no_engine_internal_imports() -> None:
    forbidden = {
        "errors.py": "graph_agent.core.exceptions",
        "call/tracing.py": "graph_agent.callbacks.events",
        "call/resolver.py": "graph_agent.core._predict_internal",
        "__init__.py": "from graph_agent_gateway import factory",
    }

    for relative_path, forbidden_text in forbidden.items():
        source = (GATEWAY_SRC / relative_path).read_text(encoding="utf-8")
        assert forbidden_text not in source


# A domain answers for itself through the package it lives in. Reaching past
# that into one of its files binds the caller to where a definition happens to
# sit today, and every rearrangement inside the domain then becomes everyone
# else's problem — which is exactly how 531 import statements came to depend on
# the gateway's internal layout. Decision:
# docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md (D4).
#
# Each name below is a module the registry package still holds but does not own:
# it moves to its final domain in a later phase, and this set shrinks to empty
# there. Nothing may be ADDED to it.
_SETTLED_DOMAINS = ("registry", "resolve", "role", "call", "dialect", "probing")

# Modules a settled domain held but did not own. The tree is whole: every module
# sits in the domain that owns it, and this set stays empty. Nothing may be
# added to it — a module with nowhere to live is a domain that has not been
# named yet, not an exception to make.
_AWAITING_REHOME: set[str] = set()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCANNED_TREES = (
    "packages/graph-agent-gateway/src",
    "packages/graph-agent-gateway/tests",
    "packages/graph-agent/src",
    "packages/graph-agent/tests",
    "apps/studio/backend/app",
    "apps/studio/backend/tests",
)


def _deep_domain_imports() -> list[str]:
    import ast

    domain_dirs = {name: GATEWAY_SRC / name for name in _SETTLED_DOMAINS}
    offences: list[str] = []
    for tree_name in _SCANNED_TREES:
        tree_root = _REPO_ROOT / tree_name
        if not tree_root.exists():
            continue
        for source_path in tree_root.rglob("*.py"):
            for domain, domain_dir in domain_dirs.items():
                if domain_dir in source_path.parents:
                    own_domain = domain
                    break
            else:
                own_domain = None
            try:
                parsed = ast.parse(source_path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - a broken file fails elsewhere
                continue
            for node in ast.walk(parsed):
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                    imported = tuple(alias.name for alias in node.names)
                elif isinstance(node, ast.Import):
                    module = node.names[0].name
                    imported = ()
                else:
                    continue
                for domain in _SETTLED_DOMAINS:
                    prefix = f"graph_agent_gateway.{domain}."
                    if not module.startswith(prefix):
                        continue
                    if domain == own_domain:
                        continue  # inside the domain, its own files are its own business
                    if module[len("graph_agent_gateway.") :] in _AWAITING_REHOME:
                        continue
                    if "tests" in source_path.parts and (
                        not imported or all(name.startswith("_") for name in imported)
                    ):
                        # A test may name the file: a private name is in no package
                        # contract, and patching one requires the module object. The
                        # exemption stops at tests — shipping code binding itself to
                        # where a definition sits today is the thing being prevented.
                        continue
                    offences.append(
                        f"{source_path.relative_to(_REPO_ROOT)}:{node.lineno} imports {module}"
                    )
    return offences


def test_nobody_outside_a_settled_domain_imports_its_files() -> None:
    offences = _deep_domain_imports()

    assert offences == [], (
        "import a domain through graph_agent_gateway.<domain>, not through the "
        "file a name happens to live in:\n  " + "\n  ".join(offences)
    )
