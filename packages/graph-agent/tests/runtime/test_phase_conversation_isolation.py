"""A phase's agent starts its own conversation, not the previous phase's.

The user ruled this directly in the nine-round finalization, Round 8 item 3:

    3. phase 间默认强隔离（`messages = []` by-design）+ 按需挖掘机制（context_access opt-in）
    -- docs.backup-2026-05-20/archive/superpowers_history/
       2026-04-27-prompt-schema-9round-final-plan.md:79

and the current migration decision re-states it as binding
(`docs/design/2026-08-15-legacy-cognitive-features-migration-decision.md:184`:
"opt-in 语义是用户裁定的,必须原样保留"). Live code cites the same ruling —
`_cognitive_framework_tools` in `core/graph_assembler.py` says "the context-access
readers stay opt-in behind the phase's ``context_access`` declaration (Round 8:
strong isolation by default)" — and implements only the opt-in half. The default
half was never wired: `StateMapper.build_phase_input` handed every phase the
global `WorkflowState.messages` list.

That is not merely wasteful. Measured on run `2026-08-15T12-40-22_bb6e358a` of
`story-deconstruction-v3-lab`, the `continuity` phase opened with 61 messages of
which 60 belonged to other phases, and one of the inherited HumanMessages read
"工具 `finish_task` 在 phase `foreshadow` 中连续重复执行了 3 次" — a loop
diagnostic about a *different* phase, delivered as if it were an instruction to
this one. In the same run the `foreshadow` and `prop` phases opened on
`entity_and_characters`' finished conversation and submitted that phase's output
fields, which `finish_task` rejected as `Extra inputs are not permitted`.

A second, quieter effect rides along. The middleware that seeds a phase's
declared inputs as a JSON block fires only when the history holds NO HumanMessage
at all (`middleware/runtime_input.py:64`), and every nudge, dead-end warning and
loop diagnostic is written into the shared channel as a HumanMessage
(`middleware/exit_control.py:209,306,327`, `middleware/execution_control.py:271`,
`middleware/loop_detection.py:134`). So one nudge anywhere stops that block from
ever being delivered again — 38 `runtime_input_injected` events across 42 phase
executions in that run, with `continuity` and `settings` getting none. This is
not the same as a phase running blind: the authored system prompt interpolates
`{field}` placeholders itself, and continuity's did carry its data. What is lost
is the engine's own structured copy of the declared inputs.

Three more middlewares scan the whole history and so read another phase's
traffic as this one's: LoopDetection's five-message window, ExecutionControl's
dead-end scan, and Compaction's token count.

The global channel keeps accumulating every phase's messages, so trace,
checkpoint and HITL resume are untouched — only what a phase is *handed* changes.
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
name: phase-conversation-isolation
description: Two sequential agent phases.
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
    required: [beta_out]
    properties:
      beta_out:
        type: string
phases: [alpha, beta]
---
<phase depends_on="input">alpha</phase>
<phase depends_on="alpha" output>beta</phase>
"""

_ALPHA_MD = """---
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
    required: [alpha_out]
    properties:
      alpha_out:
        type: string
max_iterations: 5
validator: false
---
<role>PHASE_ALPHA_MARKER 你是 alpha。</role>

<goal>
输入:
```
{text}
```
</goal>

<step id="S1" name="finish">调用 finish_task 提交 alpha_out。</step>
"""

_BETA_MD = """---
llm_role: analyst
io:
  inputs:
    type: object
    required: [alpha_out]
    properties:
      alpha_out:
        type: string
  outputs:
    type: object
    required: [beta_out]
    properties:
      beta_out:
        type: string
max_iterations: 5
validator: false
---
<role>PHASE_BETA_MARKER 你是 beta。</role>

<goal>
上游产物:
```
{alpha_out}
```
</goal>

<step id="S1" name="finish">调用 finish_task 提交 beta_out。</step>
"""


class _RecordingProvider:
    """Fake provider that records what each phase's model call was handed.

    Alpha's first turn answers with plain text and no tool call, which is what
    ExitControlMiddleware nudges — that nudge is the HumanMessage that used to
    poison every later phase.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._alpha_turns = 0

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        messages = list(request.messages)
        head = str(getattr(messages[0], "content", "")) if messages else ""
        phase = (
            "alpha" if "PHASE_ALPHA_MARKER" in head
            else "beta" if "PHASE_BETA_MARKER" in head
            else "?"
        )
        humans = [m for m in messages if type(m).__name__ == "HumanMessage"]
        call_no = len(self.calls) + 1
        self.calls.append(
            {
                "phase": phase,
                "n_messages": len(messages),
                "human_texts": [str(getattr(m, "content", "")) for m in humans],
            }
        )
        if phase == "alpha":
            self._alpha_turns += 1
            if self._alpha_turns == 1:
                yield LLMProviderChunk(content="我先想一想。", metadata={})
                return
            payload: dict[str, Any] = {"alpha_out": "ALPHA_ANSWER"}
        else:
            payload = {"beta_out": "BETA_ANSWER"}
        yield LLMProviderChunk(
            content="",
            metadata={
                "tool_calls": [
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "done",
                            "business_data_md": "## out\n```json\n"
                            + json.dumps(payload, ensure_ascii=False)
                            + "\n```\n",
                        },
                        "id": f"tc-{call_no}",
                    }
                ]
            },
        )


def _run(tmp_path: Path) -> tuple[_RecordingProvider, Any]:
    skill = tmp_path / "phase-conversation-isolation"
    (skill / "phases" / "alpha").mkdir(parents=True)
    (skill / "phases" / "beta").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "alpha" / "SKILL.md").write_text(_ALPHA_MD, encoding="utf-8")
    (skill / "phases" / "beta" / "SKILL.md").write_text(_BETA_MD, encoding="utf-8")

    provider = _RecordingProvider()
    result = run_skill(
        skill,
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        text="TEXT_INPUT_MARKER",
    )
    return provider, result


def _first_call(provider: _RecordingProvider, phase: str) -> dict[str, Any]:
    return next(call for call in provider.calls if call["phase"] == phase)


def test_a_phase_opens_with_only_its_own_conversation(tmp_path: Path) -> None:
    provider, result = _run(tmp_path)
    assert result.success, getattr(result, "error", None)

    alpha_open = _first_call(provider, "alpha")["n_messages"]
    beta_open = _first_call(provider, "beta")["n_messages"]
    assert beta_open == alpha_open, (
        "beta must open the way alpha opened — a phase is an execution scope of "
        f"its own, not the next turn of a shared conversation. alpha={alpha_open}, "
        f"beta={beta_open}, calls={provider.calls}"
    )


def test_an_upstream_nudge_does_not_starve_the_next_phase_of_its_input(tmp_path: Path) -> None:
    """The user-visible half: RuntimeInput seeds only when no HumanMessage exists."""
    provider, result = _run(tmp_path)
    assert result.success, getattr(result, "error", None)

    alpha_texts = " ".join(_first_call(provider, "alpha")["human_texts"])
    assert "TEXT_INPUT_MARKER" in alpha_texts, provider.calls

    beta_texts = " ".join(_first_call(provider, "beta")["human_texts"])
    assert "ALPHA_ANSWER" in beta_texts, (
        "beta declares alpha_out as a required input; alpha's nudge must not stop "
        f"it from ever being handed that input. calls={provider.calls}"
    )


def test_a_phase_never_sees_another_phases_nudge(tmp_path: Path) -> None:
    provider, result = _run(tmp_path)
    assert result.success, getattr(result, "error", None)

    for call in provider.calls:
        if call["phase"] != "alpha":
            joined = " ".join(call["human_texts"])
            assert "未调用 finish_task" not in joined, (
                f"a nudge aimed at alpha reached {call['phase']}: {call}"
            )


def test_the_run_still_records_every_phases_messages(tmp_path: Path) -> None:
    """Isolation changes what a phase is handed, not what the run keeps.

    The global channel is what checkpoint/HITL resume read, so it must still
    accumulate both phases — otherwise this would be a data loss, not a fix.
    """
    provider, result = _run(tmp_path)
    assert result.success, getattr(result, "error", None)
    assert {call["phase"] for call in provider.calls} == {"alpha", "beta"}
    assert len(provider.calls) >= 3, provider.calls
