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
from pathlib import Path

from graph_agent.core.graph_builder import GraphBuilder
from graph_agent.core.harness import GraphAgentHarness
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.types import Phase


class TestHarnessHasNoRunState:
    """GraphAgentHarness instances do not carry per-run mutable state."""

    def test_no_active_heartbeat_after_construction(self):
        harness = GraphAgentHarness(phases=[Phase(name="only", requires_llm=False)])
        assert not hasattr(harness, "_active_heartbeat"), (
            "Phase B removed _active_heartbeat from GraphAgentHarness instance; "
            "it moved to a per-run local variable held by PhaseExecutor. "
            "If this attribute comes back, two concurrent run() calls on the "
            "same harness will clobber each other's heartbeat state."
        )

    def test_no_active_run_context_after_construction(self):
        harness = GraphAgentHarness(phases=[Phase(name="only", requires_llm=False)])
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
        from graph_agent.core.harness import GraphAgentHarness
        from graph_agent.core.run_context import RunContext
        from graph_agent.core.types import Phase

        harness = GraphAgentHarness(phases=[Phase(name="only", requires_llm=False)])
        ctx = RunContext(thread_id="t", runtime_inputs={"pipeline": "p1", "batch": 3})

        options = harness._get_active_run_options(ctx)

        # The dict is a shallow copy (mutating the projection must not leak back).
        assert options["runtime_inputs"] == {"pipeline": "p1", "batch": 3}
        options["runtime_inputs"]["mutation"] = "leak"
        assert "mutation" not in ctx.runtime_inputs

    def test_get_active_run_options_returns_empty_dict_when_no_run_context(self):
        from graph_agent.core.harness import GraphAgentHarness
        from graph_agent.core.types import Phase

        harness = GraphAgentHarness(phases=[Phase(name="only", requires_llm=False)])
        assert harness._get_active_run_options(None) == {}


class TestSubgraphFixmeGone:
    """The concurrent-child.run() race FIXME was removed from subgraph.py."""

    def test_no_fixme_comment_for_d_7_2(self):
        subgraph_path = (
            Path(__file__).resolve().parents[3]
            / "src" / "core" / "graph_agent" / "core" / "subgraph.py"
        )
        content = subgraph_path.read_text(encoding="utf-8")
        assert "FIXME(D-7.2" not in content, (
            "subgraph.py still carries the D-7.2 FIXME — Phase B was meant "
            "to delete it once the underlying race was fixed."
        )


class TestSubgraphRequiresRunContext:
    """Subgraph nodes raise if RunContext is missing from RunnableConfig.

    After D-7.2 Phase B, every subgraph invocation reaches its node
    through ``harness.run()`` / ``.resume()``, which install the
    parent's RunContext into ``config['configurable']['_run_context']``.
    A missing key means either (a) a future refactor forgot to thread
    RunContext through a new entry point, or (b) a caller invoked the
    compiled graph directly bypassing ``run()``. Silent fallback to
    ``{}`` would re-open the correctness gap Phase B closed (subgraph
    trace_dir / storage_manager / runtime_inputs diverging from the
    parent). This test guards that the fallback was replaced with a
    RuntimeError.
    """

    def test_subgraph_execute_raises_when_run_context_missing(self):
        import logging

        import pytest
        from unittest.mock import MagicMock

        from graph_agent.core.subgraph import build_subgraph_node
        from graph_agent.core.types import Phase

        child = MagicMock()
        parent_phase = Phase(name="render", subgraph=child, requires_llm=False)
        parent_harness = MagicMock()
        parent_harness.callbacks = []

        node = build_subgraph_node(
            parent_harness, parent_phase, logging.getLogger("test_subgraph"),
        )

        state = {"context": {}, "messages": [], "current_phase": "",
                 "retry_counts": {}, "metrics": {}}

        # No ``_run_context`` in configurable — invariant violation.
        bad_config = {"configurable": {"thread_id": "t"}}

        with pytest.raises(RuntimeError, match="RunContext"):
            node(state, bad_config)  # type: ignore[arg-type]

    def test_subgraph_source_no_silent_none_fallback(self):
        """Defense in depth: grep-level check that the fallback branch
        was removed. Catches a well-meaning future edit that re-introduces
        the ``if parent_run_context is not None else {}`` shape.
        """
        subgraph_path = (
            Path(__file__).resolve().parents[3]
            / "src" / "core" / "graph_agent" / "core" / "subgraph.py"
        )
        content = subgraph_path.read_text(encoding="utf-8")
        assert "if parent_run_context is not None" not in content, (
            "subgraph.py still contains the silent-fallback conditional. "
            "Post-Phase-B, missing RunContext must raise RuntimeError."
        )
