"""MVP1 productization RED tests for public fallback decision behavior."""

from __future__ import annotations


def _resolved_route(route_id: str):
    from graph_agent_gateway.registry.schema import ResolvedRoute

    endpoint_id, route_slug = route_id.split(":", 1)
    return ResolvedRoute(
        role_name="graph_agent",
        route_id=route_id,
        endpoint_id=endpoint_id,
        protocol="openai_compatible",
        base_url=f"https://{endpoint_id}.example/v1",
        credential_ref=f"credential:{endpoint_id}",
        credential_fingerprint=f"{endpoint_id}-fingerprint",
        provider_model_id=route_slug,
        canonical_id=route_slug,
    )


def _chain():
    from graph_agent_gateway.route_handoff import ResolvedRouteChain

    return ResolvedRouteChain(
        role="graph_agent",
        routes=[_resolved_route("primary:gpt-5"), _resolved_route("fallback:gpt-5-mini")],
        skipped=[],
    )


def test_public_decide_fallback_switches_to_next_route() -> None:
    from graph_agent_gateway.fallback_decision import (
        FallbackDecisionRequest,
        decide_fallback,
    )

    decision = decide_fallback(
        FallbackDecisionRequest(
            chain=_chain(),
            current_route_id="primary:gpt-5",
            attempt=1,
            error_context={"error_type": "TimeoutError"},
        )
    )

    assert decision.action == "switch_route"
    assert decision.next_route_id == "fallback:gpt-5-mini"


def test_public_decide_fallback_give_up_is_terminal_error() -> None:
    from graph_agent_gateway.fallback_decision import (
        FallbackDecisionRequest,
        decide_fallback,
    )

    decision = decide_fallback(
        FallbackDecisionRequest(
            chain=_chain(),
            current_route_id="fallback:gpt-5-mini",
            attempt=1,
            error_context={"error_type": "ProviderError"},
        )
    )

    assert decision.action == "give_up"
    assert decision.error_code == "fallback.give_up"
    assert isinstance(decision.error_payload, dict)
    assert decision.error_payload["role"] == "graph_agent"
