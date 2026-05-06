"""PhaseNode factory — instantiates the right subclass for a given phase.

PHASE3_DESIGN.md §2.2 / §2.3: the legacy ``GraphBuilder`` closure
captured ``executor.execute_*`` methods directly; after M6 it
delegates to a polymorphic :class:`PhaseNode` instance built here.

The factory keeps the existing dispatch invariants visible:

* ``phase.requires_llm == True`` → :class:`LLMPhaseNode`.
* ``phase.requires_llm == False`` → :class:`CodePhaseNode`.
* The validation graph node always uses :class:`ValidationPhaseNode`,
  so it gets a dedicated builder rather than threading a "kind" arg
  through the execute-side dispatcher.
"""

from __future__ import annotations

from graph_agent.core.run_context import RunContext
from graph_agent.core.types import Phase
from graph_agent.core.phase_nodes.base import DependencyContainer, HeartbeatProtocol, PhaseNode
from graph_agent.core.phase_nodes.code_phase_node import CodePhaseNode
from graph_agent.core.phase_nodes.llm_phase_node import LLMPhaseNode
from graph_agent.core.phase_nodes.validation_phase_node import ValidationPhaseNode


def build_llm_phase_node(
    phase: Phase,
    dependencies: DependencyContainer,
    *,
    run_context: RunContext | None = None,
    heartbeat: HeartbeatProtocol | None = None,
) -> PhaseNode:
    """Pick between LLMPhaseNode and CodePhaseNode based on ``phase.requires_llm``.

    The legacy ``execute_llm_phase`` entry point routed every
    ``requires_llm=True`` phase straight to the LLM agent loop and
    every ``requires_llm=False`` phase to the synchronous code-only
    runner; this factory preserves that invariant.
    """
    if phase.requires_llm:
        return LLMPhaseNode(dependencies, run_context=run_context, heartbeat=heartbeat)
    return CodePhaseNode(dependencies, run_context=run_context, heartbeat=heartbeat)


def build_code_phase_node(
    phase: Phase,
    dependencies: DependencyContainer,
    *,
    run_context: RunContext | None = None,
    heartbeat: HeartbeatProtocol | None = None,
) -> CodePhaseNode:
    """Always return a :class:`CodePhaseNode` for ``mode: logic`` phases.

    Kept as a separate entry point so callers that already know they
    have a code-only phase don't have to assert on the discriminator.
    """
    del phase  # accepted for API symmetry with the LLM factory
    return CodePhaseNode(dependencies, run_context=run_context, heartbeat=heartbeat)


def build_validation_phase_node(
    phase: Phase,
    dependencies: DependencyContainer,
    *,
    run_context: RunContext | None = None,
    heartbeat: HeartbeatProtocol | None = None,
) -> ValidationPhaseNode:
    """Always return a :class:`ValidationPhaseNode` for the validation graph node."""
    del phase  # accepted for API symmetry with the execute-side factories
    return ValidationPhaseNode(dependencies, run_context=run_context, heartbeat=heartbeat)


__all__ = [
    "build_code_phase_node",
    "build_llm_phase_node",
    "build_validation_phase_node",
]
