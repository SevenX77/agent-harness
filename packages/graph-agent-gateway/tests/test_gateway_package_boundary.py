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
