"""Every model request must answer every prior tool_call_id in its history.

OpenAI-protocol providers hard-reject a history where an assistant message
carrying tool_calls is not followed by tool messages responding to each id
(field evidence: run 2026-08-01T09-10-21, DeepSeek 400 "insufficient tool
messages following tool_calls message"). The engine's reject→nudge loop builds
exactly that shape: after CognitiveFlow rejects a finish_task submission,
ExitControl nudges the graph back to the model with the trailing AI(tool_calls)
left unanswered in the outgoing request.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from graph_agent.core.llm_provider import FakeLLMProvider, LLMProviderChunk
from graph_agent.core.runner import run_skill

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: tool-history-fixture
description: Minimal agent skill for tool-history integrity contract.
llm_role: analyst
io:
  inputs:
    type: object
    required: [text]
    properties:
      text:
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
io:
  inputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
  outputs:
    type: object
    required: [summary]
    properties:
      summary:
        type: string
tools: [finish_task]
max_iterations: 8
validator: false
---
<role>你是摘要员。</role>

<goal>总结文本并调用 finish_task 提交 summary。</goal>

<step id="S1" name="finish">调用 finish_task 提交 summary。</step>
"""


def _fixture_skill(tmp_path: Path) -> Path:
    skill = tmp_path / "tool-history-fixture"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    return skill


class _RejectedFinishProvider(FakeLLMProvider):
    """finish_task payload that fails the io.outputs schema gate every time,
    driving the reject → nudge → re-invoke loop.

    Real providers mint a FRESH tool_call id per response; reusing a constant
    id lets a later AI message alias an earlier ToolMessage and masks the
    orphan (that aliasing hid this bug from the first repro attempt)."""

    def __init__(self) -> None:
        super().__init__()
        self._counter = 0

    def stream(self, request):  # type: ignore[override]
        self.requests.append(request)
        bad = {"wrong_field": "no summary here"}
        payload = {
            "reasoning": "done",
            "business_data_md": "## item-1\n```json\n"
            + json.dumps(bad, ensure_ascii=False)
            + "\n```\n",
        }
        self._counter += 1
        yield LLMProviderChunk(
            content="",
            metadata={
                "tool_calls": [
                    {
                        "name": "finish_task",
                        "args": payload,
                        "id": f"tc-{self._counter}-a",
                    },
                    {
                        "name": "finish_task",
                        "args": payload,
                        "id": f"tc-{self._counter}-b",
                    },
                ]
            },
        )


def _unanswered_tool_call_ids(messages: list) -> list[str]:
    """Order-aware: a tool_call is answered only by a ToolMessage that comes
    AFTER its assistant message (the OpenAI-protocol contract)."""
    orphans: list[str] = []
    for pos, m in enumerate(messages):
        if isinstance(m, AIMessage):
            answered_after = {
                later.tool_call_id
                for later in messages[pos + 1 :]
                if isinstance(later, ToolMessage)
            }
            for tc in m.tool_calls or []:
                if tc.get("id") and tc["id"] not in answered_after:
                    orphans.append(tc["id"])
    return orphans


def test_every_model_request_answers_all_tool_calls(tmp_path: Path) -> None:
    provider = _RejectedFinishProvider()

    try:
        run_skill(
            _fixture_skill(tmp_path),
            workspace_dir=tmp_path / "ws",
            unattended=True,
            llm_provider=provider,
            text="MARKER 文本",
        )
    except Exception:
        pass  # iteration-limit exit is fine; request shapes are the contract

    assert len(provider.requests) >= 2, "reject loop never re-invoked the model"
    for index, request in enumerate(provider.requests, start=1):
        orphans = _unanswered_tool_call_ids(list(request.messages))
        assert not orphans, (
            f"request {index} carries assistant tool_calls with no ToolMessage "
            f"response (orphaned ids: {orphans}); strict providers reject this "
            "history with HTTP 400"
        )
