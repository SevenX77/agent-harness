"""Gateway package boundary tests for Provider Intelligence V2 phase 1."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

GATEWAY_SRC = Path(__file__).resolve().parents[1] / "src" / "graph_agent_gateway"
REPO_ROOT = Path(__file__).resolve().parents[3]
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


def test_gateway_errors_join_the_engine_family_unconditionally() -> None:
    """Catalog membership is a postcondition, so it may not have an off switch.

    ``docs/engine/public-api-contract.md`` states that ``GatewayError`` and its
    leaves are ``isinstance(..., ModelProviderError)``. That base used to be
    imported under ``try/except`` with a ``RuntimeError`` fallback, so a host
    whose install lacked the engine got a gateway whose errors quietly left the
    catalog — the postcondition held or not depending on the environment, and
    nothing said which. The import is now plain, and this test fails if a
    fallback is reintroduced.
    """
    import graph_agent
    from graph_agent_gateway import errors

    assert issubclass(errors.GatewayError, graph_agent.ModelProviderError)

    module = ast.parse((GATEWAY_SRC / "errors.py").read_text(encoding="utf-8"))
    guarded = [node.lineno for node in module.body if isinstance(node, ast.Try)]
    assert guarded == []


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


def test_the_gateway_reaches_the_engine_only_through_its_public_surface() -> None:
    """The rule is which door, not a list of the doors already tried.

    This replaced a table of three (file, forbidden spelling) pairs — one per
    engine submodule somebody had reached into. A table like that only bars the
    spellings already thought of, while the rule it stands for is the engine's
    own: exactly five error families and a named public surface, imported from
    ``graph_agent`` and nowhere below it.
    """
    offenders: list[str] = []

    for path in sorted(GATEWAY_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders.extend(
                    f"{path.relative_to(GATEWAY_SRC).as_posix()}:{node.lineno}:{alias.name}"
                    for alias in node.names
                    if _is_engine_submodule(alias.name)
                )
            elif isinstance(node, ast.ImportFrom) and _is_engine_submodule(node.module or ""):
                offenders.append(
                    f"{path.relative_to(GATEWAY_SRC).as_posix()}:{node.lineno}:{node.module}"
                )

    assert offenders == []


def test_the_engine_does_not_declare_the_gateway_it_may_not_import() -> None:
    """A dependency nothing may import is not a dependency.

    The engine's own ``test_engine_source_has_no_gateway_concrete_imports``
    forbids its source from importing the gateway, yet its manifest declared
    ``graph-agent-gateway`` — an edge no engine code was allowed to use, in the
    opposite direction from the one the error catalog actually needs. It also
    handed the gateway to anyone who installed the engine, which is how the
    Studio backend came to import a distribution it never named. Declaring the
    gateway's own edge to the engine (see the manifest test below) would have
    closed that pair into a cycle.
    """
    engine = _declared_distributions(REPO_ROOT / "packages" / "graph-agent" / "pyproject.toml")

    assert "graph-agent-gateway" not in engine


def test_the_gateway_declares_the_engine_its_errors_inherit_from() -> None:
    gateway = _declared_distributions(
        REPO_ROOT / "packages" / "graph-agent-gateway" / "pyproject.toml"
    )

    assert "graph-agent" in gateway


def test_gateway_init_does_not_import_the_factory_module() -> None:
    source = (GATEWAY_SRC / "__init__.py").read_text(encoding="utf-8")

    assert "from graph_agent_gateway import factory" not in source


def _is_engine_submodule(name: str) -> bool:
    # `graph_agent` itself is the public surface and allowed;
    # `graph_agent_gateway` shares the prefix and is not the engine at all.
    return name.startswith("graph_agent.")


def _declared_distributions(manifest: Path) -> set[str]:
    project = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]
    requirements: list[str] = list(project.get("dependencies") or [])
    for extra in (project.get("optional-dependencies") or {}).values():
        requirements.extend(extra)
    return {_distribution_name(requirement) for requirement in requirements}


def _distribution_name(requirement: str) -> str:
    name = requirement.strip()
    for separator in ("[", "<", ">", "=", "!", "~", ";", " "):
        name = name.split(separator, 1)[0]
    return name.strip().lower().replace("_", "-")


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
