"""GraphBuilder — compiles a phase list + collaborators into a LangGraph StateGraph.

Extracted from ``GraphAgentHarness._build_graph`` / ``_calc_recursion_limit``
as D-7.1 of the harness split.

Compile-time collaborator — like ``RetryRouter``, the builder is
instantiated once at ``GraphAgentHarness.__init__`` time and reused for
every ``run()`` / ``resume()``. It deliberately does **not** accept a
``RunContext`` **or** a ``PhaseExecutor``: graph topology is a static
function of ``phases``, and the per-run ``PhaseExecutor`` is passed
through at invoke time via LangGraph's ``RunnableConfig["configurable"]``
and extracted inside each node closure. This per-invocation threading
(Gemini's Option D on 2026-04-24) is what closes the concurrent-
``child.run()`` race: no mutable per-run state lives on the harness
instance or inside GraphBuilder.

Per-phase execute bodies live on ``PhaseExecutor``; GraphBuilder only
wires them into the StateGraph. The 1.x subgraph / parallel-delegate
node factories were removed in MVP-0 B1 (2026-04-28) along with the
DelegatePhase / ParallelDelegatePhase modes; V2 cross-skill composition
will route through the same StateGraph using LangGraph Send API.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.retry_router import RetryRouter
from graph_agent.core.state import WorkflowState
from graph_agent.core.types import Phase


def _executor_from_config(config: RunnableConfig) -> PhaseExecutor:
    """Extract the per-run ``PhaseExecutor`` injected into LangGraph config.

    Raises ``RuntimeError`` with a specific message when the config is
    missing the executor — this is always a programming error (harness
    built the config wrong), never a runtime configuration issue.
    """
    configurable = (config or {}).get("configurable") or {}
    executor = configurable.get("_phase_executor")
    if executor is None:
        raise RuntimeError(
            "graph node invoked without _phase_executor in config['configurable']. "
            "GraphAgentHarness.run/resume must inject PhaseExecutor before .invoke()."
        )
    return cast(PhaseExecutor, executor)


class GraphBuilder:
    """Build a compiled ``StateGraph`` for a fixed phase list."""

    def __init__(
        self,
        phases: list[Phase],
        *,
        retry_router: RetryRouter,
        checkpointer: Any = None,
    ) -> None:
        self._phases = phases
        self._retry_router = retry_router
        self._checkpointer = checkpointer

    def build(self) -> Any:
        """Build and compile the LangGraph StateGraph for the phase pipeline."""
        graph: StateGraph[WorkflowState, Any, WorkflowState, WorkflowState] = StateGraph(
            WorkflowState
        )

        for phase in self._phases:
            execute_name = f"{phase.name}_execute"
            validate_name = f"{phase.name}_validate"

            if phase.requires_llm:
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

    def _make_llm_node(self, phase: Phase) -> Callable[..., WorkflowState]:
        def execute(state: WorkflowState, config: RunnableConfig) -> WorkflowState:
            return _executor_from_config(config).execute_llm_phase(phase, state)

        return execute

    def _make_validation_node(self, phase: Phase) -> Callable[..., WorkflowState]:
        def validate(state: WorkflowState, config: RunnableConfig) -> WorkflowState:
            return _executor_from_config(config).execute_validation_phase(phase, state)

        return validate

    def _make_code_only_node(self, phase: Phase) -> Callable[..., WorkflowState]:
        def execute(state: WorkflowState, config: RunnableConfig) -> WorkflowState:
            return _executor_from_config(config).execute_code_only_phase(phase, state)

        return execute
