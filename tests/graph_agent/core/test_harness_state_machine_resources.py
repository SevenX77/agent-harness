"""Regression tests for harness state-machine edge cases and resources."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import RunEndedEvent
from graph_agent.callbacks.tracing import TracingCallback
from graph_agent.core.harness import GraphAgentHarness
from graph_agent.core.types import Phase


class _CapturingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class _CompletedFakeGraph:
    def __init__(self) -> None:
        self._final_state = {
            "context": {"some_output": "value", "output_dir": ""},
            "messages": [],
            "current_phase": "phase_a",
            "retry_counts": {},
            "metrics": {"total_input_tokens": 0, "total_output_tokens": 0},
        }

    def invoke(self, initial_state, config=None):
        return {
            **self._final_state,
            "context": dict(self._final_state["context"]),
        }

    def get_state(self, config):
        return SimpleNamespace(next=(), tasks=())


class _GetStateFailingGraph(_CompletedFakeGraph):
    def get_state(self, config):
        raise RuntimeError("checkpoint unavailable")


def _build_harness_with_graph(graph: Any) -> GraphAgentHarness:
    harness = GraphAgentHarness(phases=[Phase(name="phase_a", requires_llm=False)])
    harness._graph = graph
    return harness


class _FakeCheckpointerContext:
    def __init__(self) -> None:
        self.exited = False
        self.saver = _FakeSaver(self)

    def __enter__(self) -> "_FakeSaver":
        return self.saver

    def __exit__(self, exc_type, exc, tb) -> None:
        self.exited = True


class _FakeSaver:
    def __init__(self, cm: _FakeCheckpointerContext) -> None:
        self._cm = cm

    def use(self) -> str:
        if self._cm.exited:
            raise RuntimeError("closed")
        return "ok"


def test_close_exits_checkpointer_context_manager() -> None:
    harness = GraphAgentHarness.__new__(GraphAgentHarness)
    cm = _FakeCheckpointerContext()
    harness._checkpointer_cms = [cm]

    assert cm.saver.use() == "ok"
    harness.close()

    assert cm.exited is True
    with pytest.raises(RuntimeError, match="closed"):
        cm.saver.use()


def test_invalid_studio_checkpointer_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDIO_CHECKPOINTER", "not-a-valid-spec")

    with pytest.raises(ValueError, match="STUDIO_CHECKPOINTER='not-a-valid-spec'"):
        GraphAgentHarness(phases=[Phase(name="phase_a", requires_llm=False)])


def test_interrupt_detection_failure_crashes_without_autosave() -> None:
    capture = _CapturingCallback()
    harness = _build_harness_with_graph(_GetStateFailingGraph())
    harness.callbacks.append(capture)
    save_calls: list[dict[str, Any]] = []

    def _record(*args, **kwargs):
        save_calls.append({"args": args, "kwargs": kwargs})

    harness._io_config = {"outputs": [{"name": "some_output"}]}
    harness._save_outputs_via_io = _record  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="Post-invoke interrupt detection failed"):
        harness.run(initial_context={"input": "x"})

    assert save_calls == []
    run_ended = [e for e in capture.events if isinstance(e, RunEndedEvent)]
    assert len(run_ended) == 1
    assert run_ended[0].status == "crashed"


class _SavingTraceCallback(TracingCallback):
    def __init__(self) -> None:
        super().__init__()
        self.saved_to: list[Path] = []

    def save(self, output_dir: str | Path) -> str:
        self.saved_to.append(Path(output_dir))
        return str(Path(output_dir) / "trace.json")


def test_trace_callback_from_extra_callbacks_is_saved(tmp_path: Path) -> None:
    tracer = _SavingTraceCallback()
    harness = _build_harness_with_graph(_CompletedFakeGraph())
    result = harness.run(
        initial_context={"input": "x", "output_dir": str(tmp_path)},
        extra_callbacks=[tracer],
    )

    assert tracer.saved_to == [tmp_path]
    assert result["context"]["_trace_path"] == str(tmp_path / "trace.json")


class _FailingTraceCallback(TracingCallback):
    def save(self, output_dir: str | Path) -> str:
        raise IOError("trace disk full")


def test_trace_save_failure_is_recorded_in_context(tmp_path: Path) -> None:
    tracer = _FailingTraceCallback()
    harness = _build_harness_with_graph(_CompletedFakeGraph())
    result = harness.run(
        initial_context={"input": "x", "output_dir": str(tmp_path)},
        extra_callbacks=[tracer],
    )

    assert result["context"]["_io_errors"] == [
        "Trace save failed: trace disk full"
    ]
    assert result["context"]["_validation_warnings"] == [
        "Trace save failed: trace disk full"
    ]


def test_get_thread_status_snapshot_read_failure_is_crashed() -> None:
    harness = GraphAgentHarness.__new__(GraphAgentHarness)
    harness._checkpointer = object()
    harness._graph = _GetStateFailingGraph()

    result = harness.get_thread_status("thread-x")

    assert result["status"] == "CRASHED"
    assert "checkpoint unavailable" in result["reason"]
