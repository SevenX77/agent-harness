"""How hard to think, said once in the caller's words.

Every provider spells this differently — a budget in tokens, a word like
``high``, a switch, a nested object — so the ask is parsed once here and each
dialect translates it. Reading the raw settings mapping inside a request
builder is what let the same field mean two things on two wires.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Reasoning:
    """What the caller asked about thinking.

    ``enabled`` is three-valued on purpose: some wires distinguish "the caller
    said nothing" (send no thinking field at all) from "the caller said off"
    (send an explicit off switch), and collapsing those two turns silence into
    a decision.
    """

    enabled: bool | None = None
    effort: str | None = None
    budget_tokens: int | None = None
    requested_type: str | None = None

    @classmethod
    def from_runtime_settings(cls, settings: Mapping[str, Any] | None) -> Reasoning:
        raw = settings.get("reasoning") if settings else None
        reasoning: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
        effort = reasoning.get("effort")
        budget = reasoning.get("budget_tokens")
        requested_type = reasoning.get("type")
        return cls(
            enabled=(reasoning.get("enabled") is True) if "enabled" in reasoning else None,
            effort=effort if isinstance(effort, str) and effort else None,
            budget_tokens=(
                int(budget) if isinstance(budget, int | float) and budget > 0 else None
            ),
            requested_type=requested_type if isinstance(requested_type, str) else None,
        )

    @property
    def wanted(self) -> bool:
        """True when the caller turned thinking on, as opposed to off or unsaid."""

        return self.enabled is True
