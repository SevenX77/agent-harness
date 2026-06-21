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


def _classification(action: str, *, status_code: int | None = None) -> dict[str, object]:
    return {
        "action": action,
        "scope": "request" if action == "fail_request" else "endpoint",
        "error_class": "ProviderStatusError",
        "status_code": status_code,
        "route_id": "primary:gpt-5",
        "message": "classified by Gateway error-classification SSOT",
        "retryable": action == "retry_same_route",
        "fallback_eligible": action == "fallback_route",
    }


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
            error_context={"classification": _classification("fallback_route", status_code=401)},
        )
    )

    assert decision.action == "switch_route"
    assert decision.next_route_id == "fallback:gpt-5-mini"


def test_public_chain_decide_fallback_retries_current_route_from_classification_contract() -> None:
    from graph_agent_gateway.fallback_decision import (
        FallbackDecisionRequest,
        decide_fallback,
    )

    decision = decide_fallback(
        FallbackDecisionRequest(
            chain=_chain(),
            current_route_id="primary:gpt-5",
            attempt=1,
            error_context={"classification": _classification("retry_same_route", status_code=503)},
        )
    )

    assert decision.action == "retry_same"
    assert decision.next_route_id == "primary:gpt-5"
    assert decision.reason_code == "classification_retry_same_route"


def test_public_decide_fallback_fail_fast_from_classification_contract() -> None:
    from graph_agent_gateway.fallback_decision import (
        FallbackDecisionRequest,
        decide_fallback,
    )

    decision = decide_fallback(
        FallbackDecisionRequest(
            chain=_chain(),
            current_route_id="primary:gpt-5",
            attempt=1,
            error_context={"classification": _classification("fail_request", status_code=413)},
        )
    )

    assert decision.action == "fail_fast"
    assert decision.reason_code == "classification_fail_request"
    assert decision.error_code == "gateway.fail_fast"
    assert decision.error_payload is not None
    assert decision.error_payload["classification"]["action"] == "fail_request"


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
            error_context={"classification": _classification("fallback_route", status_code=404)},
        )
    )

    assert decision.action == "give_up"
    assert decision.error_code == "resource.no_available_route"
    assert isinstance(decision.error_payload, dict)
    assert decision.error_payload["role"] == "graph_agent"


def test_public_decide_fallback_retries_retryable_current_route() -> None:
    from graph_agent_gateway.fallback_decision import (
        FallbackDecisionRequest,
        decide_fallback,
    )

    decision = decide_fallback(
        FallbackDecisionRequest(
            route_ids=["primary:gpt-5", "fallback:gpt-5-mini"],
            role="graph_agent",
            current_route_id="primary:gpt-5",
            attempt=1,
            failed_route_ids=[],
            error_context={"status_code": 503},
        )
    )

    assert decision.action == "retry_same"
    assert decision.next_route_id == "primary:gpt-5"
    assert decision.reason_code == "classification_retry_same_route"


def test_public_decide_fallback_skips_failed_routes_and_reports_exhaustion() -> None:
    from graph_agent_gateway.fallback_decision import (
        FallbackDecisionRequest,
        decide_fallback,
    )

    decision = decide_fallback(
        FallbackDecisionRequest(
            route_ids=["primary:gpt-5", "fallback:gpt-5-mini"],
            role="graph_agent",
            current_route_id="fallback:gpt-5-mini",
            attempt=2,
            failed_route_ids=["primary:gpt-5", "fallback:gpt-5-mini"],
            error_context={"status_code": 503},
        )
    )

    assert decision.action == "give_up"
    assert decision.error_code == "resource.no_available_route"
    assert decision.error_payload == {
        "role": "graph_agent",
        "route_ids": ["primary:gpt-5", "fallback:gpt-5-mini"],
        "failed_route_ids": ["fallback:gpt-5-mini", "primary:gpt-5"],
    }


def test_public_decide_fallback_empty_route_ids_is_canonical_terminal_error() -> None:
    from graph_agent_gateway.fallback_decision import (
        FallbackDecisionRequest,
        decide_fallback,
    )

    decision = decide_fallback(
        FallbackDecisionRequest(
            route_ids=[],
            role="empty_role",
            current_route_id="",
            failed_route_ids=[],
            error_context={"error_type": "EmptyRouteChain"},
        )
    )

    assert decision.action == "give_up"
    assert decision.reason_code == "all_routes_failed"
    assert decision.error_code == "resource.no_available_route"
    assert decision.error_payload == {
        "role": "empty_role",
        "route_ids": [],
        "failed_route_ids": [],
    }
