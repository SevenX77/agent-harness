from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from langchain_core.messages import AIMessage


class ToolCallingChatModel:
    def __init__(self, calls: list[list[dict[str, Any]]] | None = None) -> None:
        self.calls = calls or [
            [
                {
                    "name": "finish_task",
                    "args": {"markdown": "## answer\n\nok"},
                    "id": "finish-1",
                }
            ]
        ]
        self.system_prompts: list[str] = []
        self.tool_messages: list[Any] = []

    def bind_tools(self, tools: list[Any]) -> "ToolCallingChatModel":
        del tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.system_prompts.append(str(messages[0].content))
        self.tool_messages.extend(message for message in messages if getattr(message, "name", None))
        tool_calls = self.calls.pop(0) if self.calls else []
        return AIMessage(content="", tool_calls=tool_calls)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: e2e-agent
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
  tools:
    - finish_task
  references:
    - id: R1
      path: refs/r1.md
      summary: Runtime reference
  examples:
    - id: E2
      path: examples/e2.md
      summary: Runtime document example
---
<role>
Executor.
</role>
<goal>
Use @reference:R1 and @example:E2.
</goal>
<step id="S1" name="Read">
Read the resource registries.
</step>
<protocol id="P1">
Cite evidence.
</protocol>
<example id="E1">
Inline example.
</example>
""",
    )
    _write(root / "refs" / "r1.md", "reference body")
    _write(root / "examples" / "e2.md", "document example body")


def _subgraph_parent(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: e2e-parent
io:
  inputs:
    type: object
    properties:
      public:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
      saw_parent_secret:
        type: boolean
phases:
  - sub
---
<phase depends_on="input" output>sub</phase>
""",
    )
    _write(
        root / "phases" / "sub" / "SUBGRAPH.md",
        """---
target_skill: child
io:
  inputs:
    type: object
    properties:
      public:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
      saw_parent_secret:
        type: boolean
---
""",
    )
    child = root / "child"
    _write(
        child / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: child
io:
  inputs:
    type: object
    properties:
      public:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
      saw_parent_secret:
        type: boolean
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
    properties:
      public:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
      saw_parent_secret:
        type: boolean
---
<action>inspect</action>
""",
    )
    _write(
        child / "phases" / "inspect" / "actions" / "inspect.py",
        "def inspect(context):\n"
        "    return {\n"
        "        'answer': context.get('public'),\n"
        "        'saw_parent_secret': context.get('parent_secret') is not None,\n"
        "    }\n",
    )


def test_minimal_agent_run_uses_v030_cognitive_prompt_and_prefilled_knowledge_base(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(tmp_path)
    chat = ToolCallingChatModel()

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    assemble_graph(compiled, chat_model=chat, skill_resolver=mock_skill_resolver).graph.invoke(
        {"data": {"inputs": {"topic": "T"}}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    prompt = chat.system_prompts[0]
    for slot in (
        "role",
        "goal",
        "thinking_style",
        "knowledge_base",
        "examples",
        "ambiguity_feedback",
        "protocol_citation",
        "critical_reminders",
    ):
        assert f"<{slot}>" in prompt
    knowledge_base = prompt[prompt.index("<knowledge_base>") : prompt.index("</knowledge_base>")]
    assert "reference body" in knowledge_base


def test_agent_can_call_read_example_for_declared_document_example(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _agent_skill(tmp_path)
    chat = ToolCallingChatModel(
        [
            [{"name": "read_example", "args": {"example_id": "E2"}, "id": "read-example-1"}],
            [{"name": "finish_task", "args": {"markdown": "## answer\n\nok"}, "id": "finish-1"}],
        ]
    )

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    assemble_graph(compiled, chat_model=chat, skill_resolver=mock_skill_resolver).graph.invoke(
        {"data": {"inputs": {"topic": "T"}}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert any("document example body" in str(message.content) for message in chat.tool_messages)


def test_subgraph_target_skill_runs_and_child_data_does_not_inherit_parent(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _subgraph_parent(tmp_path)

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    result = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph.invoke(
        {
            "data": {
                "inputs": {"public": "visible"},
                "phase_outputs": {"parent": {"parent_secret": "hidden"}},
                "scratch": {"parent_secret": "hidden"},
            },
            "flow": {"trace": "parent"},
            "messages": ["parent-message"],
            "run_id": "r1",
        }
    )

    assert result["data"]["phase_outputs"]["sub"] == {
        "answer": "visible",
        "saw_parent_secret": False,
    }
