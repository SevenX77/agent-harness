"""Tests for RetryRouter (D-7.3).

Captures the exact routing behaviour previously implemented by
``GraphAgentHarness._should_retry`` / ``_get_next_phase_node`` so the
extraction into a stand-alone collaborator is behaviour-preserving.
"""

from __future__ import annotations

from graph_agent.core.retry_router import RetryRouter
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.core.types import Phase
from langgraph.graph import END


def _make_phase(name: str, *, retry_target: str | None = None) -> Phase:
    return Phase(name=name, retry_target=retry_target)


def _make_state(*, retry_feedback: list[str] | None = None) -> WorkflowState:
    return WorkflowState(
        data=BusinessData(),
        flow=FrameworkState(retry_feedback=retry_feedback),
        messages=[],
    )


class TestNextPhaseNode:
    """`next_phase_node` returns the downstream execute-node name or END."""

    def test_middle_phase_returns_next_execute_name(self):
        phases = [_make_phase("alpha"), _make_phase("beta"), _make_phase("gamma")]
        router = RetryRouter(phases)

        assert router.next_phase_node(phases[0]) == "beta_execute"
        assert router.next_phase_node(phases[1]) == "gamma_execute"

    def test_last_phase_returns_end(self):
        phases = [_make_phase("alpha"), _make_phase("beta")]
        router = RetryRouter(phases)

        assert router.next_phase_node(phases[-1]) == END

    def test_phase_not_in_list_returns_end(self):
        """Guards against caller mismatch (phase object not present in pipeline)."""
        phases = [_make_phase("alpha")]
        router = RetryRouter(phases)

        stray = _make_phase("other")
        assert router.next_phase_node(stray) == END

    def test_single_phase_pipeline_returns_end(self):
        phases = [_make_phase("only")]
        router = RetryRouter(phases)

        assert router.next_phase_node(phases[0]) == END


class TestBuildRouteCallback:
    """`build_route_callback` returns a LangGraph-compatible closure."""

    def test_retry_feedback_with_retry_target_routes_to_target(self):
        phases = [_make_phase("alpha", retry_target="preflight"), _make_phase("beta")]
        router = RetryRouter(phases)

        route = router.build_route_callback(phases[0])
        state = _make_state(retry_feedback=["validator said no"])

        assert route(state) == "preflight_execute"

    def test_retry_feedback_without_retry_target_routes_to_same_phase(self):
        phases = [_make_phase("alpha"), _make_phase("beta")]
        router = RetryRouter(phases)

        route = router.build_route_callback(phases[0])
        state = _make_state(retry_feedback=["try again"])

        assert route(state) == "alpha_execute"

    def test_no_retry_feedback_routes_to_next_phase(self):
        phases = [_make_phase("alpha"), _make_phase("beta"), _make_phase("gamma")]
        router = RetryRouter(phases)

        route = router.build_route_callback(phases[1])
        state = _make_state()

        assert route(state) == "gamma_execute"

    def test_no_retry_feedback_on_last_phase_routes_to_end(self):
        phases = [_make_phase("alpha"), _make_phase("beta")]
        router = RetryRouter(phases)

        route = router.build_route_callback(phases[-1])
        state = _make_state()

        assert route(state) == END

    def test_each_callback_captures_its_own_phase(self):
        """Guards against the classic Python late-binding loop bug.

        Building route callbacks inside a for-loop over phases must not
        leak the loop variable — each callback must return the node
        name corresponding to its own phase, not the final phase.
        """
        phases = [_make_phase("a"), _make_phase("b"), _make_phase("c")]
        router = RetryRouter(phases)

        callbacks = [router.build_route_callback(p) for p in phases]
        state = _make_state(retry_feedback=["x"])

        assert callbacks[0](state) == "a_execute"
        assert callbacks[1](state) == "b_execute"
        assert callbacks[2](state) == "c_execute"
