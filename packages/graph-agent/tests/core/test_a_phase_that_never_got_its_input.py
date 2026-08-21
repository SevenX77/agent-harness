"""A phase that dies on its own input contract still reports that it ran.

E17 made a phase execution state how it ended. That fix only reaches executions
that *opened*, and one branch never opened: when a field the phase declares as a
required input is absent from the blackboard, the run dies with
``[F-v3-runtime-state-mapping-failed]`` and the phase emits nothing at all —
no ``phase_start``, no ``phase_end``. The node that killed the run draws as idle
on the canvas and has no row in the run report's Nodes table (ledger E18).

Two causes, both fixed here:

1. ``StateMapper`` fused two jobs into ``build_phase_input`` — projecting the
   blackboard down to this phase's declared inputs, and enforcing that the
   required ones are present. ``_emit_input_dispatch`` wants only the
   projection, but called the fused method, so the *reporting* path was what
   raised, before any lifecycle existed. They are now ``select_declared_inputs``
   and ``require_declared_inputs``.
2. The required-input check ran before the execution was announced. It is the
   phase's first step, not a precondition of the phase existing — the mirror of
   OB13's argument for the output validator being the phase's last step. It now
   runs after ``opened``.
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
name: missing-input-fixture
description: Two phases where the second needs something the first never writes.
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
phases: [first, second]
---
<phase depends_on="input">first</phase>

<phase depends_on="first" output>second</phase>
"""

# `note` is declared so the dataflow has a source the compiler can see, and left
# optional so the phase is free to finish without ever writing it. That gap is
# the whole fixture: it compiles clean and only comes apart at runtime.
_FIRST_MD = """---
llm_role: analyst
validator: false
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties:
      note:
        type: string
max_iterations: 2
---
<role>Finish without writing anything.</role>

<goal>End the phase.</goal>

<step id="S1" name="finish">Call finish_task.</step>
"""

_SECOND_MD = """---
llm_role: analyst
validator: false
io:
  inputs:
    type: object
    required: [note]
    properties:
      note:
        type: string
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


class _AnsweringProvider:
    """Finishes every phase, and never writes ``note``.

    The first model call belongs to 'first', which declares only the optional
    ``note`` — so it submits an empty block and legitimately ends having written
    nothing. Any later call would belong to 'second', which owes a ``verdict``.
    'second' is meant to die before it ever reaches the model, so if that second
    answer is ever used the fixture has stopped testing what it claims to.
    """

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        del request
        self.calls += 1
        submitted: dict[str, str] = {} if self.calls == 1 else {"verdict": "fine"}
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
                            + json.dumps(submitted)
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

    def of_type(self, event_type: str) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", None) == event_type]


def _skill(tmp_path: Path) -> Path:
    skill = tmp_path / "missing-input-fixture"
    (skill / "phases" / "first").mkdir(parents=True)
    (skill / "phases" / "second").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "first" / "SKILL.md").write_text(_FIRST_MD, encoding="utf-8")
    (skill / "phases" / "second" / "SKILL.md").write_text(_SECOND_MD, encoding="utf-8")
    return skill


def test_a_phase_whose_required_input_is_absent_still_opens_and_closes(tmp_path: Path) -> None:
    log = _EventLog()
    result = run_skill(
        _skill(tmp_path),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=_AnsweringProvider(),
        event_subscriber=log,
    )
    assert not result.success, (
        "'second' declares 'note' required and 'first' never writes it, so this "
        "run is supposed to die"
    )

    starts = [e for e in log.of_type("phase_start") if e.phase_name == "second"]
    ends = [e for e in log.of_type("phase_end") if e.phase_name == "second"]

    assert starts, (
        "'second' is the phase that killed the run, and it said nothing: with no "
        "phase_start the canvas leaves its node idle and the run report has no "
        "row for it"
    )
    assert ends, "an execution that opened always closes, however badly it went"
    assert [e.status for e in ends] == ["failed"] * len(ends), (
        f"the phase never got the input it declared, so it failed; got "
        f"{[e.status for e in ends]}"
    )
    assert [e.phase_execution_id for e in ends] == [e.phase_execution_id for e in starts], (
        "the end frame must name the execution the start frame opened"
    )


def test_the_phase_before_it_still_completes(tmp_path: Path) -> None:
    """The fixture must fail at 'second', not somewhere convenient upstream."""
    log = _EventLog()
    run_skill(
        _skill(tmp_path),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=_AnsweringProvider(),
        event_subscriber=log,
    )
    first_ends = [e for e in log.of_type("phase_end") if e.phase_name == "first"]
    assert [e.status for e in first_ends] == ["completed"], (
        f"'first' declares 'note' optional and finishes without it; got {first_ends}"
    )
