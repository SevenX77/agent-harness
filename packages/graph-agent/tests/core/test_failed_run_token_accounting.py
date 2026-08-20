"""A run that died still spent what it spent.

Field evidence (2026-08-20, offline). A phase whose submissions never satisfy
its schema exhausts ``max_iterations`` and the run dies with
``[F-v3-agent-exit-control-failed]``. Its ``trace.jsonl`` holds 5 ``llm_call``
events worth 55/35 tokens — those calls were made, billed, and written down —
while ``result.metrics`` reports ``0/0/0``.

Why. ``run_skill``'s ``except GraphAgentError`` branch built a fresh
``WorkflowMetrics(wall_time_sec=...)`` because it had nothing else to build one
from: the run's spend ledger was created deeper in, inside
``_run_v030_skill_dict``, and an exception unwinds past it. So the exit that
reports a failure could not see what the failure cost, and every failed run
looked free.

The fix is an ownership one rather than a patch at the ``except``: the run's
event sink is per-run, its trace file lives in the run directory, and both exits
have to read the same ledger — so ``run_skill`` / ``resume_skill`` create it and
hand it down, instead of the inner function creating one that only the success
path can reach. Same discipline the run id already follows: decided once,
before anything can fail, so every exit reports the same values.
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
MAX_ITERATIONS = 3

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: failed-run-token-accounting
description: One agent phase that can never satisfy its own output schema.
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

_SKILL_MD = f"""---
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
    required: [summary]
    properties:
      summary:
        type: string
max_iterations: {MAX_ITERATIONS}
---
<role>Echo.</role>

<goal>Work on {{topic}}.</goal>

<step id="S1" name="finish">Call finish_task.</step>
"""


class _NeverSatisfiesTheSchema:
    """Submits the wrong shape every time, so the phase runs out of turns."""

    def __init__(self) -> None:
        self.call_count = 0

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        del request
        self.call_count += 1
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
                            + json.dumps({"not_the_summary": "x"}, ensure_ascii=False)
                            + "\n```\n",
                        },
                        "id": f"tc-{self.call_count}",
                    }
                ],
            },
        )


def _skill(tmp_path: Path) -> Path:
    skill = tmp_path / "failing-fixture"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    return skill


def test_a_failed_run_reports_the_tokens_it_spent(tmp_path: Path) -> None:
    provider = _NeverSatisfiesTheSchema()
    recorder = CallRecorder()

    result = run_skill(
        _skill(tmp_path),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        event_subscriber=recorder,
        topic="a topic",
    )

    # The fixture is only meaningful if the run really did fail after spending.
    assert result.success is False, "the fixture stopped failing; it proves nothing now"
    assert provider.call_count > 0, "no model call was made; nothing could have been lost"

    metrics = dict(result.metrics)
    assert_totals_match_the_calls(metrics, recorder)
    assert metrics["total_input_tokens"] == INPUT_TOKENS_PER_CALL * provider.call_count, metrics


def test_a_failed_run_writes_those_tokens_to_its_metrics_file(tmp_path: Path) -> None:
    """The artefact on disk is what the run list reads, so it has to carry it too."""
    provider = _NeverSatisfiesTheSchema()
    recorder = CallRecorder()
    workspace = tmp_path / "ws"

    result = run_skill(
        _skill(tmp_path),
        workspace_dir=workspace,
        unattended=True,
        llm_provider=provider,
        event_subscriber=recorder,
        topic="a topic",
    )

    assert result.success is False
    written = json.loads(
        (workspace / "runs" / result.run_id / "metrics.json").read_text(encoding="utf-8")
    )
    assert written["total_input_tokens"] == recorder.input_tokens, written
    assert written["total_output_tokens"] == recorder.output_tokens, written
