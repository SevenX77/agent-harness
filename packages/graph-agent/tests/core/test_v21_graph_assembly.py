from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.graph_assembler import assemble_graph
from langchain_core.messages import AIMessage


class FakeToolChatModel:
    def __init__(self, calls: list[list[dict[str, Any]]]) -> None:
        self.calls = calls
        self.messages_seen: list[Any] = []
        self.bound_tools: list[Any] = []

    def bind_tools(self, tools: list[Any]) -> FakeToolChatModel:
        self.bound_tools = tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.messages_seen.append(messages)
        tool_calls = self.calls.pop(0) if self.calls else []
        return AIMessage(content="", tool_calls=tool_calls)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(root: Path, phases: str, outputs: dict[str, Any] | None = None) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: assembly-test
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
"""
        + phases,
    )
    _write(root / "io" / "inputs.json", "{}\n")
    _write(root / "io" / "outputs.json", json.dumps(outputs or {}, ensure_ascii=False))


def _logic(root: Path, phase: str = "logic", action: str = "write_value") -> None:
    _write(
        root / "phases" / phase / "LOGIC.md",
        f"""---
mode: logic
---
<python_callable>
{action}
</python_callable>
""",
    )
    _write(
        root / "phases" / phase / "actions" / f"{action}.py",
        "def write_value(context):\n    context.set('foo', 42)\n",
    )


def _logic_action(root: Path, phase: str, action: str, body: str) -> None:
    _write(
        root / "phases" / phase / "LOGIC.md",
        f"""---
mode: logic
---
<python_callable>
{action}
</python_callable>
""",
    )
    _write(root / "phases" / phase / "actions" / f"{action}.py", body)


def _skill(root: Path, phase: str = "skill", tools: list[str] | None = None) -> None:
    tools_yaml = (
        "" if tools is None else "tools:\n" + "\n".join(f"  - {tool}" for tool in tools) + "\n"
    )
    _write(
        root / "phases" / phase / "SKILL.md",
        f"""---
mode: skill
{tools_yaml}---
<system_prompt>
Do work.
</system_prompt>
<exit_contract>
Call finish_task.
</exit_contract>
""",
    )


def _subgraph(root: Path, phase: str = "sub", ref: str = "child") -> None:
    _write(
        root / "phases" / phase / "SUBGRAPH.md",
        f"""---
mode: subgraph
---
<sub_skill_ref>
{ref}
</sub_skill_ref>
""",
    )


def test_assemble_single_logic_phase(tmp_path: Path) -> None:
    _base(tmp_path, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(tmp_path)

    graph = assemble_graph(compile_skill(tmp_path, cache=False)).graph
    result = graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "r1"})

    assert result["data"]["foo"] == 42


def test_assemble_single_skill_phase_with_fake_llm(tmp_path: Path) -> None:
    _base(
        tmp_path,
        '<phase id="skill" src="phases/skill" depends_on="" />\n',
        {"type": "object", "properties": {"result": {"type": "string"}}, "required": ["result"]},
    )
    _skill(tmp_path)
    chat = FakeToolChatModel(
        [[{"name": "finish_task", "args": {"markdown": "## result\n\nok"}, "id": "finish-1"}]]
    )

    graph = assemble_graph(compile_skill(tmp_path, cache=False), chat_model=chat).graph
    result = graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "r1"})

    assert result["flow"]["finish_task_result"]["ok"] is True
    assert result["data"]["skill"] == {"result": "ok"}
    assert chat.messages_seen[0][-1].content == "Call finish_task."


def test_assemble_logic_skill_dependency(tmp_path: Path) -> None:
    _base(
        tmp_path,
        '<phase id="logic" src="phases/logic" depends_on="" />\n'
        '<phase id="skill" src="phases/skill" depends_on="logic" />\n',
    )
    _logic(tmp_path)
    _skill(tmp_path)
    chat = FakeToolChatModel(
        [[{"name": "finish_task", "args": {"markdown": "## summary\n\nused"}, "id": "finish-1"}]]
    )

    result = assemble_graph(compile_skill(tmp_path, cache=False), chat_model=chat).graph.invoke(
        {"data": {}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["data"]["foo"] == 42
    assert result["data"]["skill"] == {"summary": "used"}


def test_assemble_fanout_disjoint_data_keys_merge(tmp_path: Path) -> None:
    _base(
        tmp_path,
        '<phase id="prepare" src="phases/prepare" depends_on="" />\n'
        '<phase id="branch_a" src="phases/branch_a" depends_on="prepare" />\n'
        '<phase id="branch_b" src="phases/branch_b" depends_on="prepare" />\n'
        '<phase id="assemble" src="phases/assemble" depends_on="branch_a branch_b" />\n',
    )
    _logic_action(tmp_path, "prepare", "prepare", "def prepare(context):\n    return None\n")
    _logic_action(
        tmp_path, "branch_a", "write_a", "def write_a(context):\n    return {'a_out': 1}\n"
    )
    _logic_action(
        tmp_path, "branch_b", "write_b", "def write_b(context):\n    return {'b_out': 2}\n"
    )
    _logic_action(tmp_path, "assemble", "assemble", "def assemble(context):\n    return None\n")

    result = assemble_graph(compile_skill(tmp_path, cache=False)).graph.invoke(
        {"data": {}, "flow": {}, "messages": [], "run_id": "fanout-merge"}
    )

    assert result["data"] == {"a_out": 1, "b_out": 2}


def test_assemble_fanout_same_data_key_conflict_fatal(tmp_path: Path) -> None:
    _base(
        tmp_path,
        '<phase id="prepare" src="phases/prepare" depends_on="" />\n'
        '<phase id="branch_a" src="phases/branch_a" depends_on="prepare" />\n'
        '<phase id="branch_b" src="phases/branch_b" depends_on="prepare" />\n'
        '<phase id="assemble" src="phases/assemble" depends_on="branch_a branch_b" />\n',
    )
    _logic_action(tmp_path, "prepare", "prepare", "def prepare(context):\n    return None\n")
    _logic_action(
        tmp_path, "branch_a", "write_a", "def write_a(context):\n    return {'shared': 1}\n"
    )
    _logic_action(
        tmp_path, "branch_b", "write_b", "def write_b(context):\n    return {'shared': 2}\n"
    )
    _logic_action(tmp_path, "assemble", "assemble", "def assemble(context):\n    return None\n")

    graph = assemble_graph(compile_skill(tmp_path, cache=False)).graph
    with pytest.raises(GraphAgentFatalError, match=r"\[F-v21-state-conflict\].*key='shared'"):
        graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "fanout-conflict"})


def test_assemble_subgraph_phase(tmp_path: Path) -> None:
    _base(tmp_path, '<phase id="sub" src="phases/sub" depends_on="" />\n')
    _subgraph(tmp_path)
    child = tmp_path / "phases" / "sub" / "child"
    _base(child, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(child)

    result = assemble_graph(compile_skill(tmp_path, cache=False)).graph.invoke(
        {"data": {}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["data"]["foo"] == 42


def test_critic_tool_wired_to_skill(tmp_path: Path) -> None:
    _base(tmp_path, '<phase id="skill" src="phases/skill" depends_on="" />\n')
    _skill(tmp_path, tools=["reviewer"])
    chat = FakeToolChatModel(
        [
            [
                {
                    "name": "reviewer",
                    "args": {"target_text": "draft", "criteria": "quality"},
                    "id": "c1",
                }
            ],
            [],
            [{"name": "finish_task", "args": {"markdown": "## result\n\nok"}, "id": "f1"}],
        ]
    )

    result = assemble_graph(compile_skill(tmp_path, cache=False), chat_model=chat).graph.invoke(
        {"data": {}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["flow"]["critic_metrics"]["reviewer"]["invocations"] == 1
    assert any(tool.name == "reviewer" for tool in chat.bound_tools)


def test_unknown_tool_in_skill_phase_fatal(tmp_path: Path) -> None:
    _base(tmp_path, '<phase id="skill" src="phases/skill" depends_on="" />\n')
    _skill(tmp_path, tools=["unknown_xyz"])

    with pytest.raises(SkillLoadError, match=r"\[F-v21-graph\].*unknown_xyz"):
        assemble_graph(compile_skill(tmp_path, cache=False))


def test_terminal_phase_finish_task_validates(tmp_path: Path) -> None:
    _base(
        tmp_path,
        '<phase id="skill" src="phases/skill" depends_on="" />\n',
        {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]},
    )
    _skill(tmp_path)
    chat = FakeToolChatModel(
        [[{"name": "finish_task", "args": {"markdown": "## count\n\n42"}, "id": "f1"}]]
    )

    result = assemble_graph(compile_skill(tmp_path, cache=False), chat_model=chat).graph.invoke(
        {"data": {}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["data"]["skill"] == {"count": 42}


def test_non_terminal_phase_finish_task_no_validate(tmp_path: Path) -> None:
    _base(
        tmp_path,
        '<phase id="skill" src="phases/skill" depends_on="" />\n'
        '<phase id="logic" src="phases/logic" depends_on="skill" />\n',
        {
            "type": "object",
            "properties": {"required_later": {"type": "string"}},
            "required": ["required_later"],
        },
    )
    _skill(tmp_path)
    _logic(tmp_path)
    chat = FakeToolChatModel(
        [[{"name": "finish_task", "args": {"markdown": "## draft\n\nunchecked"}, "id": "f1"}]]
    )

    result = assemble_graph(compile_skill(tmp_path, cache=False), chat_model=chat).graph.invoke(
        {"data": {}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["data"]["skill"] == {"draft": "unchecked"}
