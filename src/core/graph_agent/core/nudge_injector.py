"""NudgeInjector — per-phase cognitive-nudge state machine.

Skeleton for D-step-1 (refactor/harness-split). Implementation is migrated
from the counter + helper logic buried inside
``GraphAgentHarness._build_phase_node`` (roughly L1171-1259) during D-7.4.

Owns the per-phase counters (``planning_nudge_count``,
``selfcheck_nudge_count``, ``standard_nudge_count``, ``total_nudge_count``)
and decides when to inject which nudge. Nudge text constants still come from
``..cognitive.finish`` (not duplicated here).
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from .run_context import RunContext
from .state import WorkflowState
from .types import Phase


class NudgeInjector:
    """Stateful counter + policy for cognitive nudges within one phase run."""

    def __init__(self, phase: Phase, run_context: RunContext) -> None:
        self._phase = phase
        self._run_context = run_context

    def maybe_inject_before_invoke(self, state: WorkflowState) -> list[HumanMessage]:
        """Return messages to prepend to ``state['messages']`` for this turn.

        Empty list means no nudge this turn.
        """
        raise NotImplementedError("D-7.4: migrate planning/selfcheck nudge inject from _build_phase_node")

    def on_llm_response(self, response: AIMessage) -> None:
        """Update internal counters based on what the LLM just produced."""
        raise NotImplementedError("D-7.4: migrate counter-update logic from _build_phase_node while-loop")

    def should_exit(self) -> bool:
        """True when ``total_nudge_count`` has reached the exit cap for this phase."""
        raise NotImplementedError("D-7.4: migrate total-cap check from _build_phase_node")
