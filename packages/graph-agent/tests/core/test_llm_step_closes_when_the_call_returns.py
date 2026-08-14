"""An LLM step closes when the call returns, not when the phase is over.

Announcing the start (PR #675) made the step appear while the work was
happening. Closing it stayed behind: an AGENT phase rebuilt its ``llm_call``
events from the message list after the inner graph returned, so every step a
phase opened stayed open until the phase ended. Measured on a real 162s run —
five steps still spinning after the run had finished and reported success.

The two halves belong to one owner. The call site knows when it started, when
it returned, and what it cost; nothing else has to reconstruct any of that.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from graph_agent.core.llm_provider import (
    FakeLLMProvider,
    LLMProviderChatModel,
    LLMProviderChunk,
)
from graph_agent.core.runner import run_skill


class Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        """The step frames, which is what "a step opened and closed" is about.

        Delta frames are filtered out because a pairing this file is checking
        should not change with how many pieces an answer happened to arrive in
        — that is the delta stream's business, and it is covered where it lives
        (``tests/tracing/test_delta_frames.py``).
        """
        return [
            getattr(event, "event_type", "?")
            for event in self.events
            if getattr(type(event), "persisted", True)
        ]


def test_a_call_reports_its_own_ending(reset_run_state: None = None) -> None:
    del reset_run_state
    recorder = Recorder()
    model = LLMProviderChatModel(
        provider=FakeLLMProvider(),
        role="analyst",
        phase_name="segment",
        event_callbacks=(recorder,),
    )

    model.invoke([HumanMessage(content="hi")])

    assert recorder.types() == ["prompt_captured", "llm_call"]


def test_every_call_is_a_closed_pair_rather_than_a_pile_of_starts() -> None:
    recorder = Recorder()
    model = LLMProviderChatModel(
        provider=FakeLLMProvider(),
        role="analyst",
        phase_name="segment",
        event_callbacks=(recorder,),
    )

    model.invoke([HumanMessage(content="one")])
    model.invoke([HumanMessage(content="two")])

    assert recorder.types() == [
        "prompt_captured",
        "llm_call",
        "prompt_captured",
        "llm_call",
    ]


def test_the_ending_carries_what_the_call_cost() -> None:
    recorder = Recorder()
    model = LLMProviderChatModel(
        provider=_provider_reporting_usage(),
        role="analyst",
        phase_name="segment",
        event_callbacks=(recorder,),
    )

    model.invoke([HumanMessage(content="hi")])

    ended = [e for e in recorder.events if e.event_type == "llm_call"]
    assert len(ended) == 1
    assert ended[0].input_tokens == 11
    assert ended[0].output_tokens == 7
    assert ended[0].resolved_model == "some-model-v2"


def test_the_ending_carries_how_the_provider_actually_ran_the_call() -> None:
    # The gateway reports the settings a call was really served with —
    # temperature after protocol translation, the token ceiling that applied —
    # on the answer's metadata. Those reach the reader through the ending event
    # or not at all, which is why the old reporter was tested for it too.
    settings = {"temperature": {"authored_value": 1.2, "provider_value": 0.6}}
    recorder = Recorder()

    class _SettingsProvider(FakeLLMProvider):
        def stream(self, request):  # type: ignore[override]
            self.requests.append(request)
            yield LLMProviderChunk(
                content="ok",
                metadata={"model_name": "claude-x", "actual_runtime_settings": settings},
            )

    model = LLMProviderChatModel(
        provider=_SettingsProvider(),
        role="analyst",
        phase_name="segment",
        event_callbacks=(recorder,),
    )
    model.invoke([HumanMessage(content="hi")])

    ended = [e for e in recorder.events if e.event_type == "llm_call"][0]
    assert ended.response_data is not None
    assert ended.response_data["actual_runtime_settings"] == settings
    assert ended.response_data["content"] == "ok"


def test_a_model_the_caller_brought_reports_its_calls_like_any_other() -> None:
    # ``run_skill(mock_llm=...)`` hands the engine a ready-made LangChain model.
    # It cannot report itself — the engine did not write it — so it enters
    # behind the provider Port and the one reporting model drives it.
    from graph_agent.core.llm_provider import ChatModelProvider

    recorder = Recorder()
    model = LLMProviderChatModel(
        provider=ChatModelProvider(_CannedChatModel()),
        role="analyst",
        phase_name="segment",
        event_callbacks=(recorder,),
    )

    answer = model.invoke([HumanMessage(content="hi")])

    assert recorder.types() == ["prompt_captured", "llm_call"]
    assert answer.content == "brought-along answer"


class _CannedChatModel(BaseChatModel):
    """The shape a caller's test double takes: one canned answer, no kwargs."""

    @property
    def _llm_type(self) -> str:
        return "canned"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="brought-along answer"))])


def _provider_reporting_usage() -> FakeLLMProvider:
    class _UsageProvider(FakeLLMProvider):
        def stream(self, request):  # type: ignore[override]
            self.requests.append(request)
            yield LLMProviderChunk(
                content="an answer",
                metadata={
                    "model_name": "some-model-v2",
                    "usage_metadata": {
                        "input_tokens": 11,
                        "output_tokens": 7,
                        "total_tokens": 18,
                    },
                },
            )

    return _UsageProvider()


GRAPH_MD = """---
schema_version: "v0.3.0"
name: closing-probe
description: Agent skill used to observe when a phase closes its LLM steps.
llm_role: analyst
io:
  inputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
  outputs:
    type: object
    required: [summary]
    properties:
      summary:
        type: string
phases: [work]
---
<phase depends_on="input" output>work</phase>
"""

SKILL_MD = """---
llm_role: analyst
io:
  inputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
  outputs:
    type: object
    required: [summary]
    properties:
      summary:
        type: string
tools: [finish_task]
max_iterations: 6
validator: false
---
<role>summariser</role>

<goal>Summarise the text and submit it through finish_task.</goal>

<step id="S1" name="finish">Call finish_task with the summary.</step>
"""


class RejectThenAcceptProvider(FakeLLMProvider):
    """Two model calls in one phase: the first submission is refused."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def stream(self, request):  # type: ignore[override]
        self.requests.append(request)
        self.calls += 1
        body = {"wrong": "no summary"} if self.calls == 1 else {"summary": "a summary"}
        payload = {
            "reasoning": "done",
            "business_data_md": "## item-1\n```json\n"
            + json.dumps(body, ensure_ascii=False)
            + "\n```\n",
        }
        yield LLMProviderChunk(
            content="",
            metadata={
                "tool_calls": [
                    {"name": "finish_task", "args": payload, "id": f"tc-{self.calls}"}
                ]
            },
        )


def _run_the_probe(tmp_path: Path) -> list[str]:
    skill = tmp_path / "closing-probe"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

    seen: list[str] = []
    run_skill(
        skill,
        workspace_dir=tmp_path / "ws",
        llm_provider=RejectThenAcceptProvider(),
        event_subscriber=lambda event: seen.append(event.event_type),
        unattended=True,
        text="hello",
    )
    return seen


def test_an_agent_phase_closes_each_step_before_opening_the_next(tmp_path: Path) -> None:
    seen = _run_the_probe(tmp_path)

    calls = [name for name in seen if name in {"prompt_captured", "llm_call"}]
    assert calls, "the phase made no LLM calls at all"
    # Strictly alternating: a start, its ending, the next start. A phase that
    # reports its endings in a batch produces starts stacked up front instead,
    # and every step between them is left saying it is still running.
    assert calls == ["prompt_captured", "llm_call"] * (len(calls) // 2)


def test_no_step_is_still_open_when_the_phase_ends(tmp_path: Path) -> None:
    seen = _run_the_probe(tmp_path)

    at_phase_end = seen.index("phase_end")
    before_end = seen[:at_phase_end]
    assert before_end.count("prompt_captured") == before_end.count("llm_call")


def test_an_ending_is_reported_once_and_not_by_two_reporters(tmp_path: Path) -> None:
    # The agent node used to rebuild the closing event from the message list and
    # the bridge used to report it from LangChain's own callback. Both on top of
    # the call site would have shown a run twice as busy as it was.
    seen = _run_the_probe(tmp_path)

    assert seen.count("llm_call") == seen.count("prompt_captured")


class _ThinkingProvider(FakeLLMProvider):
    """Streams reasoning the way a reasoning model does: before the answer."""

    def __init__(self, slices: list[LLMProviderChunk]) -> None:
        super().__init__()
        self._slices = slices

    def stream(self, request: Any) -> Any:
        self.requests.append(request)
        yield from self._slices


def test_the_ending_carries_the_thinking_that_produced_it() -> None:
    """The thinking channel gets the same guarantee as the answer: one whole
    copy on the closing frame. Deltas are droppable — that is only harmless
    when what they spell out is also written once, and until now the answer
    was and the thinking was not (a reasoning model that ends in a tool call
    leaves ``content`` empty, so the run's longest output had no record)."""
    recorder = Recorder()
    model = LLMProviderChatModel(
        provider=_ThinkingProvider([
            LLMProviderChunk(reasoning="First I compare the two clauses. "),
            LLMProviderChunk(reasoning="They disagree."),
            LLMProviderChunk(content="B", metadata={"model_name": "fake-m"}),
        ]),
        role="analyst",
        phase_name="segment",
        event_callbacks=(recorder,),
    )

    model.invoke([HumanMessage(content="pick one")])

    ended = next(e for e in recorder.events if getattr(e, "event_type", "") == "llm_call")
    assert ended.response_data["reasoning"] == "First I compare the two clauses. They disagree."


def test_a_restarted_answer_forgets_the_abandoned_attempts_thinking() -> None:
    recorder = Recorder()
    model = LLMProviderChatModel(
        provider=_ThinkingProvider([
            LLMProviderChunk(reasoning="draft A thinking"),
            LLMProviderChunk(content="truncated attempt"),
            # The restart marker is an empty chunk, exactly as the gateway
            # sends it: the voiding is the event, not a payload.
            LLMProviderChunk(restarts_answer=True),
            LLMProviderChunk(reasoning="draft B thinking"),
            LLMProviderChunk(content="final"),
        ]),
        role="analyst",
        phase_name="segment",
        event_callbacks=(recorder,),
    )

    model.invoke([HumanMessage(content="q")])

    ended = next(e for e in recorder.events if getattr(e, "event_type", "") == "llm_call")
    assert ended.response_data["reasoning"] == "draft B thinking"
    assert ended.response_data["content"] == "final"


def test_a_call_that_never_thought_says_so_rather_than_saying_nothing() -> None:
    """``reasoning`` is always present: None means "did not think", and a
    reader never has to guess whether the key was simply not written yet."""
    recorder = Recorder()
    model = LLMProviderChatModel(
        provider=FakeLLMProvider(),
        role="analyst",
        phase_name="segment",
        event_callbacks=(recorder,),
    )

    model.invoke([HumanMessage(content="q")])

    ended = next(e for e in recorder.events if getattr(e, "event_type", "") == "llm_call")
    assert "reasoning" in ended.response_data
    assert ended.response_data["reasoning"] is None
