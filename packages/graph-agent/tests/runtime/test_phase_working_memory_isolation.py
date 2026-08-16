"""A phase plans for itself: ``flow.working_memory`` is phase-local on input.

Companion to ``test_phase_conversation_isolation.py``. That one closed the
``messages`` inlet (decision
``.kiro/specs/decision-2026-08-16-a-phase-opens-its-own-conversation.md``);
its leftover #2 named ``flow.working_memory`` as the second cross-phase inlet
and left the ruling open. This module pins the ruling that closed it.

The defect is visible thirty lines apart inside one class.
``ExitControlMiddleware._own_finish_payload`` (``middleware/exit_control.py``)
qualifies the framework-state marker it reads by phase name — "The framework
state carries the previous phase's marker across the boundary, so only a marker
labelled with this phase's name counts." Its neighbour
``_working_memory_has_plan`` reads a value of exactly the same cross-boundary
shape and asks only whether the key ``plan`` is present. The writer had the
phase name in hand and did not use it: ``middleware/cognitive_flow.py`` stores
the plan under the constant key ``WORKING_MEMORY_PLAN_KEY = "plan"`` in the
same statement block that emits ``WorkingMemoryUpdateEvent(phase_name=...)``.

So one upstream plan silences the planning nudge for every later phase in the
run. The consequence is narrow and worth stating precisely: a downstream phase
that only talks — text out, no tool call — should be told to record a plan
first (``PLANNING_NUDGE``) and instead gets the generic "you didn't call
finish_task" text, because the planning gate believes a plan already exists.
This is NOT a bypassed safety gate: ``nudge_policy.try_planning`` declines on
``not latest_content or has_tool_calls or has_plan``, an OR — any tool call
already stands the gate down.

What belongs in the slot is phase-local by definition: ``PLANNING_NUDGE``
(``middleware/nudge_policy.py``) asks the model to record "1. 本阶段的目标是
什么". And working memory is not the cross-phase excavation channel — its twin
is. The two tool docstrings, which are the contract the model itself reads,
divide the work: ``query_working_memory`` reads "the current working-memory
plan text recorded by update_working_memory"; ``read_artifact`` reads "an
earlier phase's named output". ``context_access`` therefore means ``artifact``
for across phases and ``working_memory`` for within one.

Write-back is untouched, exactly as in the messages ruling: this is about what
a phase is HANDED, not what the run keeps. The flow channel merges
``working_memory`` per key (``core/state.py`` ``_FLOW_DICT_MERGE_FIELDS``), so
an emptied slot travels as an empty dict and unions to a no-op, while a phase
that does record a plan overwrites only the ``plan`` key. The iterate
bookkeeping key written beside it (``iterate_executions``,
``core/graph_assembler.py``) survives both — pinned below, because an isolation
that silently ate that key would be a regression traded for a fix.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from graph_agent.callbacks.events import CallbackEvent
from graph_agent.core.llm_provider import LLMProviderChunk, LLMProviderRequest
from graph_agent.core.runner import run_skill
from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    WorkflowState,
    merge_flow_channel,
)
from graph_agent.middleware.nudge_policy import PLANNING_NUDGE
from graph_agent.runtime.state_mapper import PhaseWrapper, StateMapper

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: phase-working-memory-isolation
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
max_iterations: 8
validator: false
---
<role>PHASE_ALPHA_MARKER 你是 alpha。</role>

<goal>
输入:
```
{text}
```
</goal>

<step id="S1" name="finish">先记计划,再调用 finish_task 提交 alpha_out。</step>
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
max_iterations: 8
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


def _finish_chunk(payload: dict[str, Any], call_no: int) -> LLMProviderChunk:
    return LLMProviderChunk(
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


class _PlanningProvider:
    """Alpha records a plan; beta then opens with text and no tool call.

    Alpha's script — talk, then ``update_working_memory``, then finish — is the
    minimum that leaves a ``plan`` key in the flow channel by the time beta
    starts. Beta's first turn is text-only on purpose: that is the one shape
    the planning gate judges.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._alpha_turns = 0
        self._beta_turns = 0

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
                "human_texts": [str(getattr(m, "content", "")) for m in humans],
            }
        )
        if phase == "alpha":
            self._alpha_turns += 1
            if self._alpha_turns == 1:
                yield LLMProviderChunk(content="我先想一想再动手。", metadata={})
                return
            if self._alpha_turns == 2:
                yield LLMProviderChunk(
                    content="",
                    metadata={
                        "tool_calls": [
                            {
                                "name": "update_working_memory",
                                "args": {"plan": "ALPHA_PLAN_MARKER 先读输入再提交。"},
                                "id": f"tc-{call_no}",
                            }
                        ]
                    },
                )
                return
            yield _finish_chunk({"alpha_out": "ALPHA_ANSWER"}, call_no)
            return

        self._beta_turns += 1
        if self._beta_turns == 1:
            yield LLMProviderChunk(content="这个我大概知道怎么做。", metadata={})
            return
        yield _finish_chunk({"beta_out": "BETA_ANSWER"}, call_no)


def _run(tmp_path: Path) -> tuple[_PlanningProvider, list[CallbackEvent], Any]:
    skill = tmp_path / "phase-working-memory-isolation"
    (skill / "phases" / "alpha").mkdir(parents=True)
    (skill / "phases" / "beta").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "alpha" / "SKILL.md").write_text(_ALPHA_MD, encoding="utf-8")
    (skill / "phases" / "beta" / "SKILL.md").write_text(_BETA_MD, encoding="utf-8")

    provider = _PlanningProvider()
    events: list[CallbackEvent] = []
    result = run_skill(
        skill,
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        event_subscriber=events.append,
        text="TEXT_INPUT_MARKER",
    )
    return provider, events, result


def _nudge_kinds(events: list[CallbackEvent], phase: str) -> list[str]:
    return [
        str(getattr(event, "nudge_type", ""))
        for event in events
        if getattr(event, "event_type", "") == "nudge"
        and getattr(event, "phase_name", "") == phase
    ]


def _phase_start_scratch(events: list[CallbackEvent], phase: str) -> Any:
    for event in events:
        if (
            getattr(event, "event_type", "") == "phase_start"
            and getattr(event, "phase_name", "") == phase
        ):
            return dict(getattr(event, "context", {}) or {}).get("scratch")
    raise AssertionError(f"no phase_start event for {phase}")


def test_a_downstream_phase_still_gets_its_planning_nudge(tmp_path: Path) -> None:
    """The user-visible half: an upstream plan must not silence the gate.

    Beta talks without calling a tool and holds no plan of its own, which is
    exactly the planning gate's trigger. While ``working_memory`` crossed the
    boundary, alpha's ``plan`` key answered for beta and the generic standard
    nudge fired instead.
    """
    provider, events, result = _run(tmp_path)
    assert result.success, getattr(result, "error", None)

    assert _nudge_kinds(events, "alpha") == ["planning"], events
    assert _nudge_kinds(events, "beta") == ["planning"], (
        "beta produced text, called no tool and had recorded no plan of its own "
        "— the planning gate is for exactly that. alpha's plan must not answer "
        f"in beta's place. nudges={_nudge_kinds(events, 'beta')}"
    )

    beta_calls = [call for call in provider.calls if call["phase"] == "beta"]
    assert len(beta_calls) >= 2, provider.calls
    assert PLANNING_NUDGE in " ".join(beta_calls[1]["human_texts"]), beta_calls


def test_a_phase_opens_with_an_empty_working_memory(tmp_path: Path) -> None:
    """Observed at the phase boundary itself, not inferred from the nudge."""
    _, events, result = _run(tmp_path)
    assert result.success, getattr(result, "error", None)

    assert _phase_start_scratch(events, "alpha") == {}
    assert _phase_start_scratch(events, "beta") == {}, (
        "beta opened holding alpha's working memory: "
        f"{_phase_start_scratch(events, 'beta')!r}"
    )


def test_the_phase_boundary_behaves_the_same_on_every_run(tmp_path: Path) -> None:
    """Deterministic watch on a reported, unexplained flip-flop.

    While investigating this defect the first three runs showed no
    cross-boundary working memory and every run after that leaked, with build
    caches, encoding, pytest capture and hash randomisation all ruled out and
    no cause established. That observation is unconfirmed, so it is not used as
    an argument anywhere; it is watched here instead. Repeating the identical
    scenario and demanding identical phase-boundary observations turns any
    future flip-flop into a failing test rather than a story.
    """
    observations = []
    for index in range(3):
        _, events, result = _run(tmp_path / f"run{index}")
        assert result.success, getattr(result, "error", None)
        observations.append(
            (
                tuple(_nudge_kinds(events, "alpha")),
                tuple(_nudge_kinds(events, "beta")),
                _phase_start_scratch(events, "alpha") == {},
                _phase_start_scratch(events, "beta") == {},
            )
        )

    assert observations == [(("planning",), ("planning",), True, True)] * 3, observations


def _mapper() -> StateMapper:
    return StateMapper(
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"out": {"type": "string"}}},
        phase_id="beta",
    )


def _global_state(working_memory: dict[str, Any]) -> WorkflowState:
    return WorkflowState(
        data=BusinessData.model_validate({"text": "T"}),
        flow=FrameworkState(working_memory=working_memory),
        messages=[],
    )


def _fold(state: WorkflowState, delta: dict[str, Any]) -> FrameworkState:
    return merge_flow_channel(state["flow"], delta["flow"])


def test_isolating_the_input_does_not_eat_the_iterate_bookkeeping(tmp_path: Path) -> None:
    """``iterate_executions`` shares the dict; only ``plan`` may be overwritten.

    ``core/graph_assembler.py`` appends one entry per graph-level batch/loop
    execution under ``iterate_executions`` in the same ``working_memory`` dict
    the plan lives in. The per-key union on the flow channel is what keeps the
    two writers apart; this pins that a phase writing its own plan through the
    emptied slot still folds into the existing bookkeeping.
    """
    del tmp_path
    executions = [{"scope": "graph", "mode": "batch", "checkpoint_ns": ["ns-1"]}]
    state = _global_state({"iterate_executions": executions, "plan": "UPSTREAM_PLAN"})
    mapper = _mapper()

    def node(phase_state: WorkflowState) -> WorkflowState:
        assert phase_state["flow"].working_memory == {}, phase_state["flow"].working_memory
        return WorkflowState(
            data=BusinessData.model_validate({"out": "O"}),
            flow=phase_state["flow"].model_copy(
                update={"working_memory": {"plan": "BETA_PLAN"}}
            ),
            messages=[],
        )

    delta = PhaseWrapper(mapper, node_kind="agent").wrap(node)(state)
    merged = _fold(state, delta)
    assert merged.working_memory == {
        "iterate_executions": executions,
        "plan": "BETA_PLAN",
    }, merged.working_memory


def test_a_phase_that_records_no_plan_writes_nothing_back(tmp_path: Path) -> None:
    """Emptying the input slot must stay a no-op on the way out.

    A phase that never calls ``update_working_memory`` hands the emptied slot
    straight back. The per-key union turns that empty dict into a no-op, so the
    global slot — plan and bookkeeping alike — is left exactly as it was.
    """
    del tmp_path
    before = {
        "iterate_executions": [{"scope": "graph", "mode": "loop", "checkpoint_ns": []}],
        "plan": "UPSTREAM_PLAN",
    }
    state = _global_state(dict(before))
    mapper = _mapper()

    def node(phase_state: WorkflowState) -> WorkflowState:
        return WorkflowState(
            data=BusinessData.model_validate({"out": "O"}),
            flow=phase_state["flow"],
            messages=[],
        )

    delta = PhaseWrapper(mapper, node_kind="agent").wrap(node)(state)
    assert _fold(state, delta).working_memory == before
