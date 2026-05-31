"""Regression: AWAITING_INPUT detection must not let the run be marked
``completed`` and must not auto-save outputs.

Pre-fix bug (2.1 in 2026-04-26 cohesion plan):
``harness.run`` detects ``AWAITING_INPUT`` after ``self._graph.invoke``,
emits ``InterruptedEvent``, then **falls through** to ``_save_outputs_via_io``
and emits ``RunEndedEvent(status="completed")``. That has two consequences:

1. Outputs get saved before the user has provided the data the run is
   waiting on — partial / placeholder values land in the artifact store.
2. Studio receives ``RunEndedEvent(completed)`` and removes the run from
   the "needs input" queue, so the user can never resume it.

The contract: when the post-invoke state shows the run is paused on a
human-input interrupt, ``run`` must skip outputs auto-save and the
terminating ``RunEndedEvent`` must use ``status="interrupted"``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.skip("GraphAgentHarness has been fully deprecated in V0.3.0")

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import RunEndedEvent
from graph_agent.core.harness import GraphAgentHarness
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.core.types import Phase


class _CapturingCallback(Callback):
    """Records every event emitted via the callback bus."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class _AwaitingInputFakeGraph:
    """Stand-in for the LangGraph ``CompiledStateGraph``.

    ``invoke`` returns a normal-looking final state. ``get_state`` returns
    a snapshot that the harness's ``get_thread_status`` reads as
    ``AWAITING_INPUT`` (one task still pending and an interrupt with a
    clarification payload).
    """

    def __init__(self) -> None:
        self._business_fields: dict[str, Any] = {"some_output": "value"}
        self._flow_fields: dict[str, Any] = {
            "current_phase": "phase_a",
            "metrics": {"total_input_tokens": 0, "total_output_tokens": 0},
        }
        clarification = {
            "question": "Which environment?",
            "clarification_type": "approach_choice",
            "options": ["dev", "prod"],
        }
        interrupt = SimpleNamespace(value=clarification)
        task = SimpleNamespace(interrupts=(interrupt,))
        self._snapshot = SimpleNamespace(next=("phase_a",), tasks=(task,))

    def invoke(self, initial_state, config=None) -> WorkflowState:
        return WorkflowState(
            data=BusinessData(**self._business_fields),
            flow=FrameworkState(**self._flow_fields),
            messages=[],
        )

    def get_state(self, config):
        return self._snapshot


class _FakeModelResolver:
    def resolve(self, *args: Any, **kwargs: Any) -> object:
        raise AssertionError("fake graph tests must not resolve models")


def _build_harness_with_fake_graph(*, io_config: dict[str, Any] | None = None) -> GraphAgentHarness:
    """Build a real harness, then swap in a graph that simulates AWAITING_INPUT."""
    harness = GraphAgentHarness(
        phases=[Phase(name="phase_a", requires_llm=False)],
        io_config=io_config,
        model_resolver=_FakeModelResolver(),
    )
    harness._graph = _AwaitingInputFakeGraph()
    return harness


class TestAwaitingInputDoesNotCompleteRun:
    """The post-invoke AWAITING_INPUT detection must not finish the run."""

    def test_run_ended_event_uses_interrupted_status(self):
        capture = _CapturingCallback()
        harness = _build_harness_with_fake_graph()
        harness.callbacks.append(capture)

        harness.run(initial_context={"input": "x"})

        run_ended = [e for e in capture.events if isinstance(e, RunEndedEvent)]
        assert len(run_ended) == 1, (
            "Exactly one RunEndedEvent should fire per run; got "
            f"{len(run_ended)} of class {[type(e).__name__ for e in capture.events]}"
        )
        assert run_ended[0].status == "interrupted", (
            "When the post-invoke state is AWAITING_INPUT the terminating "
            "RunEndedEvent must carry status='interrupted'. Status was "
            f"{run_ended[0].status!r}, which falsely signals the run is done."
        )

    def test_outputs_are_not_auto_saved_while_awaiting_input(self):
        save_calls: list[dict[str, Any]] = []
        harness = _build_harness_with_fake_graph(io_config={"outputs": [{"name": "result"}]})

        def _record(*args, **kwargs):
            save_calls.append({"args": args, "kwargs": kwargs})

        harness._save_outputs_via_io = _record  # type: ignore[assignment]

        harness.run(initial_context={"input": "x"})

        assert save_calls == [], (
            "_save_outputs_via_io must not run when the workflow is paused "
            "on AWAITING_INPUT — partial outputs would corrupt the artifact "
            f"store. Got {len(save_calls)} call(s)."
        )
