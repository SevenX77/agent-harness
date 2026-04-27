"""Tests for PR-7 parallel_delegate execution nodes."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig

from graph_agent.core import parallel_delegate as parallel_delegate_module
from graph_agent.core.graph_builder import GraphBuilder
from graph_agent.core.parallel_delegate import CompositeFailure, build_parallel_delegate_node
from graph_agent.core.retry_router import RetryRouter
from graph_agent.core.state import WorkflowState
from graph_agent.core.types import ContextBridge, Phase


def _make_state(
    context: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> WorkflowState:
    return {
        "context": dict(context or {}),
        "messages": [],
        "current_phase": "",
        "retry_counts": {},
        "metrics": dict(metrics or {}),
    }


def _config() -> RunnableConfig:
    return {"configurable": {"_run_context": object()}}


class _Harness:
    def __init__(self, run_options: dict[str, Any] | None = None) -> None:
        self.callbacks: list[Any] = []
        self.run_options = dict(run_options or {})

    def _get_active_run_options(self, _run_context: Any) -> dict[str, Any]:
        return dict(self.run_options)


class _RecordingCallback:
    def __init__(self) -> None:
        self.ends: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def on_phase_start(self, phase_name: str, context_snapshot: dict[str, Any]) -> None:
        del phase_name, context_snapshot

    def on_phase_end(
        self,
        phase_name: str,
        context_snapshot: dict[str, Any],
        metrics_snapshot: dict[str, Any],
    ) -> None:
        self.ends.append((phase_name, context_snapshot, metrics_snapshot))


class _Child:
    def __init__(
        self,
        name: str,
        *,
        barrier: threading.Barrier | None = None,
        fail: bool = False,
        mutate: bool = False,
        include_finish: bool = True,
        finish_result: dict[str, Any] | None = None,
        io_errors: list[str] | None = None,
        metrics: dict[str, Any] | None = None,
        calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self.barrier = barrier
        self.fail = fail
        self.mutate = mutate
        self.include_finish = include_finish
        self.finish_result = dict(finish_result or {"schema_validation": "passed"})
        self.io_errors = list(io_errors or [])
        self.metrics = dict(metrics or {})
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
        context = {**initial_context, "_last_output": self.name}
        if self.include_finish:
            context["_finish_task_result"] = dict(self.finish_result)
        if self.io_errors:
            context["_io_errors"] = list(self.io_errors)
        return {
            "context": context,
            "messages": [],
            "current_phase": self.name,
            "retry_counts": {},
            "metrics": dict(self.metrics),
        }


def _phase(children: list[Any], **kwargs: Any) -> Phase:
    return Phase(
        name="parallel_review",
        requires_llm=False,
        parallel_subgraphs=children,  # type: ignore[arg-type]
        reducer_path=kwargs.pop("reducer_path", "reducers.reduce_outputs"),
        **kwargs,
    )


def _patch_reducer(
    monkeypatch: pytest.MonkeyPatch,
    reducer: Callable[
        [dict[str, Any], list[dict[str, Any]], list[Exception]],
        dict[str, Any] | Any,
    ],
) -> None:
    monkeypatch.setattr(
        parallel_delegate_module,
        "_resolve_reducer_callable",
        lambda _path: reducer,
    )


class TestParallelDelegateExecution:
    def test_parallel_collects_outcomes_from_all_children(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        barrier = threading.Barrier(3)
        calls: list[dict[str, Any]] = []
        children = [
            _Child("a", barrier=barrier, calls=calls),
            _Child("b", barrier=barrier, calls=calls),
            _Child("c", barrier=barrier, calls=calls),
        ]
        _patch_reducer(
            monkeypatch,
            lambda _ctx, outputs, errors: {
                "child_count": len(outputs),
                "error_count": len(errors),
            },
        )
        node = build_parallel_delegate_node(
            _Harness({"thread_id": "parent-thread"}),
            _phase(children),
            logging.getLogger("test_parallel_delegate"),
        )

        state_out = node(_make_state({"topic": "x"}), _config())

        assert sorted(call["child"] for call in calls) == ["a", "b", "c"]
        assert {call["thread_id"] for call in calls} == {
            "parent-thread:parallel_review#0",
            "parent-thread:parallel_review#1",
            "parent-thread:parallel_review#2",
        }
        assert all(child.passed_barrier for child in children)
        assert state_out["context"]["child_count"] == 3
        assert state_out["context"]["error_count"] == 0

    def test_parallel_isolates_child_ctx_writes(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[dict[str, Any]] = []
        children = [
            _Child("a", mutate=True, calls=calls),
            _Child("b", mutate=True, calls=calls),
        ]
        _patch_reducer(monkeypatch, lambda _ctx, _outputs, _errors: {})
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

    def test_parallel_collects_exception_per_child(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.INFO, logger="test_parallel_delegate")
        calls: list[dict[str, Any]] = []
        captured: dict[str, Any] = {}
        children = [
            _Child("ok", calls=calls),
            _Child("boom", fail=True, calls=calls),
            _Child("also_ok", calls=calls),
        ]

        def reducer(
            _ctx: dict[str, Any],
            outputs: list[dict[str, Any]],
            errors: list[Exception],
        ) -> dict[str, Any]:
            captured["outputs"] = outputs
            captured["errors"] = errors
            return {"reduced": True}

        _patch_reducer(monkeypatch, reducer)
        node = build_parallel_delegate_node(
            _Harness(),
            _phase(children, tolerance=0.5),
            logging.getLogger("test_parallel_delegate"),
        )

        node(_make_state(), _config())

        assert sorted(call["child"] for call in calls) == ["also_ok", "boom", "ok"]
        assert "errors=1" in caplog.text
        assert len(captured["outputs"]) == 2
        assert [str(error) for error in captured["errors"]] == ["boom failed"]

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


class TestParallelDelegateReducer:
    def test_all_children_succeed_reducer_called_with_outputs(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        def reducer(
            ctx: dict[str, Any],
            child_outputs: list[dict[str, Any]],
            errors: list[Exception],
        ) -> dict[str, Any]:
            captured["ctx"] = dict(ctx)
            captured["child_outputs"] = child_outputs
            captured["errors"] = errors
            return {"summary": [item["_last_output"] for item in child_outputs]}

        _patch_reducer(monkeypatch, reducer)
        node = build_parallel_delegate_node(
            _Harness(),
            _phase([_Child("a"), _Child("b"), _Child("c")]),
            logging.getLogger("test_parallel_delegate"),
        )

        state_out = node(_make_state({"topic": "x"}), _config())

        assert captured["ctx"]["topic"] == "x"
        assert [item["_last_output"] for item in captured["child_outputs"]] == [
            "a",
            "b",
            "c",
        ]
        assert captured["errors"] == []
        assert state_out["context"]["summary"] == ["a", "b", "c"]

    def test_zero_tolerance_zero_failures_passes(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_reducer(monkeypatch, lambda _ctx, outputs, errors: {"ok": (len(outputs), len(errors))})
        node = build_parallel_delegate_node(
            _Harness(),
            _phase([_Child("a"), _Child("b")], tolerance=0.0),
            logging.getLogger("test_parallel_delegate"),
        )

        state_out = node(_make_state(), _config())

        assert state_out["context"]["ok"] == (2, 0)
        assert state_out["current_phase"] == "parallel_review"

    def test_zero_tolerance_one_failure_raises_composite(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reducer_called = False

        def reducer(
            _ctx: dict[str, Any],
            _child_outputs: list[dict[str, Any]],
            _errors: list[Exception],
        ) -> dict[str, Any]:
            nonlocal reducer_called
            reducer_called = True
            return {}

        _patch_reducer(monkeypatch, reducer)
        node = build_parallel_delegate_node(
            _Harness(),
            _phase([_Child("ok"), _Child("boom", fail=True)], tolerance=0.0),
            logging.getLogger("test_parallel_delegate"),
        )

        with pytest.raises(CompositeFailure) as exc_info:
            node(_make_state(), _config())

        assert reducer_called is False
        assert exc_info.value.phase_name == "parallel_review"
        assert exc_info.value.total == 2
        assert [(idx, str(exc)) for idx, exc in exc_info.value.failures] == [
            (1, "boom failed")
        ]

    def test_partial_failure_within_tolerance_proceeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        def reducer(
            _ctx: dict[str, Any],
            child_outputs: list[dict[str, Any]],
            errors: list[Exception],
        ) -> dict[str, Any]:
            captured["outputs"] = child_outputs
            captured["errors"] = errors
            return {"output_count": len(child_outputs), "error_count": len(errors)}

        _patch_reducer(monkeypatch, reducer)
        node = build_parallel_delegate_node(
            _Harness(),
            _phase([_Child("a"), _Child("boom", fail=True), _Child("c")], tolerance=0.5),
            logging.getLogger("test_parallel_delegate"),
        )

        state_out = node(_make_state(), _config())

        assert state_out["context"]["output_count"] == 2
        assert state_out["context"]["error_count"] == 1
        assert [str(error) for error in captured["errors"]] == ["boom failed"]

    def test_partial_failure_exceeds_tolerance_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_reducer(monkeypatch, lambda _ctx, _outputs, _errors: {})
        node = build_parallel_delegate_node(
            _Harness(),
            _phase(
                [_Child("a"), _Child("bad_a", fail=True), _Child("bad_b", fail=True)],
                tolerance=0.5,
            ),
            logging.getLogger("test_parallel_delegate"),
        )

        with pytest.raises(CompositeFailure) as exc_info:
            node(_make_state(), _config())

        assert exc_info.value.total == 3
        assert [idx for idx, _ in exc_info.value.failures] == [1, 2]

    def test_child_no_finish_task_counts_as_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_reducer(monkeypatch, lambda _ctx, outputs, errors: {"counts": (len(outputs), len(errors))})
        node = build_parallel_delegate_node(
            _Harness(),
            _phase([_Child("ok"), _Child("unfinished", include_finish=False)], tolerance=0.5),
            logging.getLogger("test_parallel_delegate"),
        )

        state_out = node(_make_state(), _config())

        assert state_out["context"]["counts"] == (1, 1)

    def test_child_schema_validation_failed_counts_as_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        def reducer(
            _ctx: dict[str, Any],
            child_outputs: list[dict[str, Any]],
            errors: list[Exception],
        ) -> dict[str, Any]:
            captured["outputs"] = child_outputs
            captured["errors"] = errors
            return {"ok": True}

        _patch_reducer(monkeypatch, reducer)
        node = build_parallel_delegate_node(
            _Harness(),
            _phase(
                [
                    _Child("ok"),
                    _Child(
                        "bad_schema",
                        finish_result={
                            "schema_validation": "failed",
                            "validation_error_text": "missing field",
                        },
                    ),
                ],
                tolerance=0.5,
            ),
            logging.getLogger("test_parallel_delegate"),
        )

        node(_make_state(), _config())

        assert len(captured["outputs"]) == 1
        assert "missing field" in str(captured["errors"][0])

    def test_reducer_raises_wrapped_in_composite_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def reducer(
            _ctx: dict[str, Any],
            _child_outputs: list[dict[str, Any]],
            _errors: list[Exception],
        ) -> dict[str, Any]:
            raise ValueError("reducer exploded")

        _patch_reducer(monkeypatch, reducer)
        node = build_parallel_delegate_node(
            _Harness(),
            _phase([_Child("ok")]),
            logging.getLogger("test_parallel_delegate"),
        )

        with pytest.raises(CompositeFailure) as exc_info:
            node(_make_state(), _config())

        assert exc_info.value.failures[0][0] == -1
        assert isinstance(exc_info.value.failures[0][1], ValueError)

    def test_reducer_returns_non_dict_raises_composite(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_reducer(monkeypatch, lambda _ctx, _outputs, _errors: ["not", "dict"])
        node = build_parallel_delegate_node(
            _Harness(),
            _phase([_Child("ok")]),
            logging.getLogger("test_parallel_delegate"),
        )

        with pytest.raises(CompositeFailure) as exc_info:
            node(_make_state(), _config())

        assert exc_info.value.failures[0][0] == -1
        assert "reducer must return dict" in str(exc_info.value.failures[0][1])

    def test_reducer_dict_merged_into_parent_ctx(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        callback = _RecordingCallback()
        harness = _Harness()
        harness.callbacks = [callback]
        _patch_reducer(monkeypatch, lambda _ctx, _outputs, _errors: {"final_summary": "x"})
        node = build_parallel_delegate_node(
            harness,
            _phase([_Child("ok")]),
            logging.getLogger("test_parallel_delegate"),
        )

        state_out = node(_make_state({"existing": "kept"}), _config())

        assert state_out["context"]["existing"] == "kept"
        assert state_out["context"]["final_summary"] == "x"
        assert callback.ends[0][0] == "parallel_review"
        assert callback.ends[0][1]["final_summary"] == "x"

    def test_io_errors_merged_from_children(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_reducer(monkeypatch, lambda _ctx, _outputs, _errors: {"done": True})
        node = build_parallel_delegate_node(
            _Harness(),
            _phase([
                _Child("a", io_errors=["missing alpha"]),
                _Child("b", io_errors=["missing beta"]),
            ]),
            logging.getLogger("test_parallel_delegate"),
        )

        state_out = node(_make_state({"_io_errors": ["parent issue"]}), _config())

        assert state_out["context"]["_io_errors"] == [
            "parent issue",
            "missing alpha",
            "missing beta",
        ]

    def test_metrics_skip_exception_children_without_state(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_reducer(monkeypatch, lambda _ctx, outputs, errors: {"counts": (len(outputs), len(errors))})
        node = build_parallel_delegate_node(
            _Harness(),
            _phase(
                [
                    _Child("a", metrics={"total_input_tokens": 2, "total_output_tokens": 3}),
                    _Child("bad", fail=True, metrics={"total_input_tokens": 100}),
                    _Child("b", metrics={"total_input_tokens": 5, "total_output_tokens": 7}),
                ],
                tolerance=0.5,
            ),
            logging.getLogger("test_parallel_delegate"),
        )

        state_out = node(
            _make_state(metrics={"total_input_tokens": 11, "total_output_tokens": 13}),
            _config(),
        )

        assert state_out["context"]["counts"] == (2, 1)
        assert state_out["metrics"]["total_input_tokens"] == 18
        assert state_out["metrics"]["total_output_tokens"] == 23

    def test_metrics_aggregated_from_failed_but_completed_children(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_reducer(monkeypatch, lambda _ctx, outputs, errors: {"counts": (len(outputs), len(errors))})
        node = build_parallel_delegate_node(
            _Harness(),
            _phase(
                [
                    _Child("ok", metrics={"total_input_tokens": 100, "total_output_tokens": 50}),
                    _Child(
                        "bad_schema",
                        finish_result={
                            "schema_validation": "failed",
                            "validation_error_text": "missing field",
                        },
                        metrics={"total_input_tokens": 200, "total_output_tokens": 80},
                    ),
                    _Child(
                        "unfinished",
                        include_finish=False,
                        metrics={"total_input_tokens": 150, "total_output_tokens": 60},
                    ),
                ],
                tolerance=1.0,
            ),
            logging.getLogger("test_parallel_delegate"),
        )

        state_out = node(_make_state(), _config())

        assert state_out["context"]["counts"] == (1, 2)
        assert state_out["metrics"]["total_input_tokens"] == 450
        assert state_out["metrics"]["total_output_tokens"] == 190
