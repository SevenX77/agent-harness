"""Characterization tests for Callback.on_event default dispatch."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import (
    AgentLoopIterationEvent,
    AmbiguityLoggedEvent,
    CompactionEvent,
    DeadEndPrunedEvent,
    LLMCallEvent,
    NudgeEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    PromptCapturedEvent,
    RunStartedEvent,
    ToolCallEvent,
    WorkingMemoryUpdateEvent,
)


class RecordingCallback(Callback):
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def on_phase_start(self, phase_name: str, context: dict[str, Any]) -> None:
        self.calls.append(("on_phase_start", phase_name, context))

    def on_phase_end(
        self,
        phase_name: str,
        context: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        self.calls.append(("on_phase_end", phase_name, context, metrics))

    def on_llm_call(
        self,
        phase_name: str,
        input_tokens: int,
        output_tokens: int,
        *,
        response_data: dict[str, Any],
    ) -> None:
        self.calls.append(("on_llm_call", phase_name, input_tokens, output_tokens, response_data))

    def on_tool_call(
        self,
        phase_name: str,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        *,
        duration_ms: float | None = None,
    ) -> None:
        self.calls.append(("on_tool_call", phase_name, tool_name, args, result, duration_ms))

    def on_nudge(
        self,
        phase_name: str,
        nudge_count: int,
        nudge_type: str = "standard",
    ) -> None:
        self.calls.append(("on_nudge", phase_name, nudge_count, nudge_type))

    def on_working_memory_update(
        self,
        phase_name: str,
        content_length: int,
    ) -> None:
        self.calls.append(("on_working_memory_update", phase_name, content_length))

    def on_dead_end_pruned(
        self,
        phase_name: str,
        summary: str,
    ) -> None:
        self.calls.append(("on_dead_end_pruned", phase_name, summary))

    def on_compaction(
        self,
        phase_name: str,
        removed_message_count: int,
    ) -> None:
        self.calls.append(("on_compaction", phase_name, removed_message_count))


@pytest.mark.parametrize(
    ("event", "expected_call"),
    [
        (
            PhaseStartEvent(phase_name="plan", context={"topic": "baseline"}),
            ("on_phase_start", "plan", {"topic": "baseline"}),
        ),
        (
            PhaseEndEvent(
                phase_name="plan",
                context={"status": "done"},
                metrics={"tokens": 3},
            ),
            ("on_phase_end", "plan", {"status": "done"}, {"tokens": 3}),
        ),
        (
            LLMCallEvent(
                phase_name="draft",
                step_id="step-1",
                input_tokens=11,
                output_tokens=22,
                response_data={"id": "resp-1"},
            ),
            ("on_llm_call", "draft", 11, 22, {"id": "resp-1"}),
        ),
        (
            ToolCallEvent(
                tool_call_id="call-1",
                phase_name="draft",
                tool_name="read_file",
                args={"path": "a.md"},
                result="ok",
                duration_ms=12.5,
            ),
            ("on_tool_call", "draft", "read_file", {"path": "a.md"}, "ok", 12.5),
        ),
        (
            NudgeEvent(phase_name="draft", nudge_count=3, nudge_type="deadline"),
            ("on_nudge", "draft", 3, "deadline"),
        ),
        (
            WorkingMemoryUpdateEvent(
                phase_name="draft",
                content_length=128,
                content="full text ignored by legacy hook",
            ),
            ("on_working_memory_update", "draft", 128),
        ),
        (
            DeadEndPrunedEvent(phase_name="research", summary="discard branch"),
            ("on_dead_end_pruned", "research", "discard branch"),
        ),
        (
            CompactionEvent(
                phase_name="research",
                removed_message_count=4,
                removed_summary="summary ignored by legacy hook",
                content_ref="sidecar.json",
            ),
            ("on_compaction", "research", 4),
        ),
    ],
)
def test_on_event_dispatches_legacy_hook_for_legacy_event_shapes(
    event: object,
    expected_call: tuple[Any, ...],
) -> None:
    callback = RecordingCallback()

    callback.on_event(event)  # type: ignore[arg-type]

    assert callback.calls == [expected_call]


def test_on_event_dispatches_nudge_default_type_to_legacy_hook() -> None:
    callback = RecordingCallback()

    callback.on_event(NudgeEvent(phase_name="draft", nudge_count=1))

    assert callback.calls == [("on_nudge", "draft", 1, "standard")]


@pytest.mark.parametrize(
    "event",
    [
        PromptCapturedEvent(
            phase_name="draft",
            step_id="step-1",
            resolved_prompt=[{"role": "user", "content": "hello"}],
        ),
        RunStartedEvent(run_id="run-1", thread_id="thread-1", initial_context={"x": 1}),
        AmbiguityLoggedEvent(
            phase_name="draft",
            ambiguity_type="scope",
            question="which file?",
            decision="use current file",
        ),
    ],
)
def test_on_event_typed_only_events_log_debug_without_legacy_hook(
    caplog: pytest.LogCaptureFixture,
    event: object,
) -> None:
    callback = RecordingCallback()

    with caplog.at_level(logging.DEBUG, logger="graph_agent.callbacks.base"):
        callback.on_event(event)  # type: ignore[arg-type]

    assert callback.calls == []
    assert "no legacy hook" in caplog.text
    assert type(event).__name__ in caplog.text


def test_on_event_unknown_object_logs_warning_without_legacy_hook(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class UnknownEvent:
        pass

    callback = RecordingCallback()

    with caplog.at_level(logging.WARNING, logger="graph_agent.callbacks.base"):
        callback.on_event(UnknownEvent())  # type: ignore[arg-type]

    assert callback.calls == []
    assert "unrecognised event type UnknownEvent" in caplog.text


def test_on_event_current_callback_union_event_without_default_branch_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    callback = RecordingCallback()

    with caplog.at_level(logging.WARNING, logger="graph_agent.callbacks.base"):
        callback.on_event(AgentLoopIterationEvent(phase_name="draft", iteration=2))

    assert callback.calls == []
    assert "unrecognised event type AgentLoopIterationEvent" in caplog.text
