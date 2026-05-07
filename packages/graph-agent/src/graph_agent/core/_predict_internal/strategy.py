"""Predict mock strategy skeletons."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter

from graph_agent.core._predict_internal.models import GoldenCase

MockedSource = Literal["golden_case", "copilot", "heuristic_stub", "manual"]


class BaseMockStrategy(ABC):
    """Minimal Predict strategy contract for phase-name based lookup."""

    @abstractmethod
    def has_phase(self, phase_name: str) -> bool:
        """Return whether this strategy has data or behavior for ``phase_name``."""

    def has_golden_case(self, phase_name: str) -> bool:
        """Return whether P0 golden output is available for ``phase_name``."""
        return False

    def get_golden_output(self, phase_name: str) -> dict[str, Any]:
        """Return P0 golden output for ``phase_name``."""
        raise KeyError(phase_name)

    def has_manual_override(self, phase_name: str) -> bool:
        """Return whether P1 manual/Copilot output is available for ``phase_name``."""
        return False

    def get_manual_override(self, phase_name: str) -> dict[str, Any]:
        """Return P1 manual/Copilot override for ``phase_name``."""
        raise KeyError(phase_name)

    def get_manual_source(self, phase_name: str) -> MockedSource:
        """Return the P1 source label for ``phase_name``."""
        return "manual"

    def get_phase_schema(self, phase_name: str) -> dict[str, Any] | None:
        """Return the io.outputs schema used for P2 heuristic stubs."""
        return None


MockLLMParam = TypeAdapter(None | dict[str, Any] | Path | list[GoldenCase])


__all__ = ["BaseMockStrategy", "MockLLMParam", "MockedSource"]
