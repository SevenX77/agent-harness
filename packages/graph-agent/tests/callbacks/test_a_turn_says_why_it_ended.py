"""The agent loop says why each turn ended — including when it ended well.

`ExitControlMiddleware.after_agent` is the gate that decides whether an agent
phase keeps going or stops. It has four answers, and until 2026-08-20 three of
them were written with `logger.info(...)` and nothing else:

    "Qualified finish_task marker observed. Exiting success."
    "Tool calls present but no valid finish marker. Jumping back to model."
    "No finish marker and no nudge condition. Jumping back to model."

Only the fourth — the nudge — reached the event stream, through `NudgeEvent`.
So the loop's most common outcome by far, a phase ending because its submission
was accepted, was invisible to every reader of a run: the trace showed a
`finish_task` call, a verdict, then `phase_end`, with nothing saying the exit
gate had agreed. Measured 2026-08-20 on a real 8-phase run
(`.workspace/runs/2026-08-19T06-58-15_179d1440/trace.jsonl`): 77 events, four
agent phases, zero events from the component that ended all four.

That is E4's "只给结果不给过程" in its most literal form. The engine already
writes these sentences — as `print`-grade log lines nobody in the product reads.

The rule this settles, so the next guard does not have to be argued case by
case: a component that DECIDES reports every decision it makes, and a guard that
only ASSERTS reports only when the assertion fails. `ExitControl` decides — the
loop continues or stops because of what it answered — so every answer is an
event now, including the planning gate on `after_model`, which redirects the
loop before `after_agent` ever runs. `ProtocolValidationMiddleware` asserts:
passing changes nothing and happens twice per model call, so it stays
failure-only.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from graph_agent.core.llm_provider import LLMProviderChunk, LLMProviderRequest
from graph_agent.core.runner import run_skill

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: exit-decision
description: One agent phase that submits and is accepted.
llm_role: analyst
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic:
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

_SKILL_MD = """---
llm_role: analyst
validator: false
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic:
        type: string
  outputs:
    type: object
    required: [summary]
    properties:
      summary:
        type: string
max_iterations: 4
---
<role>Echo.</role>

<goal>Summarize {topic}.</goal>

<step id="S1" name="finish">Call finish_task.</step>
"""

_FINISH_ARGS = {
    "reasoning": "done",
    "business_data_md": "## item-1\n```json\n"
    + json.dumps({"summary": "ok"}, ensure_ascii=False)
    + "\n```\n",
}


class _SubmitsAtOnce:
    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        del request
        yield LLMProviderChunk(
            content="",
            metadata={"tool_calls": [{"name": "finish_task", "args": _FINISH_ARGS, "id": "finish-1"}]},
        )


class _TalksThenSubmits:
    """A turn of bare text with no plan recorded — what the planning gate is for.

    Measured while writing this file: this shape never reaches `after_agent` at
    all. `after_model`'s planning gate catches it first and jumps straight back
    to the model, which is a FIFTH decision point and was emitting only a
    `NudgeEvent`. Under the same rule it now reports its decision too — a gate
    that redirects the loop has decided something, wherever it hangs.
    """

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        del request
        self.calls += 1
        if self.calls == 1:
            yield LLMProviderChunk(content="Thinking out loud, submitting nothing.", metadata={})
            return
        yield LLMProviderChunk(
            content="",
            metadata={"tool_calls": [{"name": "finish_task", "args": _FINISH_ARGS, "id": "finish-1"}]},
        )


class _Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def __call__(self, event: Any) -> None:
        self.events.append(event)

    def decisions(self) -> list[Any]:
        return [e for e in self.events if e.event_type == "agent_exit_decision"]


def _run(tmp_path: Path, provider: Any) -> _Recorder:
    skill = tmp_path / "exit-decision"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    recorder = _Recorder()
    result = run_skill(
        skill,
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        event_subscriber=recorder,
        topic="venus",
    )
    assert result.success, getattr(result, "error", None)
    return recorder


def test_a_phase_that_ends_well_says_so(tmp_path: Path) -> None:
    recorder = _run(tmp_path, _SubmitsAtOnce())

    decisions = recorder.decisions()
    assert [d.decision for d in decisions] == ["exit_success"], (
        f"the exit gate accepted the submission and said nothing; saw {recorder.events}"
    )
    decision = decisions[0]
    assert decision.phase_name == "work"
    assert decision.iteration >= 1
    assert "finish_task" in decision.message, (
        f"the sentence has to name what was accepted; got {decision.message!r}"
    )


def test_the_decision_lands_before_the_phase_it_ended_is_closed(tmp_path: Path) -> None:
    """Order is the whole point: a reason arriving after the ending explains nothing."""
    recorder = _run(tmp_path, _SubmitsAtOnce())

    types = [e.event_type for e in recorder.events]
    assert types.index("agent_exit_decision") < types.index("phase_end")


def test_a_nudged_turn_reports_continuing_not_finishing(tmp_path: Path) -> None:
    recorder = _run(tmp_path, _TalksThenSubmits())

    outcomes = [d.decision for d in recorder.decisions()]
    assert outcomes == ["continue_nudged", "exit_success"], (
        f"the loop went around once after a nudge and then finished; saw {outcomes}"
    )
    # The nudge event carries WHAT was said to the model; the decision carries
    # what the gate DID about it. Both, or the reader has half the story.
    assert any(e.event_type == "nudge" for e in recorder.events)
