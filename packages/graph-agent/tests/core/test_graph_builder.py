"""Tests for GraphBuilder (D-7.1 + D-7.2 Phase B)."""

from __future__ import annotations

from collections.abc import Callable

from graph_agent.core.graph_builder import GraphBuilder
from graph_agent.core.retry_router import RetryRouter
from graph_agent.core.state import WorkflowState
from graph_agent.core.types import Phase
from langchain_core.runnables import RunnableConfig


def _noop_node(phase: Phase) -> Callable[..., WorkflowState]:
    def _inner(state: WorkflowState, config: RunnableConfig) -> WorkflowState:
        return state

    return _inner


def _make_builder(phases: list[Phase]) -> GraphBuilder:
    return GraphBuilder(
        phases,
        retry_router=RetryRouter(phases),
        checkpointer=None,
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


class TestExecutorFromConfig:
    """The `_executor_from_config` helper is the load-bearing link in Phase B:
    every LangGraph node extracts the per-run PhaseExecutor from
    ``config["configurable"]["_phase_executor"]``. If it silently returns
    the wrong thing (or None), the whole graph silently breaks at runtime.
    These tests pin the contract end-to-end — missing config, empty config,
    nested configurable, and happy path."""

    def _make_llm_node_with_executor_assert(
        self, phase: Phase, marker: list[str]
    ) -> Callable[..., WorkflowState]:
        """Reach into GraphBuilder's private _make_llm_node to run the real
        unwrap path. We verify the call reaches the executor passed via
        config (not any ambient instance state)."""
        from graph_agent.core.phase_executor import PhaseExecutor

        class _SpyExecutor(PhaseExecutor):
            def execute_llm_phase(self, p: Phase, state: WorkflowState) -> WorkflowState:
                marker.append(p.name)
                return state

        builder = _make_builder([phase])
        node = builder._make_llm_node(phase)  # type: ignore[attr-defined]
        return node

    def test_missing_config_raises_runtime_error(self):
        import pytest
        from graph_agent.core.graph_builder import _executor_from_config

        with pytest.raises(RuntimeError, match="_phase_executor"):
            _executor_from_config(None)  # type: ignore[arg-type]

    def test_config_without_configurable_key_raises(self):
        import pytest
        from graph_agent.core.graph_builder import _executor_from_config

        with pytest.raises(RuntimeError, match="_phase_executor"):
            _executor_from_config({})

    def test_configurable_missing_phase_executor_raises(self):
        import pytest
        from graph_agent.core.graph_builder import _executor_from_config

        with pytest.raises(RuntimeError, match="_phase_executor"):
            _executor_from_config({"configurable": {"thread_id": "x"}})

    def test_happy_path_returns_the_injected_executor(self):
        from graph_agent.core.graph_builder import _executor_from_config
        from graph_agent.core.phase_executor import PhaseExecutor

        sentinel = PhaseExecutor([])
        got = _executor_from_config({"configurable": {"_phase_executor": sentinel}})
        assert got is sentinel, "unwrap must return the exact object injected, not a copy or None"

    def test_llm_node_dispatches_to_injected_executor(self):
        """End-to-end through `_make_llm_node`: the closure must call the
        executor present in config at invoke time (no ambient lookup)."""
        from graph_agent.core.phase_executor import PhaseExecutor

        recorded: list[str] = []

        class _SpyExecutor(PhaseExecutor):
            def execute_llm_phase(self, p: Phase, state: WorkflowState) -> WorkflowState:
                recorded.append(p.name)
                return state

        phase = Phase(name="alpha")
        builder = _make_builder([phase])
        node = builder._make_llm_node(phase)  # type: ignore[attr-defined]
        state: WorkflowState = {
            "context": {},
            "messages": [],
            "current_phase": "",
            "retry_counts": {},
            "metrics": {},
        }
        spy = _SpyExecutor([])

        node(state, {"configurable": {"_phase_executor": spy}})  # type: ignore[arg-type]
        assert recorded == ["alpha"]

    def test_code_only_node_dispatches_to_injected_executor(self):
        from graph_agent.core.phase_executor import PhaseExecutor

        recorded: list[str] = []

        class _SpyExecutor(PhaseExecutor):
            def execute_code_only_phase(self, p: Phase, state: WorkflowState) -> WorkflowState:
                recorded.append(p.name)
                return state

        phase = Phase(name="beta", requires_llm=False)
        builder = _make_builder([phase])
        node = builder._make_code_only_node(phase)  # type: ignore[attr-defined]
        state: WorkflowState = {
            "context": {},
            "messages": [],
            "current_phase": "",
            "retry_counts": {},
            "metrics": {},
        }
        spy = _SpyExecutor([])

        node(state, {"configurable": {"_phase_executor": spy}})  # type: ignore[arg-type]
        assert recorded == ["beta"]


class TestConstructor:
    """Compile-time collaborator: no RunContext, no PhaseExecutor at __init__."""

    def test_no_run_context_and_no_phase_executor_params(self):
        """Regression guard: GraphBuilder.__init__ takes neither a
        RunContext nor a PhaseExecutor.

        RunContext is per-run (lifecycle mismatch with compile-time
        construction — the RetryRouter rule from the D-7.3 Gemini debate).
        PhaseExecutor is also per-run, threaded through each invocation
        via LangGraph's ``RunnableConfig["configurable"]["_phase_executor"]``
        (D-7.2 Phase B, Gemini's Option D on 2026-04-24). GraphBuilder
        only needs the static topology dependencies.
        """
        phases = [Phase(name="only", requires_llm=False)]

        GraphBuilder(
            phases,
            retry_router=RetryRouter(phases),
            checkpointer=None,
        )
