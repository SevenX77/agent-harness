"""Studio's route-state projection must DELEGATE to the gateway projector.

Hard architectural constraint: Studio only renders gateway facts; it never
self-computes the 6-state vocabulary. These tests pin that the Studio adapter
calls the canonical ``graph_agent_gateway.state_projection.project_route_state``
(rather than reimplementing the branching inline) and faithfully maps every
state — including ``historical_ready`` — back into the Studio-facing shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import app.core.adapters.gateway as gateway_module
from app.core.adapters.gateway import GatewayAdapter, ProviderModelStateProjection
from app.models.llm_config import ProviderEndpoint, ProviderRoute
from app.services.llm_health_store import RuntimeCircuit
from graph_agent_gateway.state_projection import (
    ProviderModelStateProjection as GatewayProjection,
)


def _endpoint(
    *,
    status: str = "verified",
    api_key: str | None = "secret",
    metadata: dict[str, Any] | None = None,
    last_test_message: str | None = None,
) -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id="ep-1",
        display_name="Endpoint One",
        protocol="openai_compatible",
        base_url="https://example.test/v1",
        api_key=api_key,
        status=status,
        metadata=metadata or {},
        last_test_message=last_test_message,
    )


def _route(
    *,
    status: str = "verified",
    metadata: dict[str, Any] | None = None,
) -> ProviderRoute:
    return ProviderRoute(
        route_id="ep-1:gpt-5",
        endpoint_id="ep-1",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        display_name="GPT-5",
        status=status,
        metadata=metadata or {},
    )


def _circuit(*, retry_at: datetime, reason_code: str = "rate_limited", message: str | None = "cooling") -> RuntimeCircuit:
    return RuntimeCircuit(
        scope="route",
        scope_id="ep-1:gpt-5",
        opened_at=retry_at - timedelta(seconds=60),
        retry_at=retry_at,
        ttl_seconds=60,
        reason_code=reason_code,
        message=message,
    )


def _project(adapter: GatewayAdapter, *, endpoint: ProviderEndpoint, route: ProviderRoute, circuits: list[RuntimeCircuit], now: datetime) -> ProviderModelStateProjection:
    return adapter.project_route_state(
        {
            "endpoint": endpoint,
            "route": route,
            "circuits": circuits,
            "now": now,
        }
    )


def test_studio_delegates_to_gateway_projector_with_derived_inputs(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> GatewayProjection:
        captured.update(kwargs)
        return GatewayProjection(route_id=kwargs["route_id"], ui_state="ready")

    monkeypatch.setattr(gateway_module, "gateway_project_route_state", _spy)

    adapter = GatewayAdapter(transport="in_process")
    now = datetime.now(UTC)
    endpoint = _endpoint(status="verified", api_key="secret")
    route = _route(status="verified")

    result = _project(adapter, endpoint=endpoint, route=route, circuits=[], now=now)

    # The gateway projector decided the state; Studio rendered it.
    assert result.ui_state == "ready"
    # Studio faithfully derived the projector inputs from stored facts.
    assert captured["route_id"] == "ep-1:gpt-5"
    assert captured["endpoint_status"] == "verified"
    assert captured["route_status"] == "verified"
    assert captured["credential_available"] is True
    assert captured["circuit_retry_at"] is None
    assert captured["draft_history"] is False


def test_studio_renders_historical_ready_when_gateway_returns_it(monkeypatch) -> None:
    # historical_ready is only reachable through the gateway projector; Studio
    # must not fabricate it but MUST surface it when the projector returns it.
    seen_draft_history: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> GatewayProjection:
        seen_draft_history["draft_history"] = kwargs["draft_history"]
        return GatewayProjection(route_id=kwargs["route_id"], ui_state="historical_ready")

    monkeypatch.setattr(gateway_module, "gateway_project_route_state", _spy)

    adapter = GatewayAdapter(transport="in_process")
    now = datetime.now(UTC)
    # A draft-history signal carried on route metadata flows through faithfully.
    endpoint = _endpoint(status="verified")
    route = _route(status="unverified_manual", metadata={"draft_history": True})

    result = _project(adapter, endpoint=endpoint, route=route, circuits=[], now=now)

    assert seen_draft_history["draft_history"] is True
    assert result.ui_state == "historical_ready"


def test_studio_maps_cooling_down_circuit_facts_onto_gateway_state(monkeypatch) -> None:
    def _spy(**kwargs: Any) -> GatewayProjection:
        # Gateway decides cooling_down from the retry_at Studio passed in.
        assert kwargs["circuit_retry_at"] is not None
        return GatewayProjection(
            route_id=kwargs["route_id"],
            ui_state="cooling_down",
            retry_at=kwargs["circuit_retry_at"],
        )

    monkeypatch.setattr(gateway_module, "gateway_project_route_state", _spy)

    adapter = GatewayAdapter(transport="in_process")
    now = datetime.now(UTC)
    retry_at = now + timedelta(seconds=120)
    endpoint = _endpoint(status="verified")
    route = _route(status="verified")
    circuit = _circuit(retry_at=retry_at, reason_code="rate_limited", message="slow down")

    result = _project(adapter, endpoint=endpoint, route=route, circuits=[circuit], now=now)

    assert result.ui_state == "cooling_down"
    # Studio decorates the gateway-decided state with the circuit's own facts.
    assert result.reason_code == "rate_limited"
    assert result.retry_at == retry_at.isoformat()
    assert result.ui_detail == "slow down"


def test_studio_maps_failed_endpoint_reason_and_detail_onto_gateway_state(monkeypatch) -> None:
    def _spy(**kwargs: Any) -> GatewayProjection:
        return GatewayProjection(
            route_id=kwargs["route_id"], ui_state="failed", reason_code="endpoint_unreachable"
        )

    monkeypatch.setattr(gateway_module, "gateway_project_route_state", _spy)

    adapter = GatewayAdapter(transport="in_process")
    now = datetime.now(UTC)
    endpoint = _endpoint(
        status="failed",
        metadata={"reason_code": "endpoint_dns_error"},
        last_test_message="DNS lookup failed",
    )
    route = _route(status="verified")

    result = _project(adapter, endpoint=endpoint, route=route, circuits=[], now=now)

    assert result.ui_state == "failed"
    # Studio prefers its stored failure facts over the canonical fallback.
    assert result.reason_code == "endpoint_dns_error"
    assert result.ui_detail == "DNS lookup failed"


def test_six_states_project_through_gateway_for_their_canonical_inputs() -> None:
    # End-to-end (no spy): the real gateway projector must still produce each of
    # the six states for the same inputs the old inline copy handled.
    adapter = GatewayAdapter(transport="in_process")
    now = datetime.now(UTC)

    off = _project(adapter, endpoint=_endpoint(status="disabled"), route=_route(status="verified"), circuits=[], now=now)
    assert off.ui_state == "off"

    failed_route = _project(
        adapter,
        endpoint=_endpoint(status="verified"),
        route=_route(status="failed", metadata={"reason_code": "model_failed"}),
        circuits=[],
        now=now,
    )
    assert failed_route.ui_state == "failed"
    assert failed_route.reason_code == "model_failed"

    missing_config = _project(
        adapter,
        endpoint=_endpoint(status="unverified_manual", api_key=None),
        route=_route(status="verified"),
        circuits=[],
        now=now,
    )
    assert missing_config.ui_state == "failed"
    assert missing_config.reason_code == "missing_config"

    cooling = _project(
        adapter,
        endpoint=_endpoint(status="verified"),
        route=_route(status="verified"),
        circuits=[_circuit(retry_at=now + timedelta(seconds=90))],
        now=now,
    )
    assert cooling.ui_state == "cooling_down"

    ready = _project(adapter, endpoint=_endpoint(status="verified"), route=_route(status="verified"), circuits=[], now=now)
    assert ready.ui_state == "ready"

    untested = _project(
        adapter,
        endpoint=_endpoint(status="verified"),
        route=_route(status="unverified_manual"),
        circuits=[],
        now=now,
    )
    assert untested.ui_state == "untested"

    historical = _project(
        adapter,
        endpoint=_endpoint(status="verified"),
        route=_route(status="unverified_manual", metadata={"draft_history": True}),
        circuits=[],
        now=now,
    )
    assert historical.ui_state == "historical_ready"
