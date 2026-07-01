"""Shared provider-probe result types + errors for the llm router.

Studio used to own a parallel HTTP probe implementation here, but provider
probing now lives in the gateway
(``graph_agent_gateway.registry.provider_probe``). That parallel implementation
was removed; what remains are the small result/error types the llm router and
its tests still import. These are slated to disappear entirely once the legacy
``_ping_provider`` test seam in the llm router is retired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

CopilotProvider: TypeAlias = Literal["ark", "claude", "deepseek", "gemini", "openai"]


@dataclass(frozen=True)
class PingResult:
    latency_ms: int
    model_ids: tuple[str, ...] = ()
    model_capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def model_seen(self) -> str | None:
        return self.model_ids[0] if self.model_ids else None


@dataclass(frozen=True)
class ModelProbeResult:
    model_id: str
    status: Literal[
        "ok",
        "invalid_model",
        "invalid_key",
        "rate_limited",
        "quota_exceeded",
        "network_error",
        "timeout",
        "error",
    ]
    latency_ms: int | None = None
    message: str | None = None


class _ProviderTestError(Exception):
    """Base class for provider Test errors carrying a vendor-specific code."""

    def __init__(self, message: str = "", *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code or ""


class _Unauthorized(_ProviderTestError):
    pass


class _RateLimited(_ProviderTestError):
    pass


class _QuotaExceeded(_ProviderTestError):
    pass


class _NetworkError(_ProviderTestError):
    pass


__all__ = [
    "CopilotProvider",
    "ModelProbeResult",
    "PingResult",
    "_NetworkError",
    "_QuotaExceeded",
    "_RateLimited",
    "_Unauthorized",
]
