"""RetryRouter — decides retry / next-phase / end after a phase executes.

Skeleton for D-step-1 (refactor/harness-split). Implementation is migrated
from ``GraphAgentHarness._should_retry`` and ``_get_next_phase_node`` in
``harness.py`` during D-7.3.
"""

from __future__ import annotations

from typing import Literal

from .run_context import RunContext
from .state import WorkflowState
from .types import Phase


class RetryRouter:
    """Route a phase's post-execution state to retry / next / end.

    All routing reads come from the caller-supplied ``phases`` list and the
    immutable ``RunContext``; the router never mutates state.
    """

    def __init__(self, phases: list[Phase], run_context: RunContext) -> None:
        self._phases = phases
        self._run_context = run_context

    def route(self, phase: Phase, state: WorkflowState) -> Literal["retry", "next", "end"]:
        """Return the next control-flow edge for LangGraph after ``phase`` ran."""
        raise NotImplementedError("D-7.3: migrate from GraphAgentHarness._should_retry")

    def next_phase_name(self, phase: Phase) -> str:
        """Return the node-name of the phase that follows ``phase`` in the pipeline."""
        raise NotImplementedError("D-7.3: migrate from GraphAgentHarness._get_next_phase_node")
