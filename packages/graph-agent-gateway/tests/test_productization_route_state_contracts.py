"""MVP1 productization contracts for Gateway route, fallback, and state DTOs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError


def _resolved_route():
    from graph_agent_gateway.registry.schema import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id="openai:gpt-5",
        endpoint_id="openai",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        credential_ref="credential:openai-prod",
        credential_fingerprint="credential-fingerprint",
        provider_model_id="gpt-5",
        canonical_id="openai/gpt-5",
    )


def test_resolved_route_chain_handoff_dto_uses_role_routes_and_skipped() -> None:
    from graph_agent_gateway.route_handoff import ResolvedRouteChain, RouteSkipDiagnostic

    skipped = RouteSkipDiagnostic(
        route_id="anthropic:claude",
        reason_code="credential_missing",
        message="credential is not configured",
        from_override=False,
    )
    chain = ResolvedRouteChain(
        role="graph_agent",
        routes=[_resolved_route()],
        skipped=[skipped],
    )

    dumped = chain.model_dump(mode="json")

    assert list(dumped) == ["role", "routes", "skipped"]
    assert dumped["role"] == "graph_agent"
    assert dumped["routes"][0]["route_id"] == "openai:gpt-5"
    assert dumped["skipped"][0]["reason_code"] == "credential_missing"


def test_empty_route_chain_requires_explicit_error_payload() -> None:
    from graph_agent_gateway.route_handoff import ResolvedRouteChain

    with pytest.raises(ValidationError):
        ResolvedRouteChain(role="graph_agent", routes=[], skipped=[])

    terminal = ResolvedRouteChain(
        role="graph_agent",
        routes=[],
        skipped=[],
        error_code="resource.no_available_route",
        error_payload={"role": "graph_agent", "reason": "no executable route"},
    )

    assert terminal.error_code == "resource.no_available_route"
    assert terminal.error_payload["role"] == "graph_agent"


def test_fallback_decision_action_contract_and_switch_route_target() -> None:
    from graph_agent_gateway.fallback_decision import FallbackDecision

    retry = FallbackDecision(action="retry_same", reason_code="transient_error")
    switch = FallbackDecision(
        action="switch_route",
        next_route_id="fallback:gpt-5-mini",
        reason_code="provider_unavailable",
    )

    assert retry.action == "retry_same"
    assert switch.action == "switch_route"
    assert switch.next_route_id == "fallback:gpt-5-mini"

    with pytest.raises(ValidationError):
        FallbackDecision(action="fallback", reason_code="provider_unavailable")

    with pytest.raises(ValidationError):
        FallbackDecision(action="switch_route", reason_code="provider_unavailable")


def test_give_up_fallback_decision_requires_explicit_terminal_error() -> None:
    from graph_agent_gateway.fallback_decision import FallbackDecision

    with pytest.raises(ValidationError):
        FallbackDecision(action="give_up", reason_code="all_routes_failed")

    decision = FallbackDecision(
        action="give_up",
        reason_code="all_routes_failed",
        error_code="fallback.give_up",
        error_payload={"role": "graph_agent", "failed_routes": ["openai:gpt-5"]},
    )

    assert decision.action == "give_up"
    assert decision.error_code == "fallback.give_up"
    assert decision.error_payload["failed_routes"] == ["openai:gpt-5"]


def test_materialized_role_empty_fallback_chain_requires_explicit_error() -> None:
    from graph_agent_gateway.state_projection import MaterializedRole

    with pytest.raises(ValidationError):
        MaterializedRole(
            role="graph_agent",
            fallback_chain=[],
            warnings=[],
            projections={},
        )

    materialized = MaterializedRole(
        role="graph_agent",
        fallback_chain=[],
        warnings=[],
        projections={},
        error_code="resource.no_available_route",
        error_payload={"role": "graph_agent"},
    )

    assert materialized.error_code == "resource.no_available_route"
    assert materialized.error_payload == {"role": "graph_agent"}


@pytest.mark.parametrize(
    "ui_state",
    ["ready", "historical_ready", "untested", "cooling_down", "off"],
)
def test_non_failed_six_state_projection_does_not_accept_failed_reason(ui_state: str) -> None:
    from graph_agent_gateway.state_projection import ProviderModelStateProjection

    projection = ProviderModelStateProjection(route_id="openai:gpt-5", ui_state=ui_state)
    assert projection.ui_state == ui_state
    assert projection.reason_code is None

    with pytest.raises(ValidationError):
        ProviderModelStateProjection(
            route_id="openai:gpt-5",
            ui_state=ui_state,
            reason_code="missing_config",
        )


@pytest.mark.parametrize(
    "reason_code",
    ["missing_config", "endpoint_unreachable", "model_failed"],
)
def test_failed_six_state_projection_allows_only_declared_reasons(reason_code: str) -> None:
    from graph_agent_gateway.state_projection import ProviderModelStateProjection

    projection = ProviderModelStateProjection(
        route_id="openai:gpt-5",
        ui_state="failed",
        reason_code=reason_code,
    )

    assert projection.ui_state == "failed"
    assert projection.reason_code == reason_code

    with pytest.raises(ValidationError):
        ProviderModelStateProjection(
            route_id="openai:gpt-5",
            ui_state="failed",
            reason_code="missing_key",
        )


def test_cooling_down_projection_carries_retry_at_without_failed_reason() -> None:
    from graph_agent_gateway.state_projection import ProviderModelStateProjection

    retry_at = datetime.now(UTC) + timedelta(seconds=30)
    projection = ProviderModelStateProjection(
        route_id="openai:gpt-5",
        ui_state="cooling_down",
        retry_at=retry_at,
        ui_detail="provider temporarily unavailable",
    )

    assert projection.retry_at == retry_at
    assert projection.reason_code is None
