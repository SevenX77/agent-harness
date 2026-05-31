"""Regression guards for D-7.2 Phase B — run-state removed from GraphAgentHarness.

These tests lock in the invariants that make the concurrent-``child.run()``
race (the FIXME that lived at ``subgraph.py`` L120-131 before Phase B)
impossible to re-introduce:

  1. GraphAgentHarness instance no longer holds ``_active_heartbeat``
     or ``_active_run_context`` slots — they are local variables inside
     ``run()`` / ``resume()`` now, owned by the per-invocation
     PhaseExecutor and threaded through LangGraph config.
  2. PhaseExecutor no longer accepts a ``harness`` reference — the
     Phase-A scaffolding backdoor is closed.
  3. GraphBuilder no longer accepts a ``phase_executor`` parameter —
     executor flows through each node invocation via RunnableConfig.
  4. subgraph.py has no FIXME about concurrent-run race.

Why static checks: they are cheap, deterministic, and catch the exact
wrong shape ("a future refactor silently adds ``self._active_X = ...``
back somewhere"). A real multi-threaded behavioural test would require
a full DeerFlow agent loop runnable in a test fixture — out of scope.
"""

from __future__ import annotations

import inspect

import pytest

from graph_agent.core.graph_builder import GraphBuilder
from graph_agent.core.harness import GraphAgentHarness
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.types import Phase

pytestmark = pytest.mark.skip("GraphAgentHarness has been fully deprecated in V0.3.0")


class _FakeModelResolver:
    def resolve(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("invariant tests must not resolve models")


def _harness() -> GraphAgentHarness:
    return GraphAgentHarness(
        phases=[Phase(name="only", requires_llm=False)],
        model_resolver=_FakeModelResolver(),
    )


class TestHarnessHasNoRunState:
    """GraphAgentHarness instances do not carry per-run mutable state."""

    def test_no_active_heartbeat_after_construction(self):
        harness = _harness()
        assert not hasattr(harness, "_active_heartbeat"), (
            "Phase B removed _active_heartbeat from GraphAgentHarness instance; "
            "it moved to a per-run local variable held by PhaseExecutor. "
            "If this attribute comes back, two concurrent run() calls on the "
            "same harness will clobber each other's heartbeat state."
        )

    def test_no_active_run_context_after_construction(self):
        harness = _harness()
        assert not hasattr(harness, "_active_run_context"), (
            "Phase B removed _active_run_context from GraphAgentHarness instance; "
            "RunContext now flows through LangGraph RunnableConfig. Re-introducing "
            "the instance slot reopens the concurrent-child.run() race."
        )


class TestPhaseExecutorNoHarnessReference:
    """PhaseExecutor is stand-alone — no back-reference to GraphAgentHarness."""

    def test_constructor_rejects_harness_kwarg(self):
        """Phase-A scaffolding allowed ``PhaseExecutor(callbacks, harness=self)``.
        Phase B removed that kwarg; passing it must error."""
        import pytest

        with pytest.raises(TypeError, match="unexpected keyword argument.*harness"):
            PhaseExecutor([], harness=object())  # type: ignore[call-arg]

    def test_instance_has_no_harness_field(self):
        executor = PhaseExecutor([])
        assert not hasattr(executor, "_harness"), (
            "PhaseExecutor must not hold a harness reference post-Phase-B."
        )


class TestRunContextShallowImmutability:
    """Post-D session blind-spot-1: RunContext fields that collaborators
    receive by reference are shallowly immutable.

    Rationale: before this fix, ``ctx.runtime_inputs["x"] = 1`` and
    ``ctx.callbacks.append(cb)`` both silently succeeded — a surprise
    because the dataclass itself was ``frozen=True``. Runtime
    collaborators (``PhaseExecutor``, ``NudgeInjector``, subgraph nodes)
    hold the same reference, so a well-intentioned ``cache the lookup``
    line could clobber a sibling concurrent run. Freezing the containers
    (MappingProxyType + tuple) closes 99% of foot-guns at zero runtime
    cost; deep freeze is explicitly out of scope.
    """

    def test_runtime_inputs_is_mapping_proxy(self):
        import types

        from graph_agent.core.run_context import RunContext

        ctx = RunContext(thread_id="t", runtime_inputs={"k": "v"})
        assert isinstance(ctx.runtime_inputs, types.MappingProxyType)

    def test_callbacks_is_tuple(self):
        from graph_agent.core.run_context import RunContext

        ctx = RunContext(thread_id="t", callbacks=[])
        assert isinstance(ctx.callbacks, tuple)

    def test_runtime_inputs_top_level_mutation_raises(self):
        import pytest

        from graph_agent.core.run_context import RunContext

        ctx = RunContext(thread_id="t", runtime_inputs={"k": "v"})
        with pytest.raises(TypeError):
            ctx.runtime_inputs["new"] = "leak"  # type: ignore[index]

    def test_callbacks_has_no_append(self):
        import pytest

        from graph_agent.core.run_context import RunContext

        ctx = RunContext(thread_id="t", callbacks=[])
        with pytest.raises(AttributeError):
            ctx.callbacks.append(object())  # type: ignore[attr-defined]


class TestPhaseExecutorPickleGuard:
    """PhaseExecutor raises TypeError if pickled — protects against
    accidental LangGraph checkpointer persistence of the per-run object.

    Rationale: ``config['configurable']['_phase_executor']`` is threaded
    into LangGraph for in-memory propagation. If a future checkpointer
    upgrade (or a caller that wraps ``graph.invoke`` with its own
    persistence) tries to pickle the whole config, the executor's live
    references (heartbeat thread, bound sidecar method, callback list)
    would either fail opaquely or — worse — silently succeed with stale
    references on resume. ``__getstate__`` raising up-front turns this
    into an immediate TypeError with a clear message.
    """

    def test_pickling_phase_executor_raises_typeerror(self):
        import pickle

        import pytest

        executor = PhaseExecutor([])

        with pytest.raises(TypeError, match="per-run runtime object"):
            pickle.dumps(executor)


class TestGraphBuilderNoPhaseExecutor:
    """GraphBuilder receives PhaseExecutor per-invocation via config, not at init."""

    def test_constructor_signature_omits_phase_executor(self):
        params = inspect.signature(GraphBuilder.__init__).parameters
        assert "phase_executor" not in params, (
            "GraphBuilder.__init__ must not take phase_executor — the executor "
            "is threaded per-invocation via RunnableConfig['configurable']."
        )


class TestResumeRuntimeInputsRestore:
    """resume() accepts `runtime_inputs_map` so mid-run state recovery is possible.

    Pre-D-7.2 baseline had this hardcoded to {} — Gemini flagged it as a
    correctness gap on 2026-04-24 (downstream components like
    ``StorageManager.pipeline_prefix`` read runtime_inputs via
    ``_get_active_run_options``, so the empty-dict on resume silently
    diverges from the original run). This commit exposes the knob; the
    default (None → {}) preserves the historical behaviour.
    """

    def test_resume_signature_accepts_runtime_inputs_map(self):
        import inspect

        from graph_agent.core.harness import GraphAgentHarness

        sig = inspect.signature(GraphAgentHarness.resume)
        assert "runtime_inputs_map" in sig.parameters, (
            "resume() must accept runtime_inputs_map= so callers can restore "
            "per-run inputs across a HITL resume."
        )
        # Keyword-only default (None) preserves the historical {} behaviour.
        assert sig.parameters["runtime_inputs_map"].default is None

    def test_get_active_run_options_projects_runtime_inputs(self):
        from graph_agent.core.run_context import RunContext

        harness = _harness()
        ctx = RunContext(thread_id="t", runtime_inputs={"pipeline": "p1", "batch": 3})

        options = harness._get_active_run_options(ctx)

        # The dict is a shallow copy (mutating the projection must not leak back).
        assert options["runtime_inputs"] == {"pipeline": "p1", "batch": 3}
        options["runtime_inputs"]["mutation"] = "leak"
        assert "mutation" not in ctx.runtime_inputs

    def test_get_active_run_options_returns_empty_dict_when_no_run_context(self):

        harness = _harness()
        assert harness._get_active_run_options(None) == {}


class TestPersistentRuntimeInputsOptIn:
    """P0-2.1 post-D: ``run(persistent_runtime_inputs=, persistent_storage_config=)``
    opts a caller into checkpoint-durable state that ``resume()`` can rebuild
    from, closing the hardcoded ``storage_manager=None`` gap PR #3 left open.

    We verify the surface shape (signatures + pre-flight validation) with
    cheap static tests. End-to-end checkpoint round-trip is covered by the
    E-task golden baseline (integration territory, not unit scope).
    """

    def test_run_signature_accepts_persistent_kwargs(self):
        import inspect

        from graph_agent.core.harness import GraphAgentHarness

        sig = inspect.signature(GraphAgentHarness.run)
        assert "persistent_runtime_inputs" in sig.parameters, (
            "run() must accept persistent_runtime_inputs= for "
            "checkpoint-durable resume rehydration."
        )
        assert "persistent_storage_config" in sig.parameters, (
            "run() must accept persistent_storage_config= so resume() can "
            "rebuild StorageManager from the persisted workflow state."
        )
        assert sig.parameters["persistent_runtime_inputs"].default is None
        assert sig.parameters["persistent_storage_config"].default is None

    def test_non_serialisable_persistent_inputs_raise_at_run_entry(self):
        """Pre-flight json.dumps ensures a non-serialisable payload fails
        loudly at run() entry rather than silently later at checkpoint
        write (where the error path is deeper + harder to correlate).

        We use a minimal harness and push a ``set`` (json.dumps rejects
        sets) via persistent_runtime_inputs. The check must fire before
        the graph is invoked.
        """
        import pytest

        harness = _harness()

        with pytest.raises(ValueError, match="JSON-serialisable"):
            harness.run(
                initial_context={"thread_id": "t"},
                persistent_runtime_inputs={"bad": {1, 2, 3}},
            )

    def test_resume_rehydrates_runtime_inputs_from_state(self):
        """When resume() receives ``runtime_inputs_map=None`` but the
        replayed state carries ``_persistent_runtime_inputs`` (stashed by
        the original run()), resume() must pick it up.
        """
        from unittest.mock import patch

        harness = _harness()

        captured: dict[str, object] = {}

        class _FakeGraph:
            def invoke(self, state, config):
                # Capture the run_context threaded into config so the
                # assertion can inspect it.
                captured["run_context"] = config["configurable"]["_run_context"]
                return state

        from graph_agent.core.state import (
            BusinessData,
            FrameworkState,
            WorkflowState,
        )

        with patch.object(harness, "_graph", _FakeGraph()):
            harness.resume(
                state=WorkflowState(
                    data=BusinessData(),
                    flow=FrameworkState(
                        thread_id="t",
                        run_id="r-42",
                        persistent_runtime_inputs={"pipeline": "p", "n": 3},
                        metrics={"total_input_tokens": 0, "total_output_tokens": 0},
                    ),
                    messages=[],
                ),
                human_input="go",
            )

        rc = captured["run_context"]
        # runtime_inputs is MappingProxyType; == works against dicts.
        assert dict(rc.runtime_inputs) == {"pipeline": "p", "n": 3}


# TestSubgraphFixmeGone / TestSubgraphRequiresRunContext removed in MVP-0
# B1 (2026-04-28) along with subgraph.py itself. V2 cross-skill
# composition will introduce equivalent invariants for the new design.
