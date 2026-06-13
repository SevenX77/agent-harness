"""Project stored LLM facts and runtime health into Studio UI states."""

from __future__ import annotations

from datetime import datetime

from app.core.adapters.gateway import GatewayAdapter, ProviderModelStateProjection
from app.models.llm_config import ProviderEndpoint, ProviderRoute
from app.services.llm_health_store import RuntimeCircuit


def project_provider_model_state(
    *,
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    circuits: list[RuntimeCircuit],
    now: datetime | None = None,
) -> ProviderModelStateProjection:
    adapter = GatewayAdapter(transport="in_process")
    return adapter.project_route_state(
        {
            "endpoint": endpoint,
            "route": route,
            "circuits": circuits,
            "now": now,
        }
    )
