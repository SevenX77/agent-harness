"""An answer arrives in pieces; the pieces have to know where they belong.

A step frame says a call happened. A delta frame says a bit more of it just
arrived — which is only useful to someone who can tell WHICH call, because an
agent turn runs several at once. Position cannot answer that (the pieces of two
concurrent calls interleave) and the phase cannot either (both calls are in the
same phase), so the step's own identity has to travel on every piece.

The other half of the contract is that deltas are cheap to lose. That is only
true because the answer they spell out is also written down whole, once, on the
closing frame. So `response_data` is required rather than optional, and the
prompt is not written twice.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from graph_agent.callbacks.events import LLMCallEvent, LLMDeltaEvent, PromptCapturedEvent
from graph_agent.core.llm_provider import (
    LLMProviderChatModel,
    LLMProviderChunk,
    LLMProviderRequest,
)
from graph_agent.tracing.steps import StepReporter


class _Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def of(self, event_type: str) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", None) == event_type]


class _SlicedProvider:
    """A provider that answers in the pieces it was given."""

    def __init__(self, pieces: list[LLMProviderChunk]) -> None:
        self.pieces = pieces

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        del request
        yield from self.pieces


def _model(pieces: list[LLMProviderChunk], recorder: _Recorder) -> LLMProviderChatModel:
    return LLMProviderChatModel(
        provider=_SlicedProvider(pieces),
        role="graph_agent",
        phase_name="draft",
        event_callbacks=(recorder,),
    )


def test_a_delta_names_the_step_it_belongs_to() -> None:
    """Without this, a piece cannot be pinned to a row when calls overlap."""
    recorder = _Recorder()
    model = _model(
        [
            LLMProviderChunk(content="Hel"),
            LLMProviderChunk(content="lo"),
            LLMProviderChunk(content="", metadata={"model_name": "m"}),
        ],
        recorder,
    )

    model.invoke([HumanMessage(content="hi")])

    opened = recorder.of("prompt_captured")[0]
    closed = recorder.of("llm_call")[0]
    deltas = recorder.of("llm_delta")

    assert opened.step_id == closed.step_id, "both halves of one call must agree on its identity"
    assert [d.text for d in deltas] == ["Hel", "lo"]
    assert {d.step_id for d in deltas} == {opened.step_id}


def test_two_calls_in_one_phase_do_not_share_an_identity() -> None:
    """The phase cannot identify a step: an agent turn makes several calls in it."""
    recorder = _Recorder()
    model = _model([LLMProviderChunk(content="a", metadata={})], recorder)

    model.invoke([HumanMessage(content="one")])
    model.provider = _SlicedProvider([LLMProviderChunk(content="b", metadata={})])
    model.invoke([HumanMessage(content="two")])

    step_ids = [e.step_id for e in recorder.of("prompt_captured")]
    assert len(step_ids) == 2
    assert step_ids[0] != step_ids[1]


def test_reasoning_arrives_on_its_own_channel_and_is_not_the_answer() -> None:
    """Thinking is not what the model answered; folding it in corrupts the answer."""
    recorder = _Recorder()
    model = _model(
        [
            LLMProviderChunk(reasoning="let me think"),
            LLMProviderChunk(content="42"),
            LLMProviderChunk(content="", metadata={}),
        ],
        recorder,
    )

    answer = model.invoke([HumanMessage(content="hi")])

    assert answer.content == "42", "the reasoning must not end up in the answer"
    assert [(d.channel, d.text) for d in recorder.of("llm_delta")] == [
        ("thinking", "let me think"),
        ("text", "42"),
    ]


def test_an_abandoned_attempt_takes_its_deltas_back() -> None:
    """A retry replaces the answer, so the pieces already shown are no longer part of it."""
    recorder = _Recorder()
    model = _model(
        [
            LLMProviderChunk(content="half an ans"),
            LLMProviderChunk(restarts_answer=True),
            LLMProviderChunk(content="the whole answer"),
            LLMProviderChunk(content="", metadata={}),
        ],
        recorder,
    )

    answer = model.invoke([HumanMessage(content="hi")])

    assert answer.content == "the whole answer"
    restarts = [d for d in recorder.of("llm_delta") if d.restarts_step]
    assert len(restarts) == 1, "whoever is displaying the discarded text has to be told"
    assert restarts[0].text == ""


def test_a_delta_is_never_written_to_the_trace_file(tmp_path: Any) -> None:
    """Deltas are droppable; a droppable frame in a permanent record is a lie."""
    from graph_agent.callbacks.emit import _TraceJsonlSink

    sink = _TraceJsonlSink(tmp_path)
    sink.emit(LLMDeltaEvent(phase_name="draft", step_id="s1", channel="text", text="hi"))
    sink.emit(
        LLMCallEvent(
            phase_name="draft",
            step_id="s1",
            input_tokens=1,
            output_tokens=1,
            response_data={"content": "hi"},
        )
    )

    lines = [line for line in sink.path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    assert '"llm_call"' in lines[0]


def test_the_closing_frame_must_carry_the_answer() -> None:
    """Deltas may be dropped only because the whole answer is written down once."""
    with pytest.raises(ValidationError):
        LLMCallEvent(phase_name="draft", step_id="s1", input_tokens=0, output_tokens=0)  # type: ignore[call-arg]


def test_the_prompt_is_not_written_down_twice() -> None:
    """Two copies of one prompt is two truths that can drift, and the larger payload twice."""
    assert "messages" not in LLMCallEvent.model_fields


def test_a_step_that_produced_nothing_still_reports_both_halves() -> None:
    """An empty answer is an answer; the row must not stay open forever."""
    recorder = _Recorder()
    model = _model([LLMProviderChunk(content="", metadata={})], recorder)

    model.invoke([HumanMessage(content="hi")])

    assert len(recorder.of("prompt_captured")) == 1
    assert len(recorder.of("llm_call")) == 1
    assert recorder.of("llm_delta") == []


def test_the_reporter_is_the_only_place_a_step_identity_is_minted() -> None:
    """A caller that could pass its own id could pass the same one twice."""
    recorder = _Recorder()
    reporter = StepReporter(callbacks=(recorder,), phase_name="draft")

    with reporter.llm_call([HumanMessage(content="hi")]) as step:
        step.delta("piece", channel="text")
        step.finished(AIMessage(content="piece"))

    opened: PromptCapturedEvent = recorder.of("prompt_captured")[0]
    delta: LLMDeltaEvent = recorder.of("llm_delta")[0]
    assert delta.step_id == opened.step_id
    assert opened.step_id, "a step without an identity cannot own anything"
