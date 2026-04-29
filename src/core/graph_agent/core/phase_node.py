"""PhaseNode — minimal executable node wrapper for the MVP-3 loader pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .harness import Phase
from .schema_engine import SchemaObject
from .state import WorkflowState


@dataclass(frozen=True)
class PhaseNode:
    """Compiled graph node facade emitted by the loader Phase 3 pipeline."""

    name: str
    execute_fn: Callable[[WorkflowState], WorkflowState]
    metadata: dict[str, Any] | None = None
    phase: Phase | None = None
    business_data_cls: type[Any] | None = None
    initial_state_factory: Callable[[dict[str, Any] | None], WorkflowState] | None = None
    compiled_schema: SchemaObject | None = None
    output_schema_cls: type[Any] | None = None
    validator: Callable[..., tuple[bool, list[str]]] | None = None

    def execute(self, state: WorkflowState) -> WorkflowState:
        """Execute this phase node against a WorkflowState."""

        return self.execute_fn(state)


__all__ = ["PhaseNode"]
