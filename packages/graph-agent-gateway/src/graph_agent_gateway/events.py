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

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", dict(self.context))
