"""A batch item is an execution scope of its own, not a turn in a shared conversation.

Field evidence (run 2026-08-15T10-19-55_df555c19, skill story-deconstruction-v3-lab).
The `segmentation` subgraph iterates over 2 chapters. Item 1's `segment` phase burned
8 iterations and died; item 2's `segment` then started at iteration **9**, inherited an
already-spent nudge budget, and — while holding item 2's inputs (`chapter_number: 2`,
chapter 2's text) — recorded item 1's answer as its output:

    ctx.phase_outputs.segment.parsed_segments[0].description =
      "主角在现实世界中与张超会合、驱车前往露营地…" ← chapter ONE's story

Downstream `review` consumed that as chapter 2's summary. Nothing went red.

Root cause: `_phase_batch_runner` invokes each item through `_run_with_branch_index_async`,
which sets only the branch-index contextvar used for event labelling. Its graph-level twin
`_graph_batch_runner` uses `_run_with_iteration_context_async`, which also sets
`active_outer_ns` — the value `NamespaceCheckpointer._wrap_config` needs to give each item
its own checkpoint lane. Without it every item presents the agent graph the same
`(thread_id, checkpoint_ns)` pair, so item 2's `agent_graph.invoke` resumes item 1's
checkpoint (its whole message history) and `ExitControlMiddleware`, whose budget dicts are
keyed by that same pair, hands item 2 item 1's spent budget.

Both symptoms are asserted here because they fail independently: with a generous
`max_iterations` the history bleed is SILENT and the run reports success.
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
name: batch-item-isolation-fixture
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


def _skill_md(max_iterations: int) -> str:
    return f"""---
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
max_iterations: {max_iterations}
validator: false
---
<role>你是标记回声器。</role>

<goal>
这一条要处理的项目是：
```
{{item}}
```
</goal>

<step id="S1" name="finish">调用 finish_task 提交 summary。</step>
"""


ITEM_1 = "MARKER_ITEM_1"
ITEM_2 = "MARKER_ITEM_2"


def _fixture_skill(tmp_path: Path, *, max_iterations: int) -> Path:
    skill = tmp_path / "batch-item-isolation-fixture"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(
        _skill_md(max_iterations), encoding="utf-8"
    )
    return skill


class _MarkerEchoProvider:
    """Answers with the marker of whichever item framed THIS call's system prompt.

    It also keeps, per call, the markers found anywhere in the message list it was
    handed — which is how the bleed becomes visible: a clean item-2 call carries only
    ITEM_2, a contaminated one carries item 1's turns as well.

    The first `reject_first` calls submit a payload missing the required key, so the
    finish gate rejects them and the item burns iterations — the condition under which
    item 1 exhausted the shared budget in the field.
    """

    def __init__(self, *, reject_first: int = 0) -> None:
        self.calls: list[dict[str, Any]] = []
        self._reject_first = reject_first

    @staticmethod
    def _text_of(message: Any) -> str:
        """Everything the message carries, tool-call arguments included.

        A submitted answer lives in `tool_calls[*].args`, not in `.content` (which is
        ""), so a scan of message content alone cannot see a previous item's答案 sitting
        in the history — the exact blind spot that made the first draft of this test
        pass against the unfixed engine.
        """
        parts = [str(getattr(message, "content", "") or "")]
        for call in getattr(message, "tool_calls", None) or []:
            parts.append(json.dumps(call, ensure_ascii=False, default=str))
        parts.append(str(getattr(message, "name", "") or ""))
        return "\n".join(parts)

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        rendered = [self._text_of(msg) for msg in request.messages]
        goal_markers = [m for m in (ITEM_1, ITEM_2) if m in rendered[0]] if rendered else []
        all_text = "\n".join(rendered)
        call_no = len(self.calls) + 1
        self.calls.append(
            {
                "call_no": call_no,
                "n_messages": len(request.messages),
                "goal_markers": goal_markers,
                "markers_anywhere": [m for m in (ITEM_1, ITEM_2) if m in all_text],
            }
        )
        marker = goal_markers[0] if goal_markers else "NO_MARKER"
        payload: dict[str, Any] = (
            {} if call_no <= self._reject_first else {"summary": f"call#{call_no}|{marker}"}
        )
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
                        "id": f"tc-{call_no}",
                    }
                ]
            },
        )


def _run(tmp_path: Path, provider: _MarkerEchoProvider, *, max_iterations: int) -> Any:
    return run_skill(
        _fixture_skill(tmp_path, max_iterations=max_iterations),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        items=[ITEM_1, ITEM_2],
    )


def test_a_batch_item_does_not_see_the_previous_item_conversation(tmp_path: Path) -> None:
    """The silent half: with budget to spare the run goes green while item 2's model
    call carries item 1's entire history."""
    provider = _MarkerEchoProvider(reject_first=2)

    _run(tmp_path, provider, max_iterations=20)

    def _first_call_for(marker: str) -> dict[str, Any]:
        for call in provider.calls:
            if call["goal_markers"] == [marker]:
                return call
        raise AssertionError(f"{marker} never reached the model; calls={provider.calls}")

    first_of_item_1 = _first_call_for(ITEM_1)
    first_of_item_2 = _first_call_for(ITEM_2)

    # Self-calibrating: whatever an item's opening message list looks like, item 2's
    # must look the same. Item 1 opens the phase, so it is the reference.
    assert first_of_item_2["n_messages"] == first_of_item_1["n_messages"], (
        "item 2 did not start a fresh conversation — it resumed item 1's checkpoint. "
        f"item 1 opened with {first_of_item_1['n_messages']} message(s), "
        f"item 2 with {first_of_item_2['n_messages']}. calls={provider.calls}"
    )
    assert ITEM_1 not in first_of_item_2["markers_anywhere"], (
        "item 1's answer was sitting in item 2's message history — this is how a real "
        f"model comes to re-submit the previous item's work. calls={provider.calls}"
    )


def test_a_batch_item_gets_its_own_iteration_budget(tmp_path: Path) -> None:
    """The loud half: item 1 spends the budget, item 2 dies for it."""
    provider = _MarkerEchoProvider(reject_first=2)

    result = _run(tmp_path, provider, max_iterations=3)

    assert result.success, (
        "item 2 was killed by a budget item 1 spent: "
        f"{getattr(result, 'error', None)}; calls={provider.calls}"
    )


_LOOP_SKILL_MD = """---
llm_role: analyst
iterate:
  mode: loop
  over: items
  item_var: item
  accumulate:
    var: tally
    init: {}
    from: summary
    merge: merge
io:
  inputs:
    type: object
    required: [item, tally]
    properties:
      item:
        type: string
      tally:
        type: object
  outputs:
    type: object
    required: [summary]
    properties:
      summary:
        type: object
max_iterations: 20
validator: false
---
<role>你是标记回声器。</role>

<goal>
这一轮要处理的项目是：
```
{item}
```
</goal>

<step id="S1" name="finish">调用 finish_task 提交 summary。</step>
"""

_LOOP_GRAPH_MD = _GRAPH_MD.replace(
    """  outputs:
    type: object
    required: [summary]
    properties:
      summary:
        type: array
        items:
          type: string""",
    """  outputs:
    type: object
    required: [tally]
    properties:
      tally:
        type: object""",
)


class _LoopEchoProvider(_MarkerEchoProvider):
    """A loop round must submit an OBJECT under `summary` so it can be merged."""

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        rendered = [self._text_of(msg) for msg in request.messages]
        goal_markers = [m for m in (ITEM_1, ITEM_2) if m in rendered[0]] if rendered else []
        all_text = "\n".join(rendered)
        call_no = len(self.calls) + 1
        self.calls.append(
            {
                "call_no": call_no,
                "n_messages": len(request.messages),
                "goal_markers": goal_markers,
                "markers_anywhere": [m for m in (ITEM_1, ITEM_2) if m in all_text],
            }
        )
        marker = goal_markers[0] if goal_markers else "NO_MARKER"
        payload = {"summary": {marker: f"call#{call_no}"}}
        yield LLMProviderChunk(
            content="",
            metadata={
                "tool_calls": [
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "done",
                            "business_data_md": "## item-1\n```json\n"
                            + json.dumps(payload["summary"] and payload, ensure_ascii=False)
                            + "\n```\n",
                        },
                        "id": f"tc-{call_no}",
                    }
                ]
            },
        )


def test_a_loop_round_does_not_see_the_previous_round_conversation(tmp_path: Path) -> None:
    """`iterate.mode=loop` reaches the phase node through the same wrapper, and had
    the same missing identity — round 2 resuming round 1's conversation."""
    skill = tmp_path / "loop-isolation-fixture"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_LOOP_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(_LOOP_SKILL_MD, encoding="utf-8")

    provider = _LoopEchoProvider()
    run_skill(
        skill,
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        items=[ITEM_1, ITEM_2],
    )

    rounds = {}
    for call in provider.calls:
        if len(call["goal_markers"]) == 1:
            rounds.setdefault(call["goal_markers"][0], call)
    assert set(rounds) == {ITEM_1, ITEM_2}, provider.calls
    assert rounds[ITEM_2]["n_messages"] == rounds[ITEM_1]["n_messages"], (
        "round 2 did not start a fresh conversation. "
        f"round 1 opened with {rounds[ITEM_1]['n_messages']}, "
        f"round 2 with {rounds[ITEM_2]['n_messages']}. calls={provider.calls}"
    )
    # No marker assertion here, unlike the batch case: a loop's accumulator is
    # SUPPOSED to carry round 1's result into round 2, and it arrives as a declared
    # input in the seeded turn. Round 1's marker showing up in round 2's prompt is
    # therefore correct, and the message count is what separates "the accumulator
    # flowed" from "the conversation was inherited".


def test_a_lone_item_is_the_control(tmp_path: Path) -> None:
    """Whatever the fixture proves must not be an artefact of the fixture itself:
    the same phase, the same budget, one item, succeeds."""
    provider = _MarkerEchoProvider(reject_first=0)

    result = run_skill(
        _fixture_skill(tmp_path, max_iterations=3),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        items=[ITEM_2],
    )

    assert result.success, getattr(result, "error", None)
    assert len(provider.calls) == 1, provider.calls
    assert provider.calls[0]["markers_anywhere"] == [ITEM_2], provider.calls
