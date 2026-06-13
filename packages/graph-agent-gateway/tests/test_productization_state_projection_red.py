"""MVP1 productization RED tests for Gateway-owned state projection."""

from __future__ import annotations


def _resolved_route():
    from graph_agent_gateway.registry.schema import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id="openai:gpt-5",
        endpoint_id="openai",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        credential_ref="credential:openai",
        credential_fingerprint="openai-fingerprint",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
    )


def test_project_route_state_maps_missing_config_to_failed_reason() -> None:
    from graph_agent_gateway.state_projection import project_route_state

    projection = project_route_state(
        route_id="openai:gpt-5",
        endpoint_status="unverified_manual",
        route_status="unverified_manual",
        credential_available=False,
        circuit_retry_at=None,
        draft_history=False,
    )

    assert projection.ui_state == "failed"
    assert projection.reason_code == "missing_config"


def test_materialize_role_skips_failed_routes_and_returns_terminal_error() -> None:
    from graph_agent_gateway.state_projection import (
        ProviderModelStateProjection,
        materialize_role,
    )

    route = _resolved_route()
    materialized = materialize_role(
        role="graph_agent",
        routes=[route],
        projections={
            route.route_id: ProviderModelStateProjection(
                route_id=route.route_id,
                ui_state="failed",
                reason_code="model_failed",
            )
        },
    )

    assert materialized.fallback_chain == []
    assert materialized.error_code == "resource.no_available_route"
    assert materialized.error_payload["role"] == "graph_agent"
