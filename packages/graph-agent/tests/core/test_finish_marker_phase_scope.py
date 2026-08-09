"""A finish marker belongs to the phase that produced it.

``FrameworkState.finish_task_result`` survives phase boundaries, so the second
agent phase's exit gate saw the FIRST phase's passing marker and jumped
straight to "success" — the phase produced nothing and the run then died on
its own missing outputs (field evidence: runs 2026-08-01T12-52-39 /
16-58-05 / 17-09-30, review phase with exactly one llm_call and zero
tool_calls; offline repro logged "Qualified finish_task marker observed.
Exiting success." before review's first turn was even judged).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from graph_agent.core.llm_provider import FakeLLMProvider, LLMProviderChunk
from graph_agent.core.runner import run_skill

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: two-agent-fixture
description: Two chained agent phases for finish-marker scoping.
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
    required: [reviewed]
    properties:
      reviewed:
        type: string
phases: [draft, review]
---
<phase depends_on="input">draft</phase>
<phase depends_on="draft" output>review</phase>
"""

_DRAFT_MD = """---
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
max_iterations: 3
validator: false
---
<role>摘要员</role>

<goal>总结文本</goal>

<step id="S1" name="finish">调用 finish_task 提交 summary</step>
"""

_REVIEW_MD = """---
llm_role: analyst
io:
  inputs:
    type: object
    required: [summary]
    properties:
      summary:
        type: string
  outputs:
    type: object
    required: [reviewed]
    properties:
      reviewed:
        type: string
tools: [finish_task]
max_iterations: 3
validator: false
---
<role>复核员</role>

<goal>复核摘要</goal>

<step id="S1" name="finish">调用 finish_task 提交 reviewed</step>
"""


def _fixture_skill(tmp_path: Path) -> Path:
    skill = tmp_path / "two-agent-fixture"
    for phase, body in (("draft", _DRAFT_MD), ("review", _REVIEW_MD)):
        (skill / "phases" / phase).mkdir(parents=True)
        (skill / "phases" / phase / "SKILL.md").write_text(body, encoding="utf-8")
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    return skill


class _DraftFinishesReviewStallsProvider(FakeLLMProvider):
    """draft submits a valid finish_task; review replies with prose only."""

    def stream(self, request):  # type: ignore[override]
        self.requests.append(request)
        phase = (request.metadata or {}).get("phase_name")
        if phase == "draft":
            payload = {
                "reasoning": "done",
                "business_data_md": "## item-1\n```json\n"
                + json.dumps({"summary": "一句话摘要"}, ensure_ascii=False)
                + "\n```\n",
            }
            yield LLMProviderChunk(
                content="",
                metadata={
                    "tool_calls": [
                        {"name": "finish_task", "args": payload, "id": "draft-1"}
                    ]
                },
            )
            return
        yield LLMProviderChunk(content="复核完成,无需修改。", metadata={})


def test_next_phase_is_not_finished_by_the_previous_phase_marker(
    tmp_path: Path,
) -> None:
    provider = _DraftFinishesReviewStallsProvider()

    try:
        run_skill(
            _fixture_skill(tmp_path),
            workspace_dir=tmp_path / "ws",
            unattended=True,
            llm_provider=provider,
            text="洪水冲垮了堤坝。",
        )
    except Exception:
        pass  # review never submits, so the run legitimately fails

    calls = Counter((req.metadata or {}).get("phase_name") for req in provider.requests)
    assert calls["draft"] == 1
    assert calls["review"] > 1, (
        "review returned prose with no finish_task, so the exit gate must nudge "
        f"it back to the model; it instead exited on the draft phase's marker "
        f"(calls: {dict(calls)})"
    )
