from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import AgentNodeAST


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _graph(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: v030-agent
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


def _agent(root: Path, body_extra: str = "") -> None:
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
phase_config:
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
    - finish_task
  references:
    - id: R1
      path: refs/r1.md
      summary: Primary reference.
---
<role>
Research assistant.
</role>
<goal>
Answer @reference:R1 using @example:E1 and @tool:finish_task.
</goal>
<step id="S1" name="Read">
Use the reference.
</step>
<protocol id="P1">
Always cite @step:S1.
</protocol>
<example id="E1">
Example content.
</example>
{body_extra}
""",
    )


class FakeAgentChatModel:
    def __init__(self) -> None:
        self.messages_seen: list[list[object]] = []
        self.bound_tool_names: list[str] = []

    def bind_tools(self, tools: list[object]) -> FakeAgentChatModel:
        self.bound_tool_names = [getattr(tool, "name", "") for tool in tools]
        return self

    def invoke(self, messages: list[object]) -> AIMessage:
        self.messages_seen.append(messages)
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {"markdown": "## answer\n\nok"},
                    "id": "finish-1",
                }
            ],
        )


def test_v030_agent_ast_parses_body_xml_and_inline_graph_io(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _agent(tmp_path)

    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
    ast = compiled.nodes[0].ast

    assert isinstance(ast, AgentNodeAST)
    assert compiled.manifest.schema_version == "v0.3.0"
    assert compiled.raw["io"]["inputs"]["properties"]["topic"]["type"] == "string"
    assert ast.role == "Research assistant."
    assert ast.goal.startswith("Answer @reference:R1")
    assert ast.steps[0].id == "S1"
    assert ast.protocols[0].id == "P1"
    assert "Role: Research assistant." in ast.system_prompt


def test_v030_agent_mention_target_must_be_reachable(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _agent(tmp_path, body_extra="<goal>Broken @reference:MISSING.</goal>")

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
    assert exc_info.value.payload.code == "[F-v3-mention-target-not-found]"


def test_v030_agent_broken_mention_syntax_fails(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _agent(tmp_path, body_extra="<goal>Broken @reference mention.</goal>")

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
    assert exc_info.value.payload.code == "[F-v3-mention-syntax-invalid]"


def test_v030_agent_runtime_uses_cognitive_template_and_resource_tools(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _graph(tmp_path)
    _agent(tmp_path)
    _write(tmp_path / "refs" / "r1.md", "Reference body.")
    chat = FakeAgentChatModel()

    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(compiled, chat_model=chat, skill_resolver=mock_skill_resolver).graph
    result = graph.invoke({"data": {"topic": "T"}, "flow": {}, "messages": [], "run_id": "r1"})

    system_prompt = chat.messages_seen[0][0].content
    assert "<knowledge_base>" in system_prompt
    assert "<output_schema>" in system_prompt
    assert "read_reference" in chat.bound_tool_names
    assert result["data"]["answer"] == "ok"
