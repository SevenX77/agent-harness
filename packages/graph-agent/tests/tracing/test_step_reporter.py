"""One owner for "a step is running", so nobody has to assemble one by hand.

A step's two halves used to be built wherever they happened to be noticed: the
middleware minted an id, timed the call and dispatched both events itself; the
agent node built the closing event again with its own id. Nothing owned the
step, so every property of one — its identity, how long it took, who it belongs
to — was re-decided per site.

`StepReporter` owns it. Callers say what is happening; the reporter decides how
a step is reported.
"""

from __future__ import annotations

from typing import Any

from graph_agent.callbacks.events import ToolCallEvent, ToolCallStartedEvent
from graph_agent.tracing import StepReporter


class _Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []
        self.timeline: list[str] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)
        self.timeline.append(type(event).__name__)


class _ExplodingCallback:
    def on_event(self, event: Any) -> None:
        del event
        raise RuntimeError("a listener must not be able to abort the run")


def _reporter(*callbacks: Any) -> StepReporter:
    return StepReporter(callbacks=callbacks, phase_name="draft")


def test_a_tool_step_reports_both_halves_under_one_identity() -> None:
    recorder = _Recorder()

    with _reporter(recorder).tool_call(
        tool_call_id="call-1", tool_name="lookup", args={"topic": "ownership"}
    ) as step:
        step.finished("found it")

    started, finished = recorder.events
    assert isinstance(started, ToolCallStartedEvent)
    assert isinstance(finished, ToolCallEvent)
    assert started.tool_call_id == finished.tool_call_id == "call-1"
    assert started.tool_name == finished.tool_name == "lookup"
    assert started.phase_name == finished.phase_name == "draft"
    assert started.args == finished.args == {"topic": "ownership"}
    assert finished.result == "found it"


def test_the_step_is_announced_before_the_work_and_reported_after() -> None:
    recorder = _Recorder()

    with _reporter(recorder).tool_call(tool_call_id="call-1", tool_name="lookup") as step:
        recorder.timeline.append("work")
        step.finished("done")

    assert recorder.timeline == ["ToolCallStartedEvent", "work", "ToolCallEvent"]


def test_the_step_times_itself() -> None:
    """How long a step took is a property of the step, not of its caller."""
    recorder = _Recorder()

    with _reporter(recorder).tool_call(tool_call_id="call-1", tool_name="lookup") as step:
        step.finished("done")

    finished = recorder.events[-1]
    assert finished.duration_ms is not None
    assert finished.duration_ms >= 0.0


def test_a_step_nobody_finished_reports_only_that_it_started() -> None:
    """Some tools are answered elsewhere; the start is still worth reporting."""
    recorder = _Recorder()

    with _reporter(recorder).tool_call(tool_call_id="finish-1", tool_name="finish_task"):
        pass

    assert [type(e).__name__ for e in recorder.events] == ["ToolCallStartedEvent"]


def test_a_call_noticed_after_the_fact_reports_only_its_end() -> None:
    """Reconstructing a start that was never observed would be inventing one."""
    recorder = _Recorder()

    _reporter(recorder).completed_tool_call(
        tool_call_id="call-9",
        tool_name="finish_task",
        args={"reasoning": "done"},
        result="PHASE_COMPLETE",
        parent_node_id="draft",
        node_type="agent",
    )

    (event,) = recorder.events
    assert isinstance(event, ToolCallEvent)
    assert event.tool_call_id == "call-9"
    assert event.duration_ms is None, "a duration nobody measured must not be invented"
    assert event.node_type == "agent"
    assert event.parent_node_id == "draft"


def test_a_listener_that_raises_does_not_break_the_step() -> None:
    recorder = _Recorder()

    with _reporter(_ExplodingCallback(), recorder).tool_call(
        tool_call_id="call-1", tool_name="lookup"
    ) as step:
        step.finished("done")

    assert [type(e).__name__ for e in recorder.events] == [
        "ToolCallStartedEvent",
        "ToolCallEvent",
    ]


def test_a_reporter_with_no_listeners_is_still_usable() -> None:
    with StepReporter(callbacks=(), phase_name="draft").tool_call(
        tool_call_id="call-1", tool_name="lookup"
    ) as step:
        step.finished("done")
