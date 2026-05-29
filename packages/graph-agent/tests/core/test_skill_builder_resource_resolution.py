from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.skill_builder import resolve_skill_resource


def test_resolve_skill_resource_loads_local_tool_callable(tmp_path: Path) -> None:
    tool_file = tmp_path / "actions" / "echo.py"
    tool_file.parent.mkdir(parents=True)
    tool_file.write_text(
        "def run(ctx, value='x'):\n"
        "    return f\"{ctx['prefix']}:{value}\"\n",
        encoding="utf-8",
    )

    tool = resolve_skill_resource(tmp_path, "actions.echo.run", kind="tool")

    assert callable(tool)
    assert tool({"prefix": "ok"}, value="now") == "ok:now"


def test_resolve_skill_resource_loads_builtin_tool_callable(tmp_path: Path) -> None:
    tool = resolve_skill_resource(
        tmp_path,
        "builtin.read_file.make_read_file_tool",
        kind="tool",
    )

    assert callable(tool)
    assert tool.__name__ == "make_read_file_tool"


def test_resolve_skill_resource_returns_schema_module(tmp_path: Path) -> None:
    schema_file = tmp_path / "schemas" / "answer.py"
    schema_file.parent.mkdir(parents=True)
    schema_file.write_text("MARKER = 'schema-module'\n", encoding="utf-8")

    module = resolve_skill_resource(tmp_path, "schemas.answer", kind="schema")

    assert module.MARKER == "schema-module"


def test_resolve_skill_resource_normalizes_reference_paths(tmp_path: Path) -> None:
    reference = tmp_path / "references" / "guide.md"
    reference.parent.mkdir(parents=True)
    reference.write_text("guide", encoding="utf-8")

    assert resolve_skill_resource(tmp_path, "./guide.md", kind="reference") == "references/guide.md"
    assert (
        resolve_skill_resource(tmp_path, "references/guide.md", kind="reference")
        == "references/guide.md"
    )


def test_resolve_skill_resource_rejects_invalid_and_non_callable_tools(tmp_path: Path) -> None:
    module_file = tmp_path / "actions" / "value.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("not_a_tool = 42\n", encoding="utf-8")

    with pytest.raises(SkillLoadError, match="Cannot import tool module 'actions'"):
        resolve_skill_resource(tmp_path, "actions.value", kind="tool")

    with pytest.raises(SkillLoadError, match="not callable"):
        resolve_skill_resource(tmp_path, "actions.value.not_a_tool", kind="tool")

    with pytest.raises(SkillLoadError, match="does not define 'missing_tool'"):
        resolve_skill_resource(tmp_path, "actions.value.missing_tool", kind="tool")

    with pytest.raises(SkillLoadError, match="Builtin module 'graph_agent.tools.builtin'"):
        resolve_skill_resource(tmp_path, "builtin.missing_tool", kind="tool")


def test_resolve_skill_resource_rejects_reference_escape_and_missing_file(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-reference.md"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(SkillLoadError, match="must be relative"):
        resolve_skill_resource(tmp_path, str(outside), kind="reference")

    assert resolve_skill_resource(tmp_path, "missing.md", kind="reference") == "missing.md"
