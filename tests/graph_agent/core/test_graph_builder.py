"""Tests for GraphBuilder (D-7.1)."""

from __future__ import annotations

from typing import Any, Callable

from graph_agent.core.graph_builder import GraphBuilder
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.retry_router import RetryRouter
from graph_agent.core.state import WorkflowState
from graph_agent.core.types import Phase


def _noop_node(phase: Phase) -> Callable[[WorkflowState], WorkflowState]:
    def _inner(state: WorkflowState) -> WorkflowState:
        return state
    return _inner


def _make_builder(
    phases: list[Phase],
    *,
    subgraph_factory: Callable[[Phase], Callable[[WorkflowState], WorkflowState]] | None = None,
) -> GraphBuilder:
    return GraphBuilder(
        phases,
        phase_executor=PhaseExecutor([]),
        retry_router=RetryRouter(phases),
        checkpointer=None,
        subgraph_node_factory=subgraph_factory or _noop_node,
    )


class TestRecursionLimit:
    """`recursion_limit` derives from phase counts + retries + cross-phase links."""

    def test_single_phase_defaults(self):
        # default max_retries=3, no cross-phase retry
        phases = [Phase(name="only")]
        builder = _make_builder(phases)

        # base = 3 * 2 = 6, linear = 1 * 2 = 2, cross = 0 * 4 = 0, fixed = 10
        assert builder.recursion_limit() == 6 + 2 + 0 + 10

    def test_multi_phase_no_cross_retry(self):
        phases = [
            Phase(name="a", max_retries=2),
            Phase(name="b", max_retries=4),
        ]
        builder = _make_builder(phases)

        # base = (2+4)*2 = 12, linear = 2*2 = 4, cross = 0, fixed = 10
        assert builder.recursion_limit() == 12 + 4 + 0 + 10

    def test_cross_phase_retry_adds_four_each(self):
        phases = [
            Phase(name="a", max_retries=2),
            Phase(name="b", max_retries=3, retry_target="a"),
        ]
        builder = _make_builder(phases)

        # base = (2+3)*2 = 10, linear = 4, cross = 1 (only b retries cross), cross*4 = 4, fixed = 10
        assert builder.recursion_limit() == 10 + 4 + 4 + 10

    def test_retry_target_equal_to_self_not_counted_as_cross(self):
        phases = [Phase(name="a", max_retries=2, retry_target="a")]
        builder = _make_builder(phases)

        assert builder.recursion_limit() == (2 * 2) + (1 * 2) + 0 + 10


class TestBuild:
    """Smoke tests: build() produces a working compiled graph for various phase types."""

    def test_build_single_code_only_phase(self):
        # code_only (requires_llm=False) + no validator → linear path to END.
        phases = [Phase(name="only", requires_llm=False)]
        builder = _make_builder(phases)

        graph = builder.build()
        # The compiled graph exposes its topology via .get_graph().
        nodes = graph.get_graph().nodes
        assert "only_execute" in nodes

    def test_build_llm_phase_adds_execute_and_validate_nodes(self):
        phases = [Phase(name="analyse")]  # requires_llm=True by default
        builder = _make_builder(phases)

        graph = builder.build()
        nodes = graph.get_graph().nodes
        assert "analyse_execute" in nodes
        assert "analyse_validate" in nodes

    def test_build_multi_phase_mixed_types(self):
        phases = [
            Phase(name="prep", requires_llm=False),
            Phase(name="analyse"),  # LLM
        ]
        builder = _make_builder(phases)

        graph = builder.build()
        nodes = graph.get_graph().nodes
        assert {"prep_execute", "analyse_execute", "analyse_validate"}.issubset(nodes)

    def test_build_with_subgraph_phase_uses_subgraph_factory(self):
        """Phases with `subgraph` go through the supplied factory, not PhaseExecutor."""
        factory_calls: list[Phase] = []

        def factory(phase: Phase) -> Callable[[WorkflowState], WorkflowState]:
            factory_calls.append(phase)
            return _noop_node(phase)

        # Use a sentinel (truthy) for subgraph field — the factory is what matters.
        phases = [Phase(name="sub", subgraph=object())]  # type: ignore[arg-type]
        builder = _make_builder(phases, subgraph_factory=factory)

        builder.build()
        # The subgraph factory was consulted for the one subgraph phase.
        assert [p.name for p in factory_calls] == ["sub"]


class TestConstructor:
    """No RunContext dependency — GraphBuilder is a compile-time collaborator."""

    def test_no_run_context_param_accepted(self):
        """Regression guard: GraphBuilder.__init__ deliberately rejects RunContext.

        Compile-time collaborators must not require a per-run object that
        does not yet exist when `_build_graph` runs (the RetryRouter rule
        from the D-7.3 Gemini debate applies here too).
        """
        phases = [Phase(name="only", requires_llm=False)]

        # No TypeError = signature does not require RunContext.
        GraphBuilder(
            phases,
            phase_executor=PhaseExecutor([]),
            retry_router=RetryRouter(phases),
            checkpointer=None,
            subgraph_node_factory=_noop_node,
        )
