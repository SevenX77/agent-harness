"""Project stored LLM facts and runtime health into Studio UI states."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.models.llm_config import ProviderEndpoint, ProviderRoute
from app.services.llm_health_store import RuntimeCircuit

ProviderUiState = Literal["ready", "untested", "cooling_down", "needs_setup", "off"]


@dataclass(frozen=True)
class ProviderModelStateProjection:
    ui_state: ProviderUiState
    reason_code: str | None = None
    retry_at: str | None = None
    ui_detail: str | None = None


def project_provider_model_state(
    *,
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    circuits: list[RuntimeCircuit],
    now: datetime | None = None,
) -> ProviderModelStateProjection:
    current_time = now or datetime.now(UTC)
    if endpoint.status == "disabled" or route.status == "disabled":
        return ProviderModelStateProjection(ui_state="off")
    setup_reason = _setup_reason(endpoint, route)
    if setup_reason is not None:
        return ProviderModelStateProjection(ui_state="needs_setup", reason_code=setup_reason)
    active_circuit = _select_active_circuit(endpoint, route, circuits, current_time)
    if active_circuit is not None:
        return ProviderModelStateProjection(
            ui_state="cooling_down",
            reason_code=active_circuit.reason_code,
            retry_at=active_circuit.retry_at.isoformat(),
            ui_detail=active_circuit.message,
        )
    if endpoint.status == "verified" and route.status == "verified":
        return ProviderModelStateProjection(ui_state="ready")
    return ProviderModelStateProjection(ui_state="untested")


def _setup_reason(endpoint: ProviderEndpoint, route: ProviderRoute) -> str | None:
    if endpoint.api_key is None or not endpoint.api_key.get_secret_value():
        return "missing_key"
    if endpoint.status == "failed":
        return str(endpoint.metadata.get("reason_code") or "invalid_endpoint")
    if route.status == "failed":
        return str(route.metadata.get("reason_code") or "invalid_model")
    return None


def _select_active_circuit(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    circuits: list[RuntimeCircuit],
    now: datetime,
) -> RuntimeCircuit | None:
    relevant = [
        circuit
        for circuit in circuits
        if circuit.retry_at > now and _circuit_matches(endpoint, route, circuit)
    ]
    if not relevant:
        return None
    return min(
        relevant,
        key=lambda circuit: (
            -circuit.retry_at.timestamp(),
            _scope_priority(circuit.scope),
        ),
    )


def _circuit_matches(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    circuit: RuntimeCircuit,
) -> bool:
    if circuit.scope == "route":
        return circuit.scope_id == route.route_id
    if circuit.scope == "endpoint":
        return circuit.scope_id == endpoint.endpoint_id
    effective_bucket = endpoint.rate_limit_bucket or endpoint.endpoint_id
    return circuit.scope_id == effective_bucket


def _scope_priority(scope: str) -> int:
    if scope == "route":
        return 0
    if scope == "endpoint":
        return 1
    return 2
