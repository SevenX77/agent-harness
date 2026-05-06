"""RetryRouter — LangGraph conditional-edge routing for a phase pipeline.

Extracted from ``GraphAgentHarness._should_retry`` and ``_get_next_phase_node``
(harness.py L1565-L1585 before the extract) as D-7.3 of the harness-split.

Compile-time collaborator: the router is built once at
``GraphAgentHarness.__init__`` time and reused for every ``run()``/``resume()``.
It deliberately does **not** accept a ``RunContext`` — routing topology is
fully determined by the static phase list, and a ``RunContext`` does not
exist yet when the LangGraph ``StateGraph`` is being compiled. See
``.kiro/specs/harness-split/context.md`` §五 intro for the reasoning that
overrode the "RunContext for all four collaborators" suggestion.
"""

from __future__ import annotations

from collections.abc import Callable

from langgraph.graph import END

from graph_agent.core.state import WorkflowState
from graph_agent.core.types import Phase


class RetryRouter:
    """Emit LangGraph-compatible routing callbacks for a fixed phase list."""

    def __init__(self, phases: list[Phase]) -> None:
        self._phases = phases

    def build_route_callback(self, phase: Phase) -> Callable[[WorkflowState], str]:
        """Return the conditional-edge callback LangGraph invokes after ``phase``'s validate node.

        The returned closure reads ``state["flow"]`` at graph-invoke time
        and resolves to either ``"{retry_target}_execute"`` (retry branch)
        or the next phase's execute-node name / ``END``.
        """
        next_node = self.next_phase_node(phase)

        def route(state: WorkflowState) -> str:
            if state["flow"].retry_feedback:
                target = phase.retry_target or phase.name
                return f"{target}_execute"
            return next_node

        return route

    def next_phase_node(self, phase: Phase) -> str:
        """Return the execute-node name of the phase after ``phase``, or ``END``."""
        idx = next(
            (i for i, p in enumerate(self._phases) if p.name == phase.name),
            -1,
        )
        if idx < 0 or idx >= len(self._phases) - 1:
            return END
        return f"{self._phases[idx + 1].name}_execute"
