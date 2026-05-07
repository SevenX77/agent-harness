"""Predict mock strategy skeletons."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseMockStrategy(ABC):
    """Minimal Predict strategy contract for phase-name based lookup."""

    @abstractmethod
    def has_phase(self, phase_name: str) -> bool:
        """Return whether this strategy has data or behavior for ``phase_name``."""


__all__ = ["BaseMockStrategy"]
