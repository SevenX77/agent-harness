from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from graph_agent.callbacks.events import (
    LLMCallEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    ToolCallEvent,
)
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.runner import _run_v030_skill_dict, run_skill


class SpyCallback:
    def __init__(self) -> None:
        self.events: list[object] = []

    def on_event(self, event: object) -> None:
        self.events.append(event)


class V030ToolCallingChatModel:
    def __init__(self) -> None:
        self.bound_tool_names: list[str] = []
        self.invocations: int = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> V030ToolCallingChatModel:
        del kwargs
        self.bound_tool_names = [str(getattr(tool, "name", "")) for tool in tools]
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


class V030NoToolChatModel:
    def __init__(self) -> None:
        self.invocations: int = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> V030NoToolChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        self.invocations += 1
        return AIMessage(content="no tool calls")


class V030UnknownToolChatModel:
    def bind_tools(self, tools: list[Any], **kwargs: Any) -> V030UnknownToolChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "missing_tool",
                    "args": {},
                    "id": "missing-1",
                }
            ],
        )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_v030_observable_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: pr2-observability-red
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
      request_id:
        type: string
    required: [topic, request_id]
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
phase_config:
  io:
    inputs:
      type: object
      properties:
        topic:
          type: string
        request_id:
          type: string
      required: [topic, request_id]
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
        '''def inspect_payload(topic: str) -> dict:
    """Return a nested payload so ToolCallEvent must serialize dict/list output."""
    return {"topic": topic, "items": ["alpha", "beta"], "nested": {"ok": True}}
''',
    )


def _event_types(events: list[object]) -> set[type[object]]:
    return {type(event) for event in events}


def test_v030_run_skill_emits_phase_llm_tool_events_from_graph_root(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "observable_skill"
    output_dir = tmp_path / "out"
    _write_v030_observable_skill(skill_root)
    spy = SpyCallback()

    result = run_skill(
        skill_root,
        mock_llm=V030ToolCallingChatModel(),
        callbacks=[spy],
        workspace_dir=output_dir,
        skill_resolver=mock_skill_resolver,
        topic="observability",
        request_id="req-123",
        output_dir=str(output_dir),
    )

    assert result.success is True
    seen = _event_types(spy.events)
    assert PhaseStartEvent in seen
    assert LLMCallEvent in seen
    assert ToolCallEvent in seen
    assert PhaseEndEvent in seen

    phase_start = next(event for event in spy.events if isinstance(event, PhaseStartEvent))
    phase_end = next(event for event in spy.events if isinstance(event, PhaseEndEvent))
    assert phase_start.context == {
        "inputs": {"topic": "observability", "request_id": "req-123"},
        "phase_outputs": {},
        "scratch": {},
    }
    assert phase_end.context["phase_outputs"]["main"] == {"answer": "trace-ready"}

    llm_events = [event for event in spy.events if isinstance(event, LLMCallEvent)]
    assert llm_events
    assert all(event.input_tokens == 0 and event.output_tokens == 0 for event in llm_events)

    tool_events = [event for event in spy.events if isinstance(event, ToolCallEvent)]
    assert {event.tool_name for event in tool_events} >= {"inspect_payload", "finish_task"}
    inspect_event = next(event for event in tool_events if event.tool_name == "inspect_payload")
    assert json.loads(inspect_event.result)["items"] == ["alpha", "beta"]


def test_v030_run_skill_fails_when_agent_returns_without_finish_task(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "observable_skill"
    _write_v030_observable_skill(skill_root)
    spy = SpyCallback()

    result = run_skill(
        skill_root,
        mock_llm=V030NoToolChatModel(),
        callbacks=[spy],
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
        topic="observability",
        request_id="req-no-finish",
    )

    assert result.success is False
    assert result.diagnostic_counts["by_code"] == {"[F-v3-agent-exit-control-failed]": 1}
    phase_end = next(event for event in spy.events if isinstance(event, PhaseEndEvent))
    assert phase_end.context == {
        "inputs": {"topic": "observability", "request_id": "req-no-finish"},
        "phase_outputs": {},
        "scratch": {},
    }


def test_v030_run_skill_emits_phase_end_when_agent_raises(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "observable_skill"
    _write_v030_observable_skill(skill_root)
    spy = SpyCallback()

    with pytest.raises(GraphAgentFatalError):
        _run_v030_skill_dict(
            skill_root,
            mock_llm=V030UnknownToolChatModel(),
            callbacks=[spy],
            workspace_dir=tmp_path / "workspace",
            skill_resolver=mock_skill_resolver,
            topic="observability",
            request_id="req-error",
        )

    phase_end = next(event for event in spy.events if isinstance(event, PhaseEndEvent))
    assert phase_end.context == {
        "inputs": {"topic": "observability", "request_id": "req-error"},
        "phase_outputs": {},
        "scratch": {},
    }


def test_v030_run_skill_returns_real_trace_path_and_writes_typed_stream(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "observable_skill"
    trace_dir = tmp_path / "trace-output"
    _write_v030_observable_skill(skill_root)
    events: list[object] = []

    result = run_skill(
        skill_root,
        mock_llm=V030ToolCallingChatModel(),
        event_subscriber=events.append,
        workspace_dir=trace_dir,
        skill_resolver=mock_skill_resolver,
        topic="observability",
        request_id="req-456",
    )

    assert result.success is True
    assert result.trace_path is not None
    trace_path = Path(result.trace_path)
    assert trace_path.is_file()
    assert trace_path.name == "trace.jsonl"

    typed_stream = trace_path
    assert typed_stream.is_file()
    event_types = {
        json.loads(line)["event_type"]
        for line in typed_stream.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert {"phase_start", "llm_call", "tool_call", "phase_end"} <= event_types
    assert {"phase_start", "llm_call", "tool_call", "phase_end"} <= {
        getattr(event, "event_type", "") for event in events
    }
