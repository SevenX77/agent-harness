from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.cognitive.context_facade import Context
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from langchain_core.tools import StructuredTool


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(root: Path, phase_lines: list[str]) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: actions-test
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
"""
        + "\n".join(phase_lines)
        + "\n",
    )
    _write(root / "io" / "inputs.json", "{}\n")
    _write(root / "io" / "outputs.json", "{}\n")


def _logic(root: Path, phase: str = "logic_phase") -> None:
    _write(
        root / "phases" / phase / "LOGIC.md",
        """---
mode: logic
name: logic
---
<python_callable>
foo
</python_callable>
""",
    )


def _skill(root: Path, phase: str = "skill_phase") -> None:
    _write(
        root / "phases" / phase / "SKILL.md",
        """---
mode: skill
name: skill
---
<system_prompt>
Do work.
</system_prompt>
<exit_contract>
Call finish_task.
</exit_contract>
""",
    )


def _subgraph(root: Path, phase: str = "subgraph_phase") -> None:
    _write(
        root / "phases" / phase / "SUBGRAPH.md",
        """---
mode: subgraph
name: sub
target_skill: skills.child
---
""",
    )


def _single_logic(root: Path) -> None:
    _base(root, ['<phase id="logic_phase" src="phases/logic_phase" depends_on="" />'])
    _logic(root)


def _single_skill(root: Path) -> None:
    _base(root, ['<phase id="skill_phase" src="phases/skill_phase" depends_on="" />'])
    _skill(root)


def test_actions_loader_happy_path(tmp_path: Path) -> None:
    _single_logic(tmp_path)
    _write(
        tmp_path / "phases" / "logic_phase" / "actions" / "foo.py",
        "from graph_agent.cognitive.context_facade import Context\n"
        "def foo(context: Context) -> None:\n"
        "    context.set('ok', True)\n",
    )

    compiled = SkillLoader().compile_skill(tmp_path)

    action = compiled.actions.resolve("logic_phase", "foo")
    blackboard: dict[str, object] = {}
    action(Context(blackboard, phase_id="logic_phase", run_id="run-1"))
    assert blackboard == {"ok": True}


def test_tools_loader_happy_path(tmp_path: Path) -> None:
    _single_skill(tmp_path)
    _write(
        tmp_path / "phases" / "skill_phase" / "tools" / "bar.py",
        "def bar(x: int) -> str:\n    return str(x + 1)\n",
    )

    compiled = SkillLoader().compile_skill(tmp_path)

    tools = compiled.tools.for_phase("skill_phase")
    assert len(tools) == 1
    assert isinstance(tools[0], StructuredTool)
    assert tools[0].name == "bar"


def test_context_facade_read_write() -> None:
    blackboard: dict[str, object] = {"inputs": {"name": "Ada"}, "a": 1}
    ctx = Context(blackboard, phase_id="prep", run_id="run-7")

    assert ctx.get("a") == 1
    assert ctx.get("missing", 3) == 3
    assert ctx.has("a")
    ctx.set("b", 2)
    ctx.update(c=3)
    ctx.delete("a")

    assert sorted(ctx.keys()) == ["b", "c", "inputs"]
    assert ctx.inputs["name"] == "Ada"
    assert ctx.phase_id == "prep"
    assert ctx.run_id == "run-7"
    with pytest.raises(TypeError):
        ctx.inputs["name"] = "Grace"  # type: ignore[index]


def test_action_registry_missing_keys_raise_keyerror(tmp_path: Path) -> None:
    _single_logic(tmp_path)
    _write(
        tmp_path / "phases" / "logic_phase" / "actions" / "foo.py",
        "def foo(context) -> None:\n    pass\n",
    )
    registry = SkillLoader().compile_skill(tmp_path).actions

    with pytest.raises(KeyError, match="unknown phase_id"):
        registry.resolve("missing", "foo")
    with pytest.raises(KeyError, match="unknown action"):
        registry.resolve("logic_phase", "missing")


def test_tool_registry_empty_phase_returns_empty_list(tmp_path: Path) -> None:
    _single_skill(tmp_path)

    registry = SkillLoader().compile_skill(tmp_path).tools

    assert registry.for_phase("missing") == []


def test_action_missing_ctx_param_fatal(tmp_path: Path) -> None:
    _single_logic(tmp_path)
    _write(
        tmp_path / "phases" / "logic_phase" / "actions" / "foo.py", "def foo(x: int):\n    pass\n"
    )

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-logic-action-entrypoint-missing]"
    assert "context/ctx" in str(exc_info.value)


def test_tool_with_ctx_param_fatal(tmp_path: Path) -> None:
    _single_skill(tmp_path)
    _write(
        tmp_path / "phases" / "skill_phase" / "tools" / "bar.py",
        "def bar(ctx, x: int) -> str:\n    return 'x'\n",
    )

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-agent-tool-unknown]"
    assert "blackboard" in str(exc_info.value)


def test_tool_imports_context_fatal(tmp_path: Path) -> None:
    _single_skill(tmp_path)
    _write(
        tmp_path / "phases" / "skill_phase" / "tools" / "bar.py",
        "from graph_agent.cognitive.context_facade import Context\n"
        "def bar(x: int) -> str:\n"
        "    return str(x)\n",
    )

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-agent-tool-unknown]"
    assert "Context facade" in str(exc_info.value)


def test_action_in_skill_phase_fatal(tmp_path: Path) -> None:
    _single_skill(tmp_path)
    _write(
        tmp_path / "phases" / "skill_phase" / "actions" / "foo.py", "def foo(context):\n    pass\n"
    )

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-logic-action-dir-missing]"
    assert "actions/ is only allowed" in str(exc_info.value)


def test_tool_in_logic_phase_fatal(tmp_path: Path) -> None:
    _single_logic(tmp_path)
    _write(
        tmp_path / "phases" / "logic_phase" / "tools" / "bar.py",
        "def bar() -> str:\n    return 'x'\n",
    )

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-agent-tool-unknown]"
    assert "tools/ is only allowed" in str(exc_info.value)


def test_action_in_subgraph_phase_fatal(tmp_path: Path) -> None:
    _base(tmp_path, ['<phase id="subgraph_phase" src="phases/subgraph_phase" depends_on="" />'])
    _subgraph(tmp_path)
    _write(
        tmp_path / "phases" / "subgraph_phase" / "actions" / "foo.py",
        "def foo(context):\n    pass\n",
    )

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-logic-action-dir-missing]"
    assert "SUBGRAPH" in str(exc_info.value)


def test_tool_in_subgraph_phase_fatal(tmp_path: Path) -> None:
    _base(tmp_path, ['<phase id="subgraph_phase" src="phases/subgraph_phase" depends_on="" />'])
    _subgraph(tmp_path)
    _write(
        tmp_path / "phases" / "subgraph_phase" / "tools" / "bar.py", "def bar():\n    return 'x'\n"
    )

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-agent-tool-unknown]"
    assert "SUBGRAPH" in str(exc_info.value)


def test_root_level_actions_fatal(tmp_path: Path) -> None:
    _single_skill(tmp_path)
    _write(tmp_path / "actions" / "foo.py", "def foo(context):\n    pass\n")

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-logic-action-dir-missing]"
    assert "root-level actions" in str(exc_info.value)


def test_root_level_tools_allowed(tmp_path: Path) -> None:
    _single_skill(tmp_path)
    _write(tmp_path / "tools" / "root_tool.py", "def root_tool() -> str:\n    return 'root'\n")

    compiled = SkillLoader().compile_skill(tmp_path)

    assert [tool.name for tool in compiled.tools.for_root()] == ["root_tool"]
    assert [tool.name for tool in compiled.tools.for_phase("skill_phase")] == ["root_tool"]


def test_duplicate_action_id_fatal(tmp_path: Path) -> None:
    _single_logic(tmp_path)
    _write(
        tmp_path / "phases" / "logic_phase" / "actions" / "one.py",
        "def my_action(context):\n    pass\n",
    )
    _write(
        tmp_path / "phases" / "logic_phase" / "actions" / "two.py",
        "def my_action(context):\n    pass\n",
    )

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-logic-action-name-invalid]"
    assert "duplicate action" in str(exc_info.value)


def test_module_import_failure_fatal(tmp_path: Path) -> None:
    _single_logic(tmp_path)
    _write(tmp_path / "phases" / "logic_phase" / "actions" / "bad.py", "def bad(:\n    pass\n")

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path)
    assert exc_info.value.payload.code == "[F-v3-logic-action-entrypoint-missing]"
    assert "module load failed" in str(exc_info.value)
