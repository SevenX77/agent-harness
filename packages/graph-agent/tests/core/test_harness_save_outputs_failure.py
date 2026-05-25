"""Regression: ``_save_outputs_via_io`` must not silently swallow write
failures.

Pre-fix bug (2.2 in 2026-04-26 cohesion plan): the body of
``_save_outputs_via_io`` was::

    try:
        io_mgr.save_outputs(...)
    except Exception as exc:
        logger.warning("[Harness] Auto-save outputs failed: %s", exc)

i.e. *any* exception from the I/O layer (disk full, permission denied,
schema/target mismatch) was reduced to a single warning line and the run
was then reported as ``RunEndedEvent(status="completed")``. From the
caller's perspective the workflow had succeeded — but the artifact was
missing. The silent loss is the worst possible failure mode for an
artifact-producing pipeline.

Fixed contract: a ``save_outputs`` failure must propagate. The outer
``run()`` try/except converts it to ``InternalErrorEvent`` +
``RunEndedEvent(status="crashed")`` and re-raises, so callers know the
data did not land.
"""

from __future__ import annotations

from typing import Any

import pytest
from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import RunEndedEvent
from graph_agent.core.harness import GraphAgentHarness
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.core.types import Phase


class _CapturingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class _CompletedFakeGraph:
    """Returns a normal final state with no outstanding tasks (run completed)."""

    def __init__(self) -> None:
        self._business_fields: dict[str, Any] = {"some_output": "value"}
        self._flow_fields: dict[str, Any] = {
            "current_phase": "phase_a",
            "metrics": {"total_input_tokens": 0, "total_output_tokens": 0},
        }

    def invoke(self, initial_state, config=None) -> WorkflowState:
        return WorkflowState(
            data=BusinessData(**self._business_fields),
            flow=FrameworkState(**self._flow_fields),
            messages=[],
        )

    def get_state(self, config):
        from types import SimpleNamespace

        return SimpleNamespace(next=(), tasks=())


class _FakeModelResolver:
    def resolve(self, *args: Any, **kwargs: Any) -> object:
        raise AssertionError("fake graph tests must not resolve models")


def _build_harness_with_completed_graph(
    *, io_config: dict[str, Any] | None = None
) -> GraphAgentHarness:
    harness = GraphAgentHarness(
        phases=[Phase(name="phase_a", requires_llm=False)],
        io_config=io_config,
        model_resolver=_FakeModelResolver(),
    )
    harness._graph = _CompletedFakeGraph()
    return harness


class TestSaveOutputsFailurePropagates:
    def test_io_error_in_save_outputs_propagates(self, monkeypatch):
        """An IOError from save_outputs must bubble out of run()."""
        harness = _build_harness_with_completed_graph(
            io_config={"outputs": [{"name": "result", "target": "file", "path": "/x"}]}
        )

        def _broken_save(self, *args, **kwargs):
            raise OSError("disk full")

        from graph_agent.io.manager import IOManager

        monkeypatch.setattr(IOManager, "save_outputs", _broken_save)

        with pytest.raises(IOError, match="disk full"):
            harness.run(initial_context={"input": "x"})

    def test_run_marked_crashed_when_save_outputs_fails(self, monkeypatch):
        """RunEndedEvent must carry status='crashed' if outputs save failed."""
        capture = _CapturingCallback()
        harness = _build_harness_with_completed_graph(
            io_config={"outputs": [{"name": "result", "target": "file", "path": "/x"}]}
        )
        harness.callbacks.append(capture)

        def _broken_save(self, *args, **kwargs):
            raise PermissionError("read-only filesystem")

        from graph_agent.io.manager import IOManager

        monkeypatch.setattr(IOManager, "save_outputs", _broken_save)

        with pytest.raises(PermissionError):
            harness.run(initial_context={"input": "x"})

        run_ended = [e for e in capture.events if isinstance(e, RunEndedEvent)]
        assert len(run_ended) == 1
        assert run_ended[0].status == "crashed", (
            "When the outputs auto-save fails, the run is not actually "
            "complete — RunEndedEvent must carry status='crashed' so "
            "Studio's terminal-state UI does not falsely advertise "
            "successful completion. Status was "
            f"{run_ended[0].status!r}."
        )
