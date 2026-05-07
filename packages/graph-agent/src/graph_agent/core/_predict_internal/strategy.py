"""Predict mock strategy skeletons."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from graph_agent.core._predict_internal.models import GoldenCase


class BaseMockStrategy(ABC):
    """Minimal Predict strategy contract for phase-name based lookup."""

    @abstractmethod
    def has_phase(self, phase_name: str) -> bool:
        """Return whether this strategy has data or behavior for ``phase_name``."""


MockLLMParam = TypeAdapter(None | dict[str, Any] | Path | list[GoldenCase])


__all__ = ["BaseMockStrategy", "MockLLMParam"]
