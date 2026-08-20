"""An event says which phase execution it happened in, instead of a reader guessing.

Field evidence (2026-08-20, run ``2026-08-20T13-14-59_14582c6b``). ``LLMCallEvent``
carries ``phase_name`` but no execution id, so the run report charges a call to
"whichever execution of this node is open right now" and says so in its own
comment (``apps/studio/backend/app/services/run_report.py``: "an ``llm_call``
carries no execution id of its own, and the trace is ordered"). That premise
fails under a fan-out: in that run ``aggregate``, ``extrac`` and ``settings``
each had two executions open at the same time, and 4 of the 63 calls landed in
those windows, charged to whichever execution happened to have opened last.

This is the same wrong premise as OB10 one level down. There the run's total was
rebuilt from surviving state instead of counted at the call; here a call's owner
is rebuilt from position instead of stated by the producer. Both make a reader
reconstruct something the emitter already knew.

The scope already exists — ``wrap_edge_transition`` mints the destination
execution id and holds it for the whole phase body, which is how
``PhaseStartEvent`` gets it. So the fix is to stamp it in the one place every
event already passes through, exactly as ``subgraph_path`` is stamped, rather
than adding an argument to each emitter and hoping nobody forgets one.
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
name: events-name-their-execution
description: Two agent phases in a row, each making one model call.
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


class _AnsweringProvider:
    def __init__(self) -> None:
        self.call_count = 0

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        self.call_count += 1
        phase = str(request.metadata.get("phase_name") or "")
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


def _skill(tmp_path: Path) -> Path:
    skill = tmp_path / "execution-id-fixture"
    skill.mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    for name in ("prepare", "draft"):
        phase_dir = skill / "phases" / name
        phase_dir.mkdir(parents=True)
        (phase_dir / "SKILL.md").write_text(_phase_md(name), encoding="utf-8")
    return skill


def test_a_call_names_the_phase_execution_it_belongs_to(tmp_path: Path) -> None:
    provider = _AnsweringProvider()
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

    opened = {
        event.phase_name: event.phase_execution_id
        for event in log.events
        if getattr(event, "event_type", None) == "phase_start"
    }
    assert opened, "no phase opened; the fixture proved nothing"

    calls = [event for event in log.events if getattr(event, "event_type", None) == "llm_call"]
    assert calls, "no call was made; the fixture proved nothing"
    for call in calls:
        assert call.phase_execution_id == opened[call.phase_name], (
            f"{call.event_type} in {call.phase_name} says it belongs to "
            f"{call.phase_execution_id!r}, but that phase opened as "
            f"{opened[call.phase_name]!r}"
        )


def test_every_event_inside_a_phase_names_that_execution(tmp_path: Path) -> None:
    """Not just calls: anything a reader charges to an execution has to say so."""
    log = _EventLog()
    run_skill(
        _skill(tmp_path),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=_AnsweringProvider(),
        event_subscriber=log,
        topic="a topic",
    )

    opened = {
        event.phase_name: event.phase_execution_id
        for event in log.events
        if getattr(event, "event_type", None) == "phase_start"
    }
    unnamed = sorted(
        {
            event.event_type
            for event in log.events
            if getattr(event, "phase_name", None) in opened
            and getattr(event, "phase_execution_id", None) is None
        }
    )
    assert not unnamed, f"these event types happened inside a phase without naming it: {unnamed}"
