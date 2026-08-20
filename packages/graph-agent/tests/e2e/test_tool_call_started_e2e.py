"""End to end: a real run announces a tool call before it reports one.

The middleware unit tests pin the ordering against the tool body in isolation
(skill tools must be pure, so a real one cannot record that it ran). What this
proves is that the started event reaches a run's callbacks at all, and that the
identity it announces survives to whichever emitter reports the completion.

It also pins the one tool that is NOT announced — see the second test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from graph_agent.callbacks.events import ToolCallEvent, ToolCallStartedEvent
from graph_agent.core.runner import run_skill


class SpyCallback:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


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


def _write_skill(root: Path) -> None:
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
    """Return the topic so the completion half carries a result."""
    return {"topic": topic}
''',
    )


def _run(tmp_path: Path, resolver: object) -> SpyCallback:
    skill_root = tmp_path / "started_skill"
    output_dir = tmp_path / "out"
    _write_skill(skill_root)
    spy = SpyCallback()

    result = run_skill(
        skill_root,
        mock_llm=_ToolCallingChatModel(),
        callbacks=[spy],
        workspace_dir=output_dir,
        skill_resolver=resolver,
        topic="observability",
        output_dir=str(output_dir),
    )
    assert result.success is True
    return spy


def test_run_announces_a_tool_call_with_the_provider_identity(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    spy = _run(tmp_path, mock_skill_resolver)

    started = [e for e in spy.events if isinstance(e, ToolCallStartedEvent)]
    assert [e.tool_name for e in started] == ["inspect_payload", "finish_task"]
    assert started[0].tool_call_id == "inspect-1"
    assert started[0].phase_name == "main"
    assert started[0].args == {"topic": "observability"}

    # Every emitter reads the same provider id, so the halves pair even when a
    # different one reports the completion.
    finished = [e for e in spy.events if isinstance(e, ToolCallEvent)]
    assert {e.tool_call_id for e in finished if e.tool_name == "inspect_payload"} == {"inspect-1"}
    assert {e.tool_call_id for e in finished if e.tool_name == "finish_task"} == {"finish-1"}

    announced_at = spy.events.index(started[0])
    reported_at = [
        index
        for index, event in enumerate(spy.events)
        if isinstance(event, ToolCallEvent) and event.tool_call_id == "inspect-1"
    ]
    assert reported_at and min(reported_at) > announced_at


def test_an_intercepted_tool_is_announced_like_any_other(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    """The gap this used to pin is closed, and the closing is what it asked for.

    Until 2026-08-20 this test asserted the opposite — that `finish_task` is
    never announced — and said why it stood: `MVP0_MIDDLEWARE_ORDER_CONTRACT`
    put CognitiveFlow ahead of Tracing, `CognitiveFlowMiddleware.wrap_tool_call`
    answers `finish_task` itself instead of calling the inner handler, so
    Tracing never saw the call. Its own note named the missing piece: "a
    decision about who owns tracing on the agent path".

    The decision: the observer sits outside the deciders. Tracing is now the
    first slot in the contract, so a middleware answering a call on its own
    still cannot answer it unobserved.
    """
    spy = _run(tmp_path, mock_skill_resolver)

    started = {e.tool_name for e in spy.events if isinstance(e, ToolCallStartedEvent)}
    reported = {e.tool_name for e in spy.events if isinstance(e, ToolCallEvent)}
    assert "finish_task" in reported
    assert "finish_task" in started
