"""Unit tests for the tool_paths validator."""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from graph_agent.core.manifest import (
    AgentSkillDef,
    GraphSkillDef,
    SkillManifest,
)
from graph_agent.core.parser import parse_skill_file
from graph_agent.core.validators.tool_paths import check_tool_paths


def _stage_local_tool(tmp_path: Path, *, dotted: str) -> Path:
    """Materialise a no-op .py file at the dotted location under tmp_path."""
    parts = dotted.split(".")
    *dirs, leaf = parts
    cur = tmp_path
    for d in dirs:
        cur = cur / d
        cur.mkdir(exist_ok=True)
        (cur / "__init__.py").write_text("", encoding="utf-8")
    py_file = cur / f"{leaf}.py"
    py_file.write_text("def _placeholder() -> str: return ''\n", encoding="utf-8")
    return py_file


def _write_agent_with_tools(parent_dir: Path, *, name: str, tools: list[str]) -> Path:
    tools_block = "\n".join(f"  - {t}" for t in tools)
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        f"name: {name}\n"
        f"description: agent {name}\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        "agent_tools:\n"
        f"{tools_block}\n"
        "---\n"
    )
    path = parent_dir / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _load(parent_path: Path):
    raw = parse_skill_file(parent_path)["frontmatter"]
    return TypeAdapter(SkillManifest).validate_python(raw)


def test_returns_empty_when_local_and_builtin_tools_resolve(tmp_path: Path) -> None:
    _stage_local_tool(tmp_path, dotted="tools.helpers")
    agent_path = _write_agent_with_tools(
        tmp_path,
        name="my_agent",
        tools=["tools.helpers.placeholder", "builtin.parallel_map"],
    )

    manifest = _load(agent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert issues == []
