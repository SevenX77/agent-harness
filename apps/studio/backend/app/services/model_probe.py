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
from typing import Literal


@dataclass(frozen=True)
class ModelProbeResult:
    model_id: str
    status: Literal[
        "ok",
        "invalid_model",
        "invalid_key",
        "protocol_unsupported",
        "rate_limited",
        "quota_exceeded",
        "network_error",
        "timeout",
        "error",
    ]
    latency_ms: int | None = None
    message: str | None = None


__all__ = ["ModelProbeResult"]
