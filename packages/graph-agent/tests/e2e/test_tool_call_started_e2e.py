"""End to end: a real run announces each tool call before the tool body runs.

The middleware unit tests pin the contract in isolation; this one proves the
event actually reaches a run's callbacks ahead of the tool's own side effects,
and that the identity minted at the start survives to whichever emitter reports
the completion — including ``finish_task``, whose completion is reconstructed by
the agent node rather than by the tracing middleware.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from graph_agent.callbacks.events import ToolCallEvent, ToolCallStartedEvent
from graph_agent.core.runner import run_skill


class TimelineCallback:
    """Append every event to the same log the skill's tool writes to."""

    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)
        if isinstance(event, ToolCallStartedEvent | ToolCallEvent):
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{type(event).__name__}:{event.tool_name}\n")


class _ToolCallingChatModel:
    def __init__(self) -> None:
        self.invocations = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> _ToolCallingChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        self.invocations += 1
        if self.invocations == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "inspect_payload",
                        "args": {"topic": "observability"},
                        "id": "inspect-1",
                    }
                ],
            )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {
                        "reasoning": "done",
                        "diagnostics_md": "schema aligned",
                        "business_data_md": "## main\n- answer: trace-ready\n",
                    },
                    "id": "finish-1",
                }
            ],
        )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_skill(root: Path, log_path: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: tool-call-started-e2e
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
    required: [topic]
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
    )
    _write(
        root / "phases" / "main" / "SKILL.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
    required: [topic]
  outputs:
    type: object
    properties:
      answer:
        type: string
tools:
  - inspect_payload
  - finish_task
---
<role>
Trace exerciser.
</role>
<goal>
Call @tool:inspect_payload, then finish with @tool:finish_task.
</goal>
<step id="S1" name="Inspect">
Inspect the payload.
</step>
<protocol id="P1">
Return the answer through finish_task.
</protocol>
""",
    )
    _write(
        root / "phases" / "main" / "tools" / "inspect_payload.py",
        f'''from pathlib import Path


def inspect_payload(topic: str) -> dict:
    """Record that the tool body ran, so the event order is assertable."""
    log = Path({json.dumps(str(log_path))})
    with log.open("a", encoding="utf-8") as handle:
        handle.write("tool-body:inspect_payload\\n")
    return {{"topic": topic}}
''',
    )


def test_run_announces_tool_calls_before_they_execute(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    log_path = tmp_path / "timeline.log"
    skill_root = tmp_path / "started_skill"
    output_dir = tmp_path / "out"
    _write_skill(skill_root, log_path)
    callback = TimelineCallback(log_path)

    result = run_skill(
        skill_root,
        mock_llm=_ToolCallingChatModel(),
        callbacks=[callback],
        workspace_dir=output_dir,
        skill_resolver=mock_skill_resolver,
        topic="observability",
        output_dir=str(output_dir),
    )
    assert result.success is True

    timeline = log_path.read_text(encoding="utf-8").splitlines()
    started_at = timeline.index("ToolCallStartedEvent:inspect_payload")
    body_at = timeline.index("tool-body:inspect_payload")
    assert started_at < body_at, f"started event must precede the tool body: {timeline}"

    started = [e for e in callback.events if isinstance(e, ToolCallStartedEvent)]
    assert {e.tool_name: e.tool_call_id for e in started} == {
        "inspect_payload": "inspect-1",
        "finish_task": "finish-1",
    }

    # finish_task never reaches the tracing middleware's completion path (it
    # returns a Command), so its pair is closed by the agent node — which must
    # report the same provider id.
    finished_ids = {e.tool_name: e.tool_call_id for e in callback.events if isinstance(e, ToolCallEvent)}
    assert finished_ids["finish_task"] == "finish-1"
    assert finished_ids["inspect_payload"] == "inspect-1"
