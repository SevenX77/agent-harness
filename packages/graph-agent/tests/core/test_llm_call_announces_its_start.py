"""An LLM call says it is starting, and it says so from the call site.

A round-trip is the slowest thing in a run — minutes, against milliseconds for
everything around it. Announcing it only on the way out means the panel watching
the run has nothing to show for the whole time it matters.

The announcement used to be made by a proxy wrapped around the chat model, which
only worked for a caller that invoked the model directly. An AGENT phase hands
its model to ``create_agent`` and LangChain drives it through ``_generate``
instead, so that entire path — where the long work happens — announced nothing.
These tests pin the announcement to the one place both paths pass through: the
call itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from graph_agent.core.llm_provider import (
    FakeLLMProvider,
    LLMProviderChatModel,
    LLMProviderChunk,
)
from graph_agent.core.runner import run_skill


class RecordingCallback:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [getattr(event, "event_type", "?") for event in self.events]


class ProviderThatWatchesForTheAnnouncement(FakeLLMProvider):
    """Reports whether the call had been announced by the time it was asked to work."""

    def __init__(self, callback: RecordingCallback) -> None:
        super().__init__()
        self._callback = callback
        self.announced_before_work: list[bool] = []

    def stream(self, request):  # type: ignore[override]
        self.announced_before_work.append("prompt_captured" in self._callback.types())
        return super().stream(request)


def _model(provider: Any, callback: RecordingCallback) -> LLMProviderChatModel:
    return LLMProviderChatModel(
        provider=provider,
        role="analyst",
        phase_name="segment",
        event_callbacks=(callback,),
    )


def test_the_call_is_announced_before_the_provider_is_asked_to_do_anything() -> None:
    callback = RecordingCallback()
    provider = ProviderThatWatchesForTheAnnouncement(callback)

    _model(provider, callback).invoke([HumanMessage(content="hi")])

    assert provider.announced_before_work == [True]


def test_the_announcement_carries_what_was_asked() -> None:
    callback = RecordingCallback()

    _model(FakeLLMProvider(), callback).invoke(
        [SystemMessage(content="you summarise"), HumanMessage(content="this text")]
    )

    announced = [e for e in callback.events if e.event_type == "prompt_captured"]
    assert len(announced) == 1
    assert announced[0].phase_name == "segment"
    assert announced[0].llm_role == "analyst"
    assert [m["content"] for m in announced[0].resolved_prompt] == ["you summarise", "this text"]


def test_each_call_in_a_phase_is_numbered_in_order() -> None:
    callback = RecordingCallback()
    model = _model(FakeLLMProvider(), callback)

    model.invoke([HumanMessage(content="one")])
    model.invoke([HumanMessage(content="two")])
    model.invoke([HumanMessage(content="three")])

    numbering = [e.loop_index for e in callback.events if e.event_type == "prompt_captured"]
    assert numbering == [1, 2, 3]


def test_binding_tools_keeps_one_counter_rather_than_restarting_it() -> None:
    # The agent loop binds tools once and then invokes the BOUND copy over and
    # over. A counter that lived on the unbound original would report every call
    # as the first one.
    callback = RecordingCallback()
    bound = _model(FakeLLMProvider(), callback).bind_tools([])

    bound.invoke([HumanMessage(content="one")])
    bound.invoke([HumanMessage(content="two")])

    numbering = [e.loop_index for e in callback.events if e.event_type == "prompt_captured"]
    assert numbering == [1, 2]


GRAPH_MD = """---
schema_version: "v0.3.0"
name: announce-probe
description: Agent skill used to observe when a phase reports its LLM call.
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
max_iterations: 4
validator: false
---
<role>summariser</role>

<goal>Summarise the text and submit it through finish_task.</goal>

<step id="S1" name="finish">Call finish_task with the summary.</step>
"""


class SubmittingProvider(FakeLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def stream(self, request):  # type: ignore[override]
        self.requests.append(request)
        self.calls += 1
        payload = {
            "reasoning": "done",
            "business_data_md": "## item-1\n```json\n"
            + json.dumps({"summary": "a summary"}, ensure_ascii=False)
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


def test_an_agent_phase_announces_its_llm_call_before_reporting_it(tmp_path: Path) -> None:
    # The defect this whole change exists for: an AGENT phase reported `llm_call`
    # on the way out and nothing at all on the way in, so a run spent its entire
    # duration with no step to show.
    skill = tmp_path / "announce-probe"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

    seen: list[str] = []
    result = run_skill(
        skill,
        workspace_dir=tmp_path / "ws",
        llm_provider=SubmittingProvider(),
        event_subscriber=lambda event: seen.append(event.event_type),
        unattended=True,
        text="hello",
    )

    assert result.success is True
    assert "prompt_captured" in seen
    assert seen.index("prompt_captured") < seen.index("llm_call")


def test_an_agent_phase_says_which_template_made_its_prompt(tmp_path: Path) -> None:
    # The prompt panel promises the triple (template, variables, rendered): what
    # the prompt was made from, what it was made with, and what came out. An
    # AGENT prompt IS made from a template — the cognitive template, filled with
    # the phase's role / goal / steps — so reporting only the rendered result
    # hides the two inputs a reader needs to know WHY the prompt says what it
    # says, and leaves two fields of the contract that no producer ever fills.
    skill = tmp_path / "template-probe"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

    captured: list[Any] = []
    run_skill(
        skill,
        workspace_dir=tmp_path / "ws",
        llm_provider=SubmittingProvider(),
        event_subscriber=lambda event: captured.append(event),
        unattended=True,
        text="hello",
    )

    prompts = [e for e in captured if e.event_type == "prompt_captured"]
    assert prompts, "the phase never announced a prompt"
    for prompt in prompts:
        assert prompt.template_source, "no template named"
        assert prompt.variables, "no variables reported"
        # The values are the ones the template was actually filled with, not a
        # summary written beside it.
        assert prompt.variables["role"] == "summariser"
        assert prompt.variables["goal"].startswith("Summarise the text")
        assert [step["id"] for step in prompt.variables["steps"]] == ["S1"]
