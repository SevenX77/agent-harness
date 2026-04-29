"""PhaseNode — minimal executable node wrapper for the MVP-3 loader pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .state import WorkflowState


@dataclass(frozen=True)
class PhaseNode:
    """Compiled graph node facade consumed by future build_graph_nodes."""

    name: str
    execute_fn: Callable[[WorkflowState], WorkflowState]
    metadata: dict[str, Any] | None = None

    def execute(self, state: WorkflowState) -> WorkflowState:
        """Execute this phase node against a WorkflowState."""

        return self.execute_fn(state)


__all__ = ["PhaseNode"]
