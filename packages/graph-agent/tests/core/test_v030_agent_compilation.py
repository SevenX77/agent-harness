from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import AgentNodeAST
from langchain_core.messages import AIMessage


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _graph(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "0.3.0"
name: v030-agent
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - id: main
    src: phases/main
    depends_on: []
---
""",
    )


def _agent(root: Path, body_extra: str = "") -> None:
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
mode: agent
name: main
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
  examples:
    - id: E1
      type: inline
      content: Example content.
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
{body_extra}
<exit_contract>
Return answer.
</exit_contract>
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


def test_v030_agent_ast_parses_body_xml_and_inline_graph_io(tmp_path: Path) -> None:
    _graph(tmp_path)
    _agent(tmp_path)

    compiled = SkillLoader().compile_skill(tmp_path)
    ast = compiled.nodes[0].ast

    assert isinstance(ast, AgentNodeAST)
    assert compiled.manifest.schema_version == "0.3.0"
    assert compiled.raw["io"]["inputs"]["properties"]["topic"]["type"] == "string"
    assert ast.role == "Research assistant."
    assert ast.goal.startswith("Answer @reference:R1")
    assert ast.steps[0].id == "S1"
    assert ast.protocols[0].id == "P1"
    assert "Role: Research assistant." in ast.system_prompt


def test_v030_agent_mention_target_must_be_reachable(tmp_path: Path) -> None:
    _graph(tmp_path)
    _agent(tmp_path, body_extra='<step id="S2" name="Broken">Broken @reference:MISSING.</step>')

    with pytest.raises(SkillLoadError, match=r"\[F-v3-mention-target-not-found\]"):
        SkillLoader().compile_skill(tmp_path)


def test_v030_agent_broken_mention_syntax_fails(tmp_path: Path) -> None:
    _graph(tmp_path)
    _agent(tmp_path, body_extra='<step id="S2" name="Broken">Broken @reference mention.</step>')

    with pytest.raises(SkillLoadError, match=r"\[F-v3-mention-syntax-invalid\]"):
        SkillLoader().compile_skill(tmp_path)


def test_v030_agent_unknown_mention_kind_fails(tmp_path: Path) -> None:
    _graph(tmp_path)
    _agent(tmp_path, body_extra='<step id="S2" name="Broken">Broken @persona:Lead.</step>')

    with pytest.raises(SkillLoadError, match=r"\[F-v3-mention-syntax-invalid\]"):
        SkillLoader().compile_skill(tmp_path)


def test_v030_skill_md_requires_agent_mode(tmp_path: Path) -> None:
    _graph(tmp_path)
    _agent(tmp_path)
    skill = tmp_path / "phases" / "main" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8").replace("mode: agent", "mode: skill"))

    with pytest.raises(SkillLoadError, match=r"mode 'skill' does not match SKILL.md"):
        SkillLoader().compile_skill(tmp_path)


def test_v030_graph_body_phase_xml_is_rejected(tmp_path: Path) -> None:
    _graph(tmp_path)
    _agent(tmp_path)
    graph = tmp_path / "GRAPH.md"
    graph.write_text(graph.read_text(encoding="utf-8") + '<phase id="x" src="phases/x" />\n')

    with pytest.raises(SkillLoadError, match="phases must be declared in frontmatter"):
        SkillLoader().compile_skill(tmp_path)


def test_v030_physical_root_io_is_rejected(tmp_path: Path) -> None:
    _graph(tmp_path)
    _agent(tmp_path)
    _write(tmp_path / "io" / "inputs.json", "{}")

    with pytest.raises(SkillLoadError, match=r"\[F-v3-graph-io-physical-file-deprecated\]"):
        SkillLoader().compile_skill(tmp_path)


def test_v030_agent_body_rejects_workflow_shell(tmp_path: Path) -> None:
    _graph(tmp_path)
    _agent(tmp_path, body_extra='<workflow><step id="S2" name="Bad">No shell.</step></workflow>')

    with pytest.raises(SkillLoadError, match=r"\[F-v3-agent-body-tag-invalid\]"):
        SkillLoader().compile_skill(tmp_path)


def test_v030_subgraph_target_skill_requires_matching_io(
    tmp_path: Path,
    in_memory_skill_resolver_factory: Any,
) -> None:
    child = tmp_path / "child"
    _graph(child)
    _agent(child)

    parent = tmp_path / "parent"
    _write(
        parent / "GRAPH.md",
        """---
schema_version: "0.3.0"
name: parent
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - id: sub
    src: phases/sub
    depends_on: []
---
""",
    )
    _write(
        parent / "phases" / "sub" / "SUBGRAPH.md",
        """---
mode: subgraph
name: sub
target_skill: child_skill
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
---
""",
    )
    resolver = in_memory_skill_resolver_factory({"child_skill": child})

    compiled = SkillLoader().compile_skill(parent, skill_resolver=resolver)

    assert compiled.nodes[0].ast.target_skill == "child_skill"


def test_v030_subgraph_target_skill_io_mismatch_fails(
    tmp_path: Path,
    in_memory_skill_resolver_factory: Any,
) -> None:
    child = tmp_path / "child"
    _graph(child)
    _agent(child)

    parent = tmp_path / "parent"
    _write(
        parent / "GRAPH.md",
        """---
schema_version: "0.3.0"
name: parent
io:
  inputs:
    type: object
    properties:
      other:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - id: sub
    src: phases/sub
    depends_on: []
---
""",
    )
    _write(
        parent / "phases" / "sub" / "SUBGRAPH.md",
        """---
mode: subgraph
name: sub
target_skill: child_skill
io:
  inputs:
    type: object
    properties:
      other:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
---
""",
    )
    resolver = in_memory_skill_resolver_factory({"child_skill": child})

    with pytest.raises(SkillLoadError, match=r"\[F-v3-subgraph-io-mismatch\]"):
        SkillLoader().compile_skill(parent, skill_resolver=resolver)


def test_v030_agent_runtime_uses_cognitive_template_and_resource_tools(tmp_path: Path) -> None:
    _graph(tmp_path)
    _agent(tmp_path)
    _write(tmp_path / "refs" / "r1.md", "Reference body.")
    chat = FakeAgentChatModel()

    compiled = SkillLoader().compile_skill(tmp_path)
    graph = assemble_graph(compiled, chat_model=chat).graph
    result = graph.invoke({"data": {"topic": "T"}, "flow": {}, "messages": [], "run_id": "r1"})

    system_prompt = chat.messages_seen[0][0].content
    assert "<knowledge_base>" in system_prompt
    assert "output_schema:" in system_prompt
    assert system_prompt.rfind("output_schema:") > system_prompt.rfind("<critical_reminders>")
    assert "read_reference" in chat.bound_tool_names
    assert "read_example" in chat.bound_tool_names
    assert result["data"]["main"] == {"answer": "ok"}
