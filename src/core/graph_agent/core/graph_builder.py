"""GraphBuilder — compiles a phase list + RunContext into a LangGraph StateGraph.

Skeleton for D-step-1 (refactor/harness-split). Implementation is migrated
from ``GraphAgentHarness._build_graph`` / ``_build_subgraph_node`` /
``_calc_recursion_limit`` during D-7.1.

The per-node execution callbacks that GraphBuilder wires into the StateGraph
are owned by ``PhaseExecutor``; GraphBuilder only handles topology + routing
edges + recursion-limit math.

Per context.md §11-1 (Gemini's note): heartbeat-pulser start/stop stays in
``GraphAgentHarness.run()`` try/finally — GraphBuilder does NOT start heartbeats.
"""

from __future__ import annotations

from langgraph.graph import StateGraph

from .phase_executor import PhaseExecutor
from .retry_router import RetryRouter
from .run_context import RunContext
from .types import Phase


class GraphBuilder:
    """Produce a compiled ``StateGraph`` for a fixed phase list."""

    def __init__(
        self,
        phases: list[Phase],
        run_context: RunContext,
        *,
        phase_executor: PhaseExecutor,
        retry_router: RetryRouter,
    ) -> None:
        self._phases = phases
        self._run_context = run_context
        self._phase_executor = phase_executor
        self._retry_router = retry_router

    def build(self) -> StateGraph:
        """Build and return an *uncompiled* StateGraph (caller compiles with checkpointer)."""
        raise NotImplementedError("D-7.1: migrate from GraphAgentHarness._build_graph")

    def recursion_limit(self) -> int:
        """Compute the LangGraph recursion limit appropriate for this phase list."""
        raise NotImplementedError("D-7.1: migrate from GraphAgentHarness._calc_recursion_limit")
