"""``ModelProbeResult`` — the result of probing whether one provider model can generate.

Studio's own provider-probe implementation used to live in this module (formerly
named ``copilot_test``); provider probing has since moved to the gateway
(``graph_agent_gateway.probing``). This model-centric result type
is all that remains: the llm router's official-call-method probe
(``_gateway_probe_official_call_method``) adapts the gateway's ``RouteProbeResult``
back into this shape for its callers.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.adapters.gateway import ProviderProbeStatus


@dataclass(frozen=True)
class ModelProbeResult:
    model_id: str
    # The vocabulary belongs to whoever reads provider answers, and that is the
    # gateway's judge. Re-listing the members here made adding one a three-file
    # edit that only tests kept honest.
    status: ProviderProbeStatus
    latency_ms: int | None = None
    message: str | None = None


__all__ = ["ModelProbeResult"]
