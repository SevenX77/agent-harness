"""EVERY tool call is announced when it starts, and reported exactly once.

`ToolCallStartedEvent` fired only for skill-declared tools. The framework tools
— `finish_task`, `update_working_memory`, `ask_clarification`, the whole
cognitive set — were never announced, and those are most of what an agent phase
actually calls. Measured 2026-08-20 against a real `run_skill`: a phase calling
`update_working_memory` and then `finish_task` produced two `tool_call` events,
zero `tool_call_started`, and a spy on `TracingMiddleware.wrap_tool_call` /
`awrap_tool_call` counted zero dispatches of either.

The cause is ordering, not a missing emitter. `CognitiveFlowMiddleware` sat
AHEAD of `TracingMiddleware` and answers the tools it intercepts without calling
`handler(request)`, so the rest of the wrapper chain — the observer included —
was skipped for exactly those calls. An observer a decider can skip is not
observing the system; it is observing whatever subset another component's
control flow leaves for it. So tracing belongs OUTSIDE the deciders.

This replaces `e2e/test_tool_call_started_e2e.py`'s
`test_finish_task_is_not_announced_because_cognitive_flow_intercepts_it`, which
pinned the gap while stating what closing it would need: "a decision about who
owns tracing on the agent path". That decision is the ordering above.

The second test is the other half of the move. Once the observer runs it closes
the calls that answered with a `ToolMessage`, while the agent node's post-hoc
scan of the message list exists to catch the ones that answered with a `Command`
and never closed. With both live, every ToolMessage-answered call would be
reported twice — so "report this call" has to mean "unless it has already been
reported", and that memory belongs to the one reporter the phase has.
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
name: tool-announcement
description: One agent phase that uses a tool before finishing.
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

_SKILL_MD = """---
llm_role: analyst
validator: false
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
max_iterations: 3
---
<role>Echo.</role>

<goal>Summarize {topic}.</goal>

<step id="S1" name="note">Record a note first.</step>
<step id="S2" name="finish">Then call finish_task.</step>
"""


class _NoteThenFinish:
    """Calls a framework tool, then submits — the ordinary shape of an agent turn."""

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        del request
        self.calls += 1
        if self.calls == 1:
            yield LLMProviderChunk(
                content="",
                metadata={
                    "tool_calls": [
                        {
                            "name": "update_working_memory",
                            "args": {"content": "noting it"},
                            "id": "wm-1",
                        }
                    ]
                },
            )
            return
        yield LLMProviderChunk(
            content="",
            metadata={
                "tool_calls": [
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "done",
                            "business_data_md": "## item-1\n```json\n"
                            + json.dumps({"summary": "ok"}, ensure_ascii=False)
                            + "\n```\n",
                        },
                        "id": "finish-1",
                    }
                ]
            },
        )


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None, str | None]] = []

    def __call__(self, event: Any) -> None:
        self.events.append(
            (
                event.event_type,
                getattr(event, "tool_name", None),
                getattr(event, "tool_call_id", None),
            )
        )

    def of_type(self, event_type: str) -> list[tuple[str, str | None, str | None]]:
        return [row for row in self.events if row[0] == event_type]

    def index_of(self, event_type: str, call_id: str) -> int:
        for position, row in enumerate(self.events):
            if row[0] == event_type and row[2] == call_id:
                return position
        raise AssertionError(f"no {event_type} for {call_id}; saw {self.events}")


def _run(tmp_path: Path) -> _Recorder:
    skill = tmp_path / "tool-announcement"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    recorder = _Recorder()
    result = run_skill(
        skill,
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=_NoteThenFinish(),
        event_subscriber=recorder,
        topic="venus",
    )
    assert result.success, getattr(result, "error", None)
    return recorder


def test_every_tool_call_is_announced_before_it_is_reported(tmp_path: Path) -> None:
    recorder = _run(tmp_path)

    started = {row[2] for row in recorder.of_type("tool_call_started")}
    ended = {row[2] for row in recorder.of_type("tool_call")}
    assert ended, f"the fixture called no tools at all; saw {recorder.events}"
    assert started == ended, (
        f"tool calls reported but never announced: {ended - started}; "
        f"announced but never reported: {started - ended}"
    )
    for call_id in ended:
        assert recorder.index_of("tool_call_started", call_id) < recorder.index_of(
            "tool_call", call_id
        ), f"{call_id} was reported before it was announced"


def test_a_tool_call_is_reported_exactly_once(tmp_path: Path) -> None:
    recorder = _run(tmp_path)

    reported = [row[2] for row in recorder.of_type("tool_call")]
    assert len(reported) == len(set(reported)), (
        f"the same call was reported more than once: {reported}"
    )
