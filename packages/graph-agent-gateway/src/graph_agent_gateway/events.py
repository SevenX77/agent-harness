"""Gateway-owned event DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMFallbackEvent:
    """Structured fallback event emitted by Gateway runtime."""

    phase_name: str
    from_provider: str
    to_provider: str
    reason: str
    code: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    event_type: str = field(default="llm_fallback", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", dict(self.context))

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        del mode
        return {
            "event_type": self.event_type,
            "phase_name": self.phase_name,
            "from_provider": self.from_provider,
            "to_provider": self.to_provider,
            "reason": self.reason,
            "code": self.code,
            "context": dict(self.context),
        }
