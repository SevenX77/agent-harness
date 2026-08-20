"""What the branches of a fan-out spent is part of what the run spent.

Field evidence (2026-08-20). Run ``2026-08-20T11-30-38_df572662`` — made on a
vendor snapshot that already carried the iterate fix — reports
``626900/114065/740965`` in its ``report.md`` and ``474586/96642/571228`` in the
same directory's ``metrics.json``: 169737 tokens, 22.9%, missing from one of two
numbers shown on the same screen. The skill's heaviest node fans out seven ways.

Why it happened, and why it was structural. Every phase used to write its spend
into the ``flow`` channel as "the total I inherited plus what I spent". Under a
fan-out, N phases write that channel in one superstep, and ``flow``'s dict
fields are merged PER KEY — which loses nothing when branches touch different
keys (each phase writes its own name into ``phase_execution_ids``) but degrades
to last-writer-wins when they all write the same two token keys. One branch's
total became the run's total.

This is the second shape of one wrong premise, not a relapse of the first. The
iterate fix (2026-08-19) gave each child a zeroed base so siblings' increments
could be added; a value that carries an inherited base can only ever be merged
by overwriting it or by double-counting the base, and there is no third option.
So token counting left graph state entirely (OB10): a run's total is now
accumulated as each call reports itself, where no channel can drop it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from graph_agent.core.llm_provider import LLMProviderChunk, LLMProviderRequest
from graph_agent.core.runner import run_skill

from ._token_spend_invariant import CallRecorder, assert_totals_match_the_calls

INPUT_TOKENS_PER_CALL = 11
OUTPUT_TOKENS_PER_CALL = 7
BRANCHES = ("red", "green", "blue")
#: seed + one call per branch + join.
EXPECTED_CALLS = len(BRANCHES) + 2

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: parallel-token-accounting
description: One phase fanning out to three, then joining.
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
    required: [joined]
    properties:
      joined:
        type: string
phases: [seed, red, green, blue, joined]
---
<phase depends_on="input">seed</phase>
<phase depends_on="seed">red</phase>
<phase depends_on="seed">green</phase>
<phase depends_on="seed">blue</phase>
<phase depends_on="red,green,blue" output>joined</phase>
"""


def _phase_md(output_key: str) -> str:
    return f"""---
llm_role: analyst
validator: false
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    required: [{output_key}]
    properties:
      {output_key}:
        type: string
max_iterations: 3
---
<role>Echo.</role>

<goal>Work on {{topic}}.</goal>

<step id="S1" name="finish">Call finish_task.</step>
"""


class _CountingProvider:
    """Answers every call once, reporting a fixed, known token usage.

    The answer names the phase that asked, so each branch satisfies its own
    declared output schema and the fan-out actually completes.
    """

    def __init__(self) -> None:
        self.call_count = 0

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        self.call_count += 1
        phase = str(request.metadata.get("phase_name") or "")
        payload = {phase: f"call#{self.call_count}"}
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
                            "business_data_md": "## result\n```json\n"
                            + json.dumps(payload, ensure_ascii=False)
                            + "\n```\n",
                        },
                        "id": f"tc-{self.call_count}",
                    }
                ],
            },
        )


def _skill(tmp_path: Path) -> Path:
    skill = tmp_path / "parallel-fixture"
    skill.mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    for name in ("seed", *BRANCHES, "joined"):
        phase_dir = skill / "phases" / name
        phase_dir.mkdir(parents=True)
        (phase_dir / "SKILL.md").write_text(_phase_md(name), encoding="utf-8")
    return skill


def test_every_branch_of_a_fan_out_reaches_the_run_total(tmp_path: Path) -> None:
    provider = _CountingProvider()
    recorder = CallRecorder()

    result = run_skill(
        _skill(tmp_path),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        event_subscriber=recorder,
        topic="a topic",
    )

    assert result.success, getattr(result, "error", None)
    # Without this the fixture could "pass" on a graph that never fanned out.
    assert provider.call_count == EXPECTED_CALLS, provider.call_count

    metrics = dict(result.metrics)
    assert metrics["total_input_tokens"] == INPUT_TOKENS_PER_CALL * EXPECTED_CALLS, metrics
    assert metrics["total_output_tokens"] == OUTPUT_TOKENS_PER_CALL * EXPECTED_CALLS, metrics
    assert_totals_match_the_calls(metrics, recorder)
