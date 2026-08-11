from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent_gateway.call import emit_route_decision_event
from langchain_core.messages import AIMessage

from graph_agent.core.runner import run_skill


class ToolCallingChatModel:
    def __init__(self) -> None:
        self.invocations = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> ToolCallingChatModel:
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


class GatewayFallbackChatModel:
    def __init__(self, callbacks: tuple[Any, ...]) -> None:
        self.event_callbacks = tuple(callbacks)

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> GatewayFallbackChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        emit_route_decision_event(
            callbacks=self.event_callbacks,
            phase_name="agent",
            decision="fell_back",
            next_route_id="fallback:route",
            reason="RuntimeError: probe failed",
        )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {
                        "reasoning": "done",
                        "diagnostics_md": "schema aligned",
                        "business_data_md": "## main\n- answer: fallback-ready\n",
                    },
                    "id": "finish-1",
                }
            ],
        )


class GatewayShapeResolver:
    def resolve(
        self,
        role_name: str,
        *,
        callbacks: tuple[Any, ...] = (),
        phase_name: str | None = None,
    ) -> GatewayFallbackChatModel:
        del role_name, phase_name
        return GatewayFallbackChatModel(callbacks)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_mixed_phase_skill(parent: Path, child: Path) -> None:
    _write(
        parent / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: event-subscriber-cutover
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
  - prepare
  - delegate
  - agent
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare">delegate</phase>
<phase depends_on="delegate" output>agent</phase>
""",
    )
    _write(
        parent / "phases" / "prepare" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      prep_note:
        type: string
---
<action>prepare</action>
""",
    )
    _write(
        parent / "phases" / "prepare" / "actions" / "prepare.py",
        "def prepare(inputs):\n"
        "    return {'prep_note': 'prepared:' + inputs.get('topic', '')}\n",
    )
    _write(
        parent / "phases" / "delegate" / "SUBGRAPH.md",
        f"""---
path: {child}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties:
      child_answer:
        type: string
---
""",
    )
    _write(
        parent / "phases" / "agent" / "SKILL.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
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
        parent / "phases" / "agent" / "tools" / "inspect_payload.py",
        "def inspect_payload(topic: str) -> dict:\n"
        "    return {'topic': topic, 'items': ['alpha', 'beta']}\n",
    )
    _write(
        child / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: child
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties:
      child_answer:
        type: string
phases:
  - inspect
---
<phase depends_on="input" output>inspect</phase>
""",
    )
    _write(
        child / "phases" / "inspect" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties:
      child_answer:
        type: string
---
<action>inspect</action>
""",
    )
    _write(
        child / "phases" / "inspect" / "actions" / "inspect.py",
        "def inspect(inputs):\n"
        "    return {'child_answer': 'child-ok'}\n",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    assert path.is_file(), f"trace.jsonl not found: {path}"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _event_type(event: object) -> str:
    return str(getattr(event, "event_type", ""))


def test_run_skill_event_subscriber_receives_run_phase_llm_and_tool_events(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    parent = tmp_path / "parent"
    child = parent / "subgraphs" / "child"
    workspace_dir = tmp_path / "workspace"
    _write_mixed_phase_skill(parent, child)
    subscriber_events: list[object] = []

    result = run_skill(
        parent,
        mock_llm=ToolCallingChatModel(),
        workspace_dir=workspace_dir,
        thread_id="subscriber-cutover",
        event_subscriber=subscriber_events.append,
        skill_resolver=mock_skill_resolver,
        topic="observability",
    )

    assert result.success is True
    event_types = [_event_type(event) for event in subscriber_events]
    assert event_types[0] == "run_started"
    assert event_types[-1] == "run_ended"
    assert {"phase_start", "phase_end", "llm_call", "tool_call"} <= set(event_types)

    trace_events = _read_jsonl(workspace_dir / "runs" / result.run_id / "trace.jsonl")
    assert [_event_type(event) for event in subscriber_events] == [
        event["event_type"] for event in trace_events
    ]


def test_trace_phase_lifecycle_is_single_source_for_logic_agent_and_subgraph(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    parent = tmp_path / "parent"
    child = parent / "subgraphs" / "child"
    workspace_dir = tmp_path / "workspace"
    _write_mixed_phase_skill(parent, child)

    subscriber_events: list[object] = []
    result = run_skill(
        parent,
        mock_llm=ToolCallingChatModel(),
        workspace_dir=workspace_dir,
        thread_id="single-source-lifecycle",
        event_subscriber=subscriber_events.append,
        skill_resolver=mock_skill_resolver,
        topic="observability",
    )

    events = _read_jsonl(workspace_dir / "runs" / result.run_id / "trace.jsonl")
    phase_lifecycle = [
        (event["event_type"], event.get("phase_name"))
        for event in events
        if event["event_type"] in {"phase_start", "phase_end"}
    ]
    assert phase_lifecycle == [
        ("phase_start", "prepare"),
        ("phase_end", "prepare"),
        ("phase_start", "delegate"),
        ("phase_start", "inspect"),
        ("phase_end", "inspect"),
        ("phase_end", "delegate"),
        ("phase_start", "agent"),
        ("phase_end", "agent"),
    ]
    for phase_name in {"prepare", "delegate", "inspect", "agent"}:
        assert phase_lifecycle.count(("phase_start", phase_name)) == 1
        assert phase_lifecycle.count(("phase_end", phase_name)) == 1


def test_model_resolver_gateway_fallback_event_reaches_subscriber_and_trace(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    parent = tmp_path / "parent"
    child = parent / "subgraphs" / "child"
    workspace_dir = tmp_path / "workspace"
    _write_mixed_phase_skill(parent, child)
    subscriber_events: list[object] = []

    result = run_skill(
        parent,
        workspace_dir=workspace_dir,
        thread_id="gateway-fallback-subscriber",
        event_subscriber=subscriber_events.append,
        model_resolver=GatewayShapeResolver(),
        skill_resolver=mock_skill_resolver,
        topic="observability",
    )

    assert result.success is True
    assert any(_event_type(event) == "llm_route_decision" for event in subscriber_events)

    trace_events = _read_jsonl(workspace_dir / "runs" / result.run_id / "trace.jsonl")
    assert any(event["event_type"] == "llm_route_decision" for event in trace_events)
