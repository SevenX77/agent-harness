"""What a phase spent is answered by the calls it made, and only by those.

``PhaseEndEvent`` declared ``metrics: dict[str, Any]`` and the one place that
constructs it (``graph_assembler``) never passed the argument, so the field was
``{}`` on every emission ever made. Measured on the real app, run
``2026-08-20T13-14-59_14582c6b``: 42 ``phase_end`` events, 42 of them empty —
including phases that really did call a model four times.

A declared field that nothing fills is not a gap to be filled later; it is a
contract that lies. A reader cannot tell "this phase spent nothing" from "nobody
set this", and the type says the first.

Filling it would have been the worse of the two repairs. Per-phase spend already
has an answer: the ``llm_call`` events the phase made, which is what the run
report sums into its per-node ``tokens in/out`` column
(``apps/studio/backend/app/services/run_report.py``). Adding a second place that
answers the same question is the shape OB10 removed from run totals a day
earlier, and it would come back one level down. So the field is deleted, and the
rule it should have expressed is pinned here instead.

(Which EXECUTION of a phase a call belongs to is a different question, and the
events do not answer it yet — see ledger row E15.)
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from graph_agent.callbacks.events import PhaseEndEvent
from graph_agent.core.llm_provider import LLMProviderChunk, LLMProviderRequest
from graph_agent.core.runner import run_skill

#: Distinct per phase so a per-phase total cannot pass by accident.
TOKENS = {"prepare": (13, 5), "draft": (29, 17)}

#: Any of these on a phase lifecycle event would be a second answer.
_SPEND_WORDS = ("metric", "token", "spend", "cost", "usage")

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: phase-spend-one-answer
description: Two agent phases, each calling the model once.
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
    required: [draft]
    properties:
      draft:
        type: string
phases: [prepare, draft]
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>draft</phase>
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


class _PerPhaseProvider:
    """Reports a different, known usage depending on which phase is asking."""

    def __init__(self) -> None:
        self.call_count = 0

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        self.call_count += 1
        phase = str(request.metadata.get("phase_name") or "")
        input_tokens, output_tokens = TOKENS[phase]
        yield LLMProviderChunk(
            content="",
            metadata={
                "usage_metadata": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
                "tool_calls": [
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "done",
                            "business_data_md": "## result\n```json\n"
                            + json.dumps({phase: f"call#{self.call_count}"}, ensure_ascii=False)
                            + "\n```\n",
                        },
                        "id": f"tc-{self.call_count}",
                    }
                ],
            },
        )


class _EventLog:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def __call__(self, event: Any) -> None:
        self.events.append(event)

    def of_type(self, event_type: str) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", None) == event_type]


def _skill(tmp_path: Path) -> Path:
    skill = tmp_path / "phase-spend-fixture"
    skill.mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    for name in TOKENS:
        phase_dir = skill / "phases" / name
        phase_dir.mkdir(parents=True)
        (phase_dir / "SKILL.md").write_text(_phase_md(name), encoding="utf-8")
    return skill


def test_a_phase_lifecycle_event_does_not_carry_its_own_spend() -> None:
    """The contract itself, so nobody re-declares the rival field."""
    named = [
        field
        for field in PhaseEndEvent.model_fields
        if any(word in field.lower() for word in _SPEND_WORDS)
    ]
    assert not named, (
        f"PhaseEndEvent declares {named}; what a phase spent is answered by the "
        "llm_call events it made, and a second answer can only agree by accident"
    )


def test_what_a_phase_spent_is_recoverable_from_the_calls_it_reported(tmp_path: Path) -> None:
    provider = _PerPhaseProvider()
    log = _EventLog()

    result = run_skill(
        _skill(tmp_path),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        event_subscriber=log,
        topic="a topic",
    )

    assert result.success, getattr(result, "error", None)
    assert log.of_type("phase_end"), "no phase closed; the fixture proved nothing"

    spent: dict[str, tuple[int, int]] = {}
    for call in log.of_type("llm_call"):
        phase = call.phase_name
        seen = spent.get(phase, (0, 0))
        spent[phase] = (seen[0] + call.input_tokens, seen[1] + call.output_tokens)

    assert spent == TOKENS, spent
    # And the run total is those same calls, so the two levels cannot disagree.
    metrics = dict(result.metrics)
    assert metrics["total_input_tokens"] == sum(t[0] for t in TOKENS.values()), metrics
    assert metrics["total_output_tokens"] == sum(t[1] for t in TOKENS.values()), metrics
