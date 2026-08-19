"""An agent-loop iteration number belongs to ONE execution of the phase.

`AgentLoopIterationEvent` exists to give Studio a per-iteration anchor so the
LLMCall / ToolCall events fired during that turn can be grouped "rather than
just relying on timestamp order (which breaks once parallel_map sub-runs
interleave events)" (`callbacks/events.py`, class docstring). The identity
split is stated on the neighbouring field: `phase_execution_id` says WHICH
execution of the phase this is, and is "distinct from
``AgentLoopIterationEvent.iteration``, which counts model turns INSIDE one
execution" (`callbacks/events.py:56-62`, decision 2026-08-15
edge-as-run-segment D2).

Field evidence that it does not (run
`2026-08-19T01-56-15_d0733362`, skill `story-deconstruction-v3-lab`): the
`review` phase of the `event-extraction` subgraph is batched over 2 chapters,
and the two executions reported `agent_loop_iteration` numbers 1, 2, 3 and then
4, 5, 6, 7, 8 — one continuous counter across two independent executions, so
the second execution's first model turn is indistinguishable from the first
execution's fourth.

Root cause: `ExecutionControlMiddleware` keeps `self._iteration` as a plain
instance attribute, and `build_middleware_chain` is called once per phase node
at graph-assembly time (`core/graph_assembler.py`), so every invocation of that
node shares the instance. `ExitControlMiddleware`, built by the same call in
the same chain, already had to solve exactly this and keys its budgets by the
`agent_invocation_id` the assembler stamps on the invocation config.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from graph_agent.callbacks.events import AgentLoopIterationEvent, CallbackEvent
from graph_agent.core.llm_provider import LLMProviderChunk, LLMProviderRequest
from graph_agent.core.runner import run_skill

ITEM_1 = "MARKER_ITEM_1"
ITEM_2 = "MARKER_ITEM_2"
TURNS_PER_ITEM = 2

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: iteration-per-execution-fixture
description: One agent phase iterated over two items.
llm_role: analyst
io:
  inputs:
    type: object
    required: [items]
    properties:
      items:
        type: array
        items:
          type: string
  outputs:
    type: object
    required: [summary]
    properties:
      summary:
        type: array
        items:
          type: string
phases: [work]
---
<phase depends_on="input" output>work</phase>
"""

_SKILL_MD = """---
llm_role: analyst
iterate:
  mode: batch
  over: items
  item_var: item
io:
  inputs:
    type: object
    required: [item]
    properties:
      item:
        type: string
  outputs:
    type: object
    required: [summary]
    properties:
      summary:
        type: string
max_iterations: 20
validator: false
---
<role>你是标记回声器。</role>

<goal>
这一条要处理的项目是：
```
{item}
```
</goal>

<step id="S1" name="finish">调用 finish_task 提交 summary。</step>
"""


def _fixture_skill(tmp_path: Path) -> Path:
    skill = tmp_path / "iteration-per-execution-fixture"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    return skill


class _TwoTurnProvider:
    """Makes every item spend exactly `TURNS_PER_ITEM` model turns.

    The first submission of each item omits the required key, so the finish gate
    rejects it and that item goes round once more. Counting per item rather than
    per call keeps the turn count independent of how the two concurrent items
    interleave.
    """

    def __init__(self) -> None:
        self.turns_by_item: Counter[str] = Counter()

    @staticmethod
    def _goal_marker(request: LLMProviderRequest) -> str:
        head = str(getattr(request.messages[0], "content", "") or "") if request.messages else ""
        for marker in (ITEM_1, ITEM_2):
            if marker in head:
                return marker
        return "NO_MARKER"

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        marker = self._goal_marker(request)
        self.turns_by_item[marker] += 1
        turn = self.turns_by_item[marker]
        payload: dict[str, Any] = {} if turn < TURNS_PER_ITEM else {"summary": marker}
        yield LLMProviderChunk(
            content="",
            metadata={
                "tool_calls": [
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "done",
                            "business_data_md": "## item-1\n```json\n"
                            + json.dumps(payload, ensure_ascii=False)
                            + "\n```\n",
                        },
                        "id": f"tc-{marker}-{turn}",
                    }
                ]
            },
        )


def _iteration_numbers(tmp_path: Path) -> list[int]:
    seen: list[int] = []

    def collect(event: CallbackEvent) -> None:
        if isinstance(event, AgentLoopIterationEvent) and event.phase_name == "work":
            seen.append(event.iteration)

    run_skill(
        _fixture_skill(tmp_path),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=_TwoTurnProvider(),
        event_subscriber=collect,
        items=[ITEM_1, ITEM_2],
    )
    return seen


def test_each_batch_item_counts_its_own_model_turns(tmp_path: Path) -> None:
    numbers = _iteration_numbers(tmp_path)

    assert len(numbers) == 2 * TURNS_PER_ITEM, (
        "the fixture is meant to spend "
        f"{TURNS_PER_ITEM} model turns on each of 2 items; got {numbers}"
    )
    counts = Counter(numbers)
    assert counts == Counter({turn: 2 for turn in range(1, TURNS_PER_ITEM + 1)}), (
        "the two batch items share one iteration counter, so the second execution's "
        "first model turn is reported as a continuation of the first execution "
        f"instead of as turn 1 of its own. iteration numbers seen: {numbers}"
    )
