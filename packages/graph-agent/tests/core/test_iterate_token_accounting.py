"""What an iterated phase spent is part of what the run spent.

Field evidence (2026-08-19). Run ``2026-08-19T05-21-45``'s ``trace.jsonl`` holds
84 LLM calls totalling 687613 input / 98592 output tokens, while the same run
directory's ``metrics.json`` reports 0/0/0. In run
``2026-08-19T06-22``'s metadata the reported 147414/21323 is exactly the sum of
the only three phases in the whole graph that are NOT under an ``iterate`` — so
the loss is not a rounding error or a reporting bug downstream, it is every
call made inside an iterated phase.

Why it happens, and why it is structural rather than a missed line. A batch item
and a loop round run the phase node against a CHILD state, and that child state
is then discarded in favour of a channel delta built by
``_phase_outputs_delta``. Everything the child recorded that the delta does not
carry is gone — the same loss ``phase_execution_ids`` was already threaded out
by hand to avoid. Token spend was never threaded out.

The first fix (2026-08-19) kept the count in graph state and gave each child a
ZEROED base, so siblings reported increments that could be added. It made these
two fixtures pass and left the same premise standing, which a fan-out then broke
again (see ``test_parallel_token_accounting``). Token counting has since left
graph state altogether (OB10): a run's total is accumulated as each call reports
itself, so there is no child state for an iterate to discard the count with.

What these two fixtures pin is therefore unchanged and still worth running —
batch and loop really do run their phase against a child state, and the
invariant below says the run's total covers those calls anyway.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from graph_agent.core.llm_provider import LLMProviderChunk, LLMProviderRequest
from graph_agent.core.runner import run_skill

from ._token_spend_invariant import CallRecorder, assert_totals_match_the_calls

INPUT_TOKENS_PER_CALL = 11
OUTPUT_TOKENS_PER_CALL = 7
ITEMS = ["alpha", "beta", "gamma"]

_BATCH_GRAPH_MD = """---
schema_version: "v0.3.0"
name: iterate-token-accounting
description: One agent phase iterated over three items.
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

_BATCH_SKILL_MD = """---
llm_role: analyst
validator: false
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
max_iterations: 3
---
<role>Echo.</role>

<goal>
Handle this one item:
```
{item}
```
</goal>

<step id="S1" name="finish">Call finish_task with a summary.</step>
"""

_LOOP_GRAPH_MD = """---
schema_version: "v0.3.0"
name: loop-token-accounting
description: One agent phase looped over three items.
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
    required: [tally]
    properties:
      tally:
        type: object
phases: [work]
---
<phase depends_on="input" output>work</phase>
"""

_LOOP_SKILL_MD = """---
llm_role: analyst
validator: false
iterate:
  mode: loop
  over: items
  item_var: item
  accumulate:
    var: tally
    init: {}
    from: round_result
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
    required: [round_result]
    properties:
      round_result:
        type: object
max_iterations: 3
---
<role>Echo.</role>

<goal>
Handle this one item:
```
{item}
```
</goal>

<step id="S1" name="finish">Call finish_task with a round_result.</step>
"""


class _CountingProvider:
    """Answers every call once, reporting a fixed, known token usage."""

    def __init__(self, *, payload_builder: Any) -> None:
        self.call_count = 0
        self._payload_builder = payload_builder

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        del request
        self.call_count += 1
        payload = self._payload_builder(self.call_count)
        yield LLMProviderChunk(
            content="",
            metadata={
                "usage_metadata": {
                    "input_tokens": INPUT_TOKENS_PER_CALL,
                    "output_tokens": OUTPUT_TOKENS_PER_CALL,
                    "total_tokens": INPUT_TOKENS_PER_CALL + OUTPUT_TOKENS_PER_CALL,
                },
                "tool_calls": [
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "done",
                            "business_data_md": "## item-1\n```json\n"
                            + json.dumps(payload, ensure_ascii=False)
                            + "\n```\n",
                        },
                        "id": f"tc-{self.call_count}",
                    }
                ],
            },
        )


def _skill(tmp_path: Path, name: str, graph_md: str, skill_md: str) -> Path:
    skill = tmp_path / name
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(graph_md, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(skill_md, encoding="utf-8")
    return skill


def _metrics(result: Any) -> dict[str, Any]:
    return dict(result.metrics)


def test_a_batch_item_spend_reaches_the_run_total(tmp_path: Path) -> None:
    provider = _CountingProvider(payload_builder=lambda n: {"summary": f"call#{n}"})
    recorder = CallRecorder()

    result = run_skill(
        _skill(tmp_path, "batch-fixture", _BATCH_GRAPH_MD, _BATCH_SKILL_MD),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        event_subscriber=recorder,
        items=list(ITEMS),
    )

    assert result.success, getattr(result, "error", None)
    assert provider.call_count == len(ITEMS), provider.call_count
    metrics = _metrics(result)
    assert metrics["total_input_tokens"] == INPUT_TOKENS_PER_CALL * len(ITEMS), metrics
    assert metrics["total_output_tokens"] == OUTPUT_TOKENS_PER_CALL * len(ITEMS), metrics
    assert_totals_match_the_calls(metrics, recorder)


def test_a_loop_round_spend_reaches_the_run_total(tmp_path: Path) -> None:
    provider = _CountingProvider(
        payload_builder=lambda n: {"round_result": {f"call{n}": n}},
    )
    recorder = CallRecorder()

    result = run_skill(
        _skill(tmp_path, "loop-fixture", _LOOP_GRAPH_MD, _LOOP_SKILL_MD),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        event_subscriber=recorder,
        items=list(ITEMS),
    )

    assert result.success, getattr(result, "error", None)
    assert provider.call_count == len(ITEMS), provider.call_count
    metrics = _metrics(result)
    assert metrics["total_input_tokens"] == INPUT_TOKENS_PER_CALL * len(ITEMS), metrics
    assert metrics["total_output_tokens"] == OUTPUT_TOKENS_PER_CALL * len(ITEMS), metrics
    assert_totals_match_the_calls(metrics, recorder)


