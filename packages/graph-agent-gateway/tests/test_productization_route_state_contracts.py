"""MVP1 productization contracts for Gateway route, fallback, and state DTOs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

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


def test_resolved_role_to_route_chain_projects_empty_role_terminal_error() -> None:
    from graph_agent_gateway.registry.schema import ResolvedRole, RuntimePolicy, SkippedRoute
    from graph_agent_gateway.route_handoff import resolved_role_to_route_chain

    chain = resolved_role_to_route_chain(
        ResolvedRole(
            role_name="graph_agent",
            runtime_policy=RuntimePolicy(),
            routes=[],
            skipped_diagnostics=[
                SkippedRoute(
                    route_id="missing:gpt-5",
                    reason_code="route_missing",
                    message="route is not configured",
                    from_override=False,
                )
            ],
        )
    )

    assert chain.error_code == "resource.no_available_route"
    assert chain.error_payload == {"role": "graph_agent"}
    assert chain.skipped[0].route_id == "missing:gpt-5"
    assert chain.skipped[0].reason_code == "route_missing"


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
        error_code="resource.no_available_route",
        error_payload={"role": "graph_agent", "failed_routes": ["openai:gpt-5"]},
    )

    assert decision.action == "give_up"
    assert decision.error_code == "resource.no_available_route"
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


def test_probe_verified_evidence_projects_historical_ready_with_evidence_ref() -> None:
    from graph_agent_gateway.registry.schema import EvidenceRecord
    from graph_agent_gateway.state_projection import project_route_state_from_evidence

    projection = project_route_state_from_evidence(
        route_id="openai:gpt-5",
        endpoint_status="verified",
        route_status="unverified_manual",
        credential_available=True,
        evidence_records=[
            EvidenceRecord(
                evidence_id="probe-openai-gpt5",
                evidence_type="probe",
                trust_state="probe-verified",
                route_id="openai:gpt-5",
                endpoint_id="openai",
                model_id="gpt-5",
                provider_model_id="gpt-5",
                probe_status="ok",
            )
        ],
    )

    assert projection.ui_state == "historical_ready"
    assert projection.evidence_refs == ["probe-openai-gpt5"]


@pytest.mark.parametrize(
    ("endpoint_status", "route_status", "credential_available", "circuit_retry_at", "expected_state"),
    [
        ("disabled", "unverified_manual", True, None, "off"),
        ("verified", "failed", True, None, "failed"),
        ("verified", "unverified_manual", False, None, "failed"),
        ("verified", "unverified_manual", True, datetime.now(UTC) + timedelta(seconds=30), "cooling_down"),
    ],
)
def test_probe_verified_evidence_does_not_override_terminal_or_cooling_states(
    endpoint_status: str,
    route_status: str,
    credential_available: bool,
    circuit_retry_at: datetime | None,
    expected_state: str,
) -> None:
    from graph_agent_gateway.registry.schema import EvidenceRecord
    from graph_agent_gateway.state_projection import project_route_state_from_evidence

    projection = project_route_state_from_evidence(
        route_id="openai:gpt-5",
        endpoint_status=endpoint_status,
        route_status=route_status,
        credential_available=credential_available,
        circuit_retry_at=circuit_retry_at,
        evidence_records=[
            EvidenceRecord(
                evidence_id="probe-openai-gpt5",
                evidence_type="probe",
                trust_state="probe-verified",
                route_id="openai:gpt-5",
                endpoint_id="openai",
                model_id="gpt-5",
                provider_model_id="gpt-5",
                probe_status="ok",
            )
        ],
    )

    assert projection.ui_state == expected_state
    assert projection.evidence_refs == []


def test_role_materialization_delegates_probe_evidence_to_gateway_projection(monkeypatch) -> None:
    import graph_agent_gateway.role_materialization as role_materialization
    from graph_agent_gateway.registry.schema import EvidenceRecord, ProviderEndpoint, ProviderRoute
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role
    from graph_agent_gateway.state_projection import ProviderModelStateProjection

    evidence = EvidenceRecord(
        evidence_id="probe-openai-gpt5",
        evidence_type="probe",
        trust_state="probe-verified",
        route_id="openai:gpt-5",
        endpoint_id="openai",
        model_id="gpt-5",
        provider_model_id="gpt-5",
        probe_status="ok",
    )
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> ProviderModelStateProjection:
        captured.update(kwargs)
        return ProviderModelStateProjection(
            route_id=kwargs["route_id"],
            ui_state="historical_ready",
            evidence_refs=[record.evidence_id for record in kwargs["evidence_records"]],
        )

    monkeypatch.setattr(role_materialization, "project_route_state_from_evidence", _spy)

    result = materialize_role(
        MaterializeRoleRequest(
            role=SimpleNamespace(
                model_groups=[
                    SimpleNamespace(
                        canonical_id="gpt-5",
                        provider_models=[SimpleNamespace(route_id="openai:gpt-5")],
                    )
                ],
                model_fallback_enabled=True,
            ),
            credentials=SimpleNamespace(
                provider_endpoints={
                    "openai": ProviderEndpoint(
                        endpoint_id="openai",
                        protocol="openai_compatible",
                        base_url="https://api.openai.example/v1",
                        api_key="secret",
                        status="verified",
                    )
                },
                provider_routes={
                    "openai:gpt-5": ProviderRoute(
                        route_id="openai:gpt-5",
                        endpoint_id="openai",
                        route_slug="gpt-5",
                        provider_model_id="gpt-5",
                        canonical_id="gpt-5",
                        status="unverified_manual",
                    )
                },
            ),
            evidence_records=[evidence],
            health_store=SimpleNamespace(get_active_circuits=lambda **_: []),
            now=datetime.now(UTC),
        )
    )

    assert captured["evidence_records"] == [evidence]
    assert result.fallback_chain[0].route_id == "openai:gpt-5"
