"""PhaseExecutor — executes a single phase once (LLM / code-only / validation / subgraph).

Extracted progressively from ``GraphAgentHarness._build_*_node`` factories
as D-7.2 of the harness-split. Migration order per context.md §6.1 step 4:

  * step 4.1 (this commit): ``execute_code_only_phase`` — smallest, no
    heartbeat / run_context dependency.
  * step 4.2: ``execute_validation_phase``.
  * step 4.3: ``execute_llm_phase`` — the 450-line DeerFlow agent loop.
  * step 4.4 (Phase B): switch from "bound to ``harness.callbacks`` at
    init" to "per-run PhaseExecutor passed via LangGraph ``RunnableConfig``",
    at which point ``_active_heartbeat`` / ``_active_run_context`` move
    from the harness instance onto the executor (eliminating the
    concurrent-``child.run()`` race noted in subgraph.py's FIXME).

Until step 4.4, PhaseExecutor holds only a reference to
``harness.callbacks`` (the same list that the pre-refactor closures read).
This keeps each sub-commit behaviour-preserving; the concurrency fix is
intentionally deferred to a single clearly-scoped commit.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..callbacks.base import Callback
from .state import WorkflowState
from .types import Phase

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PhaseExecutor:
    """Execute a single phase invocation; retry / routing is the graph's job."""

    def __init__(self, callbacks: list[Callback]) -> None:
        self._callbacks = callbacks

    def execute_code_only_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run a code-only phase (``requires_llm=False``).

        Tools are invoked sequentially as plain callables receiving the
        phase's mutable context dict. A tool that returns a string sets
        ``context["_last_output"]`` (the last wins, matching pre-refactor
        semantics). ``_retry_feedback`` is popped after tools run so the
        feedback is visible to tools but does not leak to the next phase.
        """
        from .harness import _clone_state  # lazy: avoid import cycle at module load

        next_state = _clone_state(state)
        for cb in self._callbacks:
            cb.on_phase_start(phase.name, dict(next_state["context"]))

        if phase.tools:
            logger.info(
                "[CodeOnly] Executing %d tool(s) for phase=%s",
                len(phase.tools),
                phase.name,
            )
            for fn in phase.tools:
                result = fn(next_state["context"])
                if isinstance(result, str):
                    next_state["context"]["_last_output"] = result

        next_state["context"].pop("_retry_feedback", None)
        next_state["current_phase"] = phase.name

        for cb in self._callbacks:
            cb.on_phase_end(
                phase.name,
                dict(next_state["context"]),
                dict(next_state["metrics"]),
            )
        return next_state

    def execute_llm_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run an LLM-driven phase (DeerFlow create_agent + nudge-loop)."""
        raise NotImplementedError("D-7.2 step 4.3: migrate LLM execution body from _build_phase_node")

    def execute_validation_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run the phase's validator and emit retry / pass state updates."""
        raise NotImplementedError("D-7.2 step 4.2: migrate from _build_validation_node")

    def execute_subgraph_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Invoke a child harness for a subgraph phase."""
        raise NotImplementedError("D-7.2: migrate from _build_subgraph_node body")
