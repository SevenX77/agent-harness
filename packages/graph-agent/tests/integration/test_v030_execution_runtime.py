from __future__ import annotations

from pathlib import Path

from graph_agent.core import runner
from langchain_core.messages import AIMessage

from tests.conftest import InMemorySkillResolver


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FinishTaskChatModel:
    def __init__(self) -> None:
        self.bound_tool_names: list[str] = []
        self.system_prompts: list[str] = []

    def bind_tools(self, tools: list[object]) -> FinishTaskChatModel:
        self.bound_tool_names = [getattr(tool, "name", "") for tool in tools]
        return self

    def invoke(self, messages: list[object]) -> AIMessage:
        self.system_prompts.append(str(messages[0].content))
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


def _agent_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "0.3.0"
name: runtime-agent
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
  - id: main
    src: phases/main
    depends_on: []
---
""",
    )
    _write(root / "refs" / "r1.md", "Reference body.")
    _write(
        root / "phases" / "main" / "SKILL.md",
        """---
mode: agent
name: main
phase_config:
  tools:
    - finish_task
  references:
    - id: R1
      path: refs/r1.md
      summary: Primary reference.
  examples:
    - id: E1
      type: inline
      content: Inline example.
---
<role>
Research assistant.
</role>
<goal>
Answer using @reference:R1 and @example:E1.
</goal>
<step id="S1" name="Read">
Read @reference:R1.
</step>
<protocol id="P1">
Cite evidence.
</protocol>
<exit_contract>
Return answer.
</exit_contract>
""",
    )


def test_v030_runner_executes_agent_with_resolver_and_builtin_tools(tmp_path: Path) -> None:
    _agent_skill(tmp_path)
    chat = FinishTaskChatModel()

    result = runner._run_skill_dict(
        tmp_path,
        mock_llm=chat,
        skill_resolver=InMemorySkillResolver({}),
        topic="T",
    )

    assert result["context"]["main"] == {"answer": "ok"}
    assert "read_reference" in chat.bound_tool_names
    assert "read_example" in chat.bound_tool_names
    assert "output_schema:" in chat.system_prompts[0]
    assert "Reference body." in chat.system_prompts[0]


def _logic_skill(root: Path, *, name: str) -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "0.3.0"
name: {name}
io:
  inputs:
    type: object
    properties:
      raw:
        type: string
  outputs:
    type: object
    properties:
      clean:
        type: string
phases:
  - id: normalize
    src: phases/normalize
    depends_on: []
---
""",
    )
    _write(
        root / "phases" / "normalize" / "LOGIC.md",
        """---
mode: logic
name: normalize
io:
  inputs:
    type: object
    properties:
      raw:
        type: string
  outputs:
    type: object
    properties:
      clean:
        type: string
actions:
  - normalize
---
""",
    )
    _write(
        root / "actions" / "normalize.py",
        "def run(state_slice, **kwargs):\n"
        "    return {'clean': state_slice['raw'].strip().lower()}\n",
    )


def _subgraph_parent(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "0.3.0"
name: parent
io:
  inputs:
    type: object
    properties:
      raw:
        type: string
  outputs:
    type: object
    properties:
      clean:
        type: string
phases:
  - id: child
    src: phases/child
    depends_on: []
---
""",
    )
    _write(
        root / "phases" / "child" / "SUBGRAPH.md",
        """---
mode: subgraph
name: child
target_skill: child_skill
io:
  inputs:
    type: object
    properties:
      raw:
        type: string
  outputs:
    type: object
    properties:
      clean:
        type: string
---
""",
    )


def test_v030_runner_invokes_subgraph_by_skill_resolver(tmp_path: Path) -> None:
    child = tmp_path / "child"
    parent = tmp_path / "parent"
    _logic_skill(child, name="child-skill")
    _subgraph_parent(parent)
    resolver = InMemorySkillResolver({"child_skill": child})

    result = runner._run_skill_dict(parent, skill_resolver=resolver, raw="  HELLO  ")

    assert result["context"]["clean"] == "hello"
