from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent import (
    BlackboardState,
    CompiledSkill,
    CompiledStateGraph,
    assemble_graph,
    compile_skill,
)
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import load_workflow_from_md
from tests.core.test_v21_graph_assembly import _base, _logic


def test_compile_skill_facade_returns_compiled(tmp_path: Path) -> None:
    _base(tmp_path, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(tmp_path)

    compiled = compile_skill(tmp_path, cache=False)

    assert isinstance(compiled, CompiledSkill)


def test_assemble_graph_facade_returns_compiled_state_graph(tmp_path: Path) -> None:
    _base(tmp_path, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(tmp_path)

    assembled = assemble_graph(compile_skill(tmp_path, cache=False))

    assert isinstance(assembled, CompiledStateGraph)


def test_blackboard_state_exported() -> None:
    state: BlackboardState = {"data": {}}
    assert state["data"] == {}


def test_load_workflow_from_md_v21_root_ok(tmp_path: Path) -> None:
    _base(tmp_path, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(tmp_path)

    graph = load_workflow_from_md(tmp_path)
    result = graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "r1"})

    assert result["data"]["foo"] == 42


def test_load_workflow_from_md_legacy_schema_2_skill_md_crash(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        '---\nschema_version: "2.0"\nname: old\n---\n', encoding="utf-8"
    )

    with pytest.raises(SkillLoadError, match=r"root SKILL.md is not supported"):
        load_workflow_from_md(tmp_path)
