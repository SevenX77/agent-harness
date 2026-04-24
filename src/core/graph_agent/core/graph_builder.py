"""GraphBuilder — compiles a phase list + collaborators into a LangGraph StateGraph.

Extracted from ``GraphAgentHarness._build_graph`` / ``_calc_recursion_limit``
(the last two graph-topology methods on the harness) as D-7.1 of the
harness split.

Compile-time collaborator — like ``RetryRouter``, the builder is
instantiated once at ``GraphAgentHarness.__init__`` time and reused for
every ``run()`` / ``resume()``. It deliberately does **not** accept a
``RunContext``: graph topology is a static function of ``phases`` plus
the (stateless) collaborator dependencies, and a ``RunContext`` does not
exist when the graph is being compiled. See the D-7.3 Gemini debate
recorded in context.md and the earlier ``RetryRouter`` docstring for the
full rationale — the "lifecycle mismatch" rule applies here too.

Per-phase execute node functions live on ``PhaseExecutor``; GraphBuilder
only wires them into the StateGraph. Subgraph nodes come from a
caller-supplied ``subgraph_node_factory`` so GraphBuilder stays
independent of the subgraph module (which itself still reads some legacy
state off the parent harness during Phase A — that will be cleaned up in
D-7.2 Phase B).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from .phase_executor import PhaseExecutor
from .retry_router import RetryRouter
from .state import WorkflowState
from .types import Phase


class GraphBuilder:
    """Build a compiled ``StateGraph`` for a fixed phase list."""

    def __init__(
        self,
        phases: list[Phase],
        *,
        phase_executor: PhaseExecutor,
        retry_router: RetryRouter,
        checkpointer: Any = None,
        subgraph_node_factory: Callable[[Phase], Callable[[WorkflowState], WorkflowState]],
    ) -> None:
        self._phases = phases
        self._phase_executor = phase_executor
        self._retry_router = retry_router
        self._checkpointer = checkpointer
        self._subgraph_node_factory = subgraph_node_factory

    def build(self) -> Any:
        """Build and compile the LangGraph StateGraph for the phase pipeline."""
        graph: StateGraph = StateGraph(WorkflowState)

        for phase in self._phases:
            execute_name = f"{phase.name}_execute"
            validate_name = f"{phase.name}_validate"

            if phase.subgraph is not None:
                graph.add_node(execute_name, self._subgraph_node_factory(phase))
                graph.add_node(validate_name, self._make_validation_node(phase))
                graph.add_edge(execute_name, validate_name)
                graph.add_conditional_edges(
                    validate_name,
                    self._retry_router.build_route_callback(phase),
                )
            elif phase.requires_llm:
                graph.add_node(execute_name, self._make_llm_node(phase))
                graph.add_node(validate_name, self._make_validation_node(phase))
                graph.add_edge(execute_name, validate_name)
                graph.add_conditional_edges(
                    validate_name,
                    self._retry_router.build_route_callback(phase),
                )
            else:
                graph.add_node(execute_name, self._make_code_only_node(phase))
                next_node = self._retry_router.next_phase_node(phase)
                if next_node == END:
                    graph.add_edge(execute_name, END)
                else:
                    graph.add_edge(execute_name, next_node)

        if self._phases:
            graph.set_entry_point(f"{self._phases[0].name}_execute")

        return graph.compile(checkpointer=self._checkpointer)

    def recursion_limit(self) -> int:
        """Compute the LangGraph recursion limit appropriate for this phase list.

        Accounts for cross-phase retries via ``retry_target``: a phase
        retrying to an earlier phase effectively doubles both phases'
        node visits, so each such link adds four units to the budget.
        """
        cross_phase_retries = sum(
            1 for p in self._phases if p.retry_target and p.retry_target != p.name
        )
        base = sum(p.max_retries for p in self._phases) * 2
        linear = len(self._phases) * 2
        return base + linear + cross_phase_retries * 4 + 10

    def _make_llm_node(self, phase: Phase) -> Callable[[WorkflowState], WorkflowState]:
        executor = self._phase_executor

        def execute(state: WorkflowState) -> WorkflowState:
            return executor.execute_llm_phase(phase, state)

        return execute

    def _make_validation_node(self, phase: Phase) -> Callable[[WorkflowState], WorkflowState]:
        executor = self._phase_executor

        def validate(state: WorkflowState) -> WorkflowState:
            return executor.execute_validation_phase(phase, state)

        return validate

    def _make_code_only_node(self, phase: Phase) -> Callable[[WorkflowState], WorkflowState]:
        executor = self._phase_executor

        def execute(state: WorkflowState) -> WorkflowState:
            return executor.execute_code_only_phase(phase, state)

        return execute
