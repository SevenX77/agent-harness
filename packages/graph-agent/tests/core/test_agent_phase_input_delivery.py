"""An AGENT phase's declared inputs must reach the model at run time.

Field evidence (run 2026-08-01T07-50-22, skill exp-a-round1): the LLM request
contained exactly ONE static SystemMessage — no Human message, no input data,
and `{var}` placeholders in <goal> arrived as literals. The model (DeepSeek)
replied "输入缺失…仅含未替换的模板占位符". The v0.3.0 assembler bakes the
cognitive-template system prompt at assembly time and `_skill_node` forwards
the outer (empty) message list verbatim, so no mechanism ever delivers the
phase's io.inputs to the model.
"""

from __future__ import annotations

import json
from pathlib import Path

from graph_agent.core.llm_provider import FakeLLMProvider, LLMProviderResponse
from graph_agent.core.runner import run_skill

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: input-delivery-fixture
description: Minimal agent skill for input delivery contract.
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
max_iterations: 3
validator: false
---
<role>你是摘要员。</role>

<goal>
总结以下文本：
```
{text}
```
</goal>

<step id="S1" name="finish">调用 finish_task 提交 summary。</step>
"""

_FINISH_PAYLOAD = {
    "reasoning": "done",
    "business_data_md": "## item-1\n```json\n{\"summary\": \"ok\"}\n```\n",
}


def _fixture_skill(tmp_path: Path) -> Path:
    skill = tmp_path / "input-delivery-fixture"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    return skill


def _finishing_provider() -> FakeLLMProvider:
    return FakeLLMProvider(
        response=LLMProviderResponse(
            content="",
            metadata={
                "tool_calls": [
                    {"name": "finish_task", "args": _FINISH_PAYLOAD, "id": "tc-1"}
                ]
            },
        )
    )


def test_agent_phase_receives_declared_inputs(tmp_path: Path) -> None:
    provider = _finishing_provider()
    marker = "第1行 洪水冲垮了堤坝 MARKER-8471"

    try:
        run_skill(
            _fixture_skill(tmp_path),
            workspace_dir=tmp_path / "ws",
            unattended=True,
            llm_provider=provider,
            text=marker,
        )
    except Exception:
        pass  # output handling is not this contract; the request content is

    assert provider.requests, "model was never invoked"
    first = provider.requests[0]
    rendered = "\n".join(str(getattr(m, "content", m)) for m in first.messages)
    assert marker in rendered, (
        "phase input never reached the model; request was:\n" + rendered[:800]
    )
    assert "{text}" not in rendered, "goal placeholder arrived unrendered"


def test_input_payload_is_not_duplicated_per_iteration(tmp_path: Path) -> None:
    provider = _finishing_provider()
    marker = "MARKER-ONCE-5150"

    try:
        run_skill(
            _fixture_skill(tmp_path),
            workspace_dir=tmp_path / "ws",
            unattended=True,
            llm_provider=provider,
            text=marker,
        )
    except Exception:
        pass

    assert provider.requests
    rendered = "\n".join(
        str(getattr(m, "content", m)) for m in provider.requests[0].messages
    )
    assert rendered.count(marker) <= 2, (
        "input payload injected more than once into a single request:\n"
        + json.dumps(rendered.count(marker))
    )
