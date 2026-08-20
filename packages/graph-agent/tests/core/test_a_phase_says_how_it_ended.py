"""A phase execution ends by saying how it ended, not merely that it did.

Field evidence (2026-08-20, run ``2026-08-20T15-44-03_98726d7c``): a run that
died on ``[F-v3-agent-validator-failed]`` left a trace in which nothing said the
phase had failed — the finish_task verdict was ``accepted``, the exit decision
was ``exit_success``, and ``phase_end`` carried no outcome at all. The only
failure signal was the run-level ``run_ended status=crashed``. Both readers took
the phase at its word: the canvas drew the node that died as **Success**, and
the run report's Nodes table gave it **ok** (ledger E17).

The reader is not the problem. ``run-status-projection.ts`` already believes any
event that states its own outcome, and the report already groups by execution —
neither was told. What was missing is the producer saying it.

Two things this pins:

1. ``phase_end`` states the outcome, so "a phase ended without saying how" stops
   being representable.
2. The outcome covers the phase's whole execution, validator included. The
   validator checks the phase's declared output contract, which is part of doing
   the phase, not something that happens after it — so a phase whose output is
   rejected must not report ``completed`` and then let the run die elsewhere.
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
name: phase-outcome-fixture
description: One agent phase, so a single phase_end tells the whole story.
llm_role: analyst
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    required: [verdict]
    properties:
      verdict:
        type: string
phases: [only]
---
<phase depends_on="input" output>only</phase>
"""

_PHASE_MD = """---
llm_role: analyst
validator: {validator}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    required: [verdict]
    properties:
      verdict:
        type: string
max_iterations: 2
---
<role>Answer once.</role>

<goal>Produce a verdict.</goal>

<step id="S1" name="finish">Call finish_task with a verdict.</step>
"""

_REJECTING_VALIDATOR = '''
def validate(output, state_slice, **kwargs):
    """Reject every submission, so the phase's declared output never passes."""
    del output, state_slice, kwargs
    raise ValueError("this fixture rejects every submission by design")
'''


class _AnsweringProvider:
    def __init__(self) -> None:
        self.calls = 0

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        del request
        self.calls += 1
        yield LLMProviderChunk(
            content="",
            metadata={
                "usage_metadata": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
                "tool_calls": [
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "done",
                            "business_data_md": "## result\n```json\n"
                            + json.dumps({"verdict": "fine"})
                            + "\n```\n",
                        },
                        "id": f"tc-{self.calls}",
                    }
                ],
            },
        )


class _EventLog:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def __call__(self, event: Any) -> None:
        self.events.append(event)


def _skill(tmp_path: Path, *, validator: bool) -> Path:
    skill = tmp_path / "phase-outcome-fixture"
    phase_dir = skill / "phases" / "only"
    phase_dir.mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (phase_dir / "SKILL.md").write_text(
        _PHASE_MD.format(validator="true" if validator else "false"), encoding="utf-8"
    )
    if validator:
        (phase_dir / "validator.py").write_text(_REJECTING_VALIDATOR, encoding="utf-8")
    return skill


def _phase_ends(log: _EventLog) -> list[Any]:
    return [e for e in log.events if getattr(e, "event_type", None) == "phase_end"]


def test_a_phase_that_finished_says_it_completed(tmp_path: Path) -> None:
    log = _EventLog()
    result = run_skill(
        _skill(tmp_path, validator=False),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=_AnsweringProvider(),
        event_subscriber=log,
    )
    assert result.success, getattr(result, "error", None)

    ends = _phase_ends(log)
    assert ends, "no phase ended; the fixture proved nothing"
    assert [e.status for e in ends] == ["completed"] * len(ends)


def test_a_phase_whose_output_was_rejected_says_it_failed(tmp_path: Path) -> None:
    log = _EventLog()
    result = run_skill(
        _skill(tmp_path, validator=True),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=_AnsweringProvider(),
        event_subscriber=log,
    )
    assert not result.success, "the fixture's validator rejects everything"

    ends = _phase_ends(log)
    assert ends, (
        "the phase opened and died, so it must still close — a phase that never "
        "ends leaves its node running forever"
    )
    assert [e.status for e in ends] == ["failed"] * len(ends), (
        "the validator rejected this phase's declared output, so the phase did "
        f"not complete; got {[e.status for e in ends]}"
    )
