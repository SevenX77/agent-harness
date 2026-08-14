"""A model turn may accept finish_task at most once.

DeepSeek habitually emits the SAME finish_task twice in one response
(parallel tool_calls). Both went through CognitiveFlow's accept branch, each
returning a Command that writes the ``flow`` channel — two writes in one
superstep on a LastValue channel → LangGraph ``InvalidUpdateError: At key
'flow': Can receive only one value per step`` (field evidence: run
2026-08-01T12-16-44, skill exp-a-round1). The rejection branch only writes
``messages`` (which has a reducer), which is why schema-failing duplicates
never crashed.
"""

from __future__ import annotations

import json
from pathlib import Path

from graph_agent.core.llm_provider import FakeLLMProvider, LLMProviderResponse
from graph_agent.core.runner import run_skill

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: dup-finish-fixture
description: Minimal agent skill for duplicate finish_task idempotency.
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
max_iterations: 4
validator: false
---
<role>你是摘要员。</role>

<goal>总结文本并调用 finish_task 提交 summary。</goal>

<step id="S1" name="finish">调用 finish_task 提交 summary。</step>
"""


def _fixture_skill(tmp_path: Path) -> Path:
    skill = tmp_path / "dup-finish-fixture"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    return skill


def _parallel_valid_finish_provider() -> FakeLLMProvider:
    payload = {
        "reasoning": "done",
        "business_data_md": "## item-1\n```json\n"
        + json.dumps({"summary": "两句话总结"}, ensure_ascii=False)
        + "\n```\n",
    }
    return FakeLLMProvider(
        response=LLMProviderResponse(
            content="",
            metadata={
                "tool_calls": [
                    {"name": "finish_task", "args": payload, "id": "tc-dup-a"},
                    {"name": "finish_task", "args": payload, "id": "tc-dup-b"},
                ]
            },
        )
    )


def test_parallel_valid_finish_calls_do_not_clash_on_flow(tmp_path: Path) -> None:
    result = run_skill(
        _fixture_skill(tmp_path),
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=_parallel_valid_finish_provider(),
        text="洪水冲垮了堤坝,救援连夜展开。",
    )

    assert result.status == "success", (
        f"run ended {result.status!r}; duplicate finish_task in one turn must "
        "be idempotent, not a flow-channel double write"
    )
