"""Tests for PR-7 parallel_delegate execution nodes."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig

from graph_agent.core.graph_builder import GraphBuilder
from graph_agent.core.parallel_delegate import build_parallel_delegate_node
from graph_agent.core.retry_router import RetryRouter
from graph_agent.core.state import WorkflowState
from graph_agent.core.types import ContextBridge, Phase


def _make_state(context: dict[str, Any] | None = None) -> WorkflowState:
    return {
        "context": dict(context or {}),
        "messages": [],
        "current_phase": "",
        "retry_counts": {},
        "metrics": {},
    }


def _config() -> RunnableConfig:
    return {"configurable": {"_run_context": object()}}


class _Harness:
    def __init__(self, run_options: dict[str, Any] | None = None) -> None:
        self.callbacks: list[Any] = []
        self.run_options = dict(run_options or {})

    def _get_active_run_options(self, _run_context: Any) -> dict[str, Any]:
        return dict(self.run_options)


class _Child:
    def __init__(
        self,
        name: str,
        *,
        barrier: threading.Barrier | None = None,
        fail: bool = False,
        mutate: bool = False,
        calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self.barrier = barrier
        self.fail = fail
        self.mutate = mutate
        self.calls = calls if calls is not None else []
        self.passed_barrier = False

    def run(
        self,
        *,
        initial_context: dict[str, Any],
        trace_dir: Any = None,
        thread_id: str | None = None,
        artifact_saver: Any = None,
        runtime_inputs_map: dict[str, Any] | None = None,
        extra_callbacks: list[Any] | None = None,
    ) -> WorkflowState:
        del trace_dir, artifact_saver, runtime_inputs_map, extra_callbacks
        self.calls.append(
            {
                "child": self.name,
                "initial_context": initial_context,
                "thread_id": thread_id,
            }
        )
        if self.barrier is not None:
            self.barrier.wait(timeout=2)
            self.passed_barrier = True
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        if self.mutate:
            initial_context["child_wrote"] = self.name
            initial_context["nested"]["value"] = self.name
        return {
            "context": {**initial_context, "_last_output": self.name},
            "messages": [],
            "current_phase": self.name,
            "retry_counts": {},
            "metrics": {},
        }


def _phase(children: list[Any], **kwargs: Any) -> Phase:
    return Phase(
        name="parallel_review",
        requires_llm=False,
        parallel_subgraphs=children,  # type: ignore[arg-type]
        reducer_path=kwargs.pop("reducer_path", "reducers.reduce_outputs"),
        **kwargs,
    )


class TestParallelDelegateExecution:
    def test_parallel_collects_outcomes_from_all_children(self) -> None:
        barrier = threading.Barrier(3)
        calls: list[dict[str, Any]] = []
        children = [
            _Child("a", barrier=barrier, calls=calls),
            _Child("b", barrier=barrier, calls=calls),
            _Child("c", barrier=barrier, calls=calls),
        ]
        node = build_parallel_delegate_node(
            _Harness({"thread_id": "parent-thread"}),
            _phase(children),
            logging.getLogger("test_parallel_delegate"),
        )

        with pytest.raises(NotImplementedError, match=r"Commit 3.*3 outcomes"):
            node(_make_state({"topic": "x"}), _config())

        assert sorted(call["child"] for call in calls) == ["a", "b", "c"]
        assert {call["thread_id"] for call in calls} == {
            "parent-thread:parallel_review#0",
            "parent-thread:parallel_review#1",
            "parent-thread:parallel_review#2",
        }
        assert all(child.passed_barrier for child in children)

    def test_parallel_isolates_child_ctx_writes(self) -> None:
        calls: list[dict[str, Any]] = []
        children = [
            _Child("a", mutate=True, calls=calls),
            _Child("b", mutate=True, calls=calls),
        ]
        phase = _phase(
            children,
            context_bridge=ContextBridge(inputs={"parent_value": "child_value"}),
        )
        node = build_parallel_delegate_node(
            _Harness(),
            phase,
            logging.getLogger("test_parallel_delegate"),
        )
        state = _make_state(
            {"parent_value": "shared", "nested": {"value": "original"}}
        )

        with pytest.raises(NotImplementedError, match="Commit 3"):
            node(state, _config())

        assert state["context"] == {
            "parent_value": "shared",
            "nested": {"value": "original"},
        }
        assert {call["initial_context"]["child_value"] for call in calls} == {"shared"}
        assert {call["initial_context"]["nested"]["value"] for call in calls} == {
            "a",
            "b",
        }

    def test_parallel_collects_exception_per_child(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger="test_parallel_delegate")
        calls: list[dict[str, Any]] = []
        children = [
            _Child("ok", calls=calls),
            _Child("boom", fail=True, calls=calls),
            _Child("also_ok", calls=calls),
        ]
        node = build_parallel_delegate_node(
            _Harness(),
            _phase(children),
            logging.getLogger("test_parallel_delegate"),
        )

        with pytest.raises(NotImplementedError, match="Commit 3"):
            node(_make_state(), _config())

        assert sorted(call["child"] for call in calls) == ["also_ok", "boom", "ok"]
        assert "errors=1" in caplog.text

    def test_parallel_raises_notimplemented_after_collection(self) -> None:
        completed: list[str] = []

        class _CompletingChild(_Child):
            def run(self, **kwargs: Any) -> WorkflowState:
                state = super().run(**kwargs)
                completed.append(self.name)
                return state

        children = [_CompletingChild("a"), _CompletingChild("b")]
        node = build_parallel_delegate_node(
            _Harness(),
            _phase(children),
            logging.getLogger("test_parallel_delegate"),
        )

        with pytest.raises(NotImplementedError, match="Commit 3"):
            node(_make_state(), _config())

        assert sorted(completed) == ["a", "b"]

    def test_parallel_requires_reducer_path(self) -> None:
        phase = _phase([_Child("a")], reducer_path=None)

        with pytest.raises(ValueError, match="requires reducer_path"):
            build_parallel_delegate_node(
                _Harness(),
                phase,
                logging.getLogger("test_parallel_delegate"),
            )

    def test_parallel_requires_subgraphs_non_empty(self) -> None:
        phase = Phase(
            name="parallel_review",
            requires_llm=False,
            reducer_path="reducers.reduce_outputs",
        )

        with pytest.raises(ValueError, match="no parallel_subgraphs"):
            build_parallel_delegate_node(
                _Harness(),
                phase,
                logging.getLogger("test_parallel_delegate"),
            )

    def test_graph_builder_routes_parallel_delegate_to_factory(self) -> None:
        calls: list[Phase] = []
        phase = _phase([_Child("a"), _Child("b")])

        def _noop_node(_phase: Phase) -> Callable[..., WorkflowState]:
            def _inner(state: WorkflowState, config: RunnableConfig) -> WorkflowState:
                del config
                return state

            return _inner

        def _factory(factory_phase: Phase) -> Callable[..., WorkflowState]:
            calls.append(factory_phase)
            return _noop_node(factory_phase)

        builder = GraphBuilder(
            [phase],
            retry_router=RetryRouter([phase]),
            checkpointer=None,
            subgraph_node_factory=_noop_node,
            parallel_delegate_node_factory=_factory,
        )

        graph = builder.build()

        assert graph.get_graph().nodes
        assert calls == [phase]
