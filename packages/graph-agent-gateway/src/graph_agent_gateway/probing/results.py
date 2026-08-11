"""What a probe reports back.

Evidence about one endpoint or one route at one moment: what was asked, what
came back, how long it took. Writing any of it into the registry is the host's
decision, not the probe's.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from graph_agent_gateway.registry import ProviderKind, ProviderProbeBackend

from .judge import ProviderProbeStatus


class EndpointProbeResult(BaseModel):
    """Connectivity result for one provider endpoint."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    provider_kind: ProviderKind
    backend: ProviderProbeBackend
    base_url: str
    status: ProviderProbeStatus
    latency_ms: int | None = None
    model_ids: tuple[str, ...] = ()
    model_capabilities: dict[str, dict[str, Any]] = Field(default_factory=dict)
    message: str | None = None
    error_code: str | None = None

    @property
    def model_seen(self) -> str | None:
        return self.model_ids[0] if self.model_ids else None


class RouteProbeResult(BaseModel):
    """Generation probe result for one provider route."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    route_id: str
    provider_kind: ProviderKind
    backend: ProviderProbeBackend
    base_url: str
    model_id: str
    status: ProviderProbeStatus
    latency_ms: int | None = None
    message: str | None = None
