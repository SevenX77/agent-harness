"""Unit tests for the tool_paths validator."""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.manifest import (
    SkillManifest,
)
from graph_agent.core.parser import parse_skill_file
from graph_agent.core.validators.tool_paths import check_tool_paths
from pydantic import TypeAdapter


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


def _write_graph_with_phases(
    parent_dir: Path,
    *,
    name: str,
    phases_yaml: str,
) -> Path:
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        f"name: {name}\n"
        f"description: graph {name}\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        f"{phases_yaml}"
        "---\n"
    )
    path = parent_dir / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


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


def test_fatal_when_ref_lacks_dot(tmp_path: Path) -> None:
    agent_path = _write_agent_with_tools(
        tmp_path,
        name="my_agent",
        tools=["nodot"],
    )

    manifest = _load(agent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-invalid-format"
    assert "nodot" in issues[0].message
    assert issues[0].location == "SKILL.md:agent_tools.0"


def test_fatal_when_local_module_missing(tmp_path: Path) -> None:
    agent_path = _write_agent_with_tools(
        tmp_path,
        name="my_agent",
        tools=["missing.fn"],
    )

    manifest = _load(agent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-not-found"
    assert "missing.fn" in issues[0].message
    assert issues[0].location == "SKILL.md:agent_tools.0"


def test_fatal_when_builtin_module_missing(tmp_path: Path) -> None:
    agent_path = _write_agent_with_tools(
        tmp_path,
        name="my_agent",
        tools=["builtin.no_such_submodule.fn"],
    )

    manifest = _load(agent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-not-found"
    assert "builtin.no_such_submodule.fn" in issues[0].message
    assert "graph_agent.tools.builtin.no_such_submodule" in issues[0].message


def test_fatal_when_llm_phase_agent_tools_missing(tmp_path: Path) -> None:
    parent_path = _write_graph_with_phases(
        tmp_path,
        name="parent",
        phases_yaml=(
            "  - name: think\n"
            "    mode: llm\n"
            "    prompt: do it\n"
            "    agent_tools:\n"
            "      - missing.fn\n"
        ),
    )

    manifest = _load(parent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-not-found"
    assert issues[0].location == "SKILL.md:phases.think.agent_tools.0"


def test_fatal_when_llm_phase_validator_missing(tmp_path: Path) -> None:
    parent_path = _write_graph_with_phases(
        tmp_path,
        name="parent",
        phases_yaml=(
            "  - name: think\n    mode: llm\n    prompt: do it\n    validator: missing.validate\n"
        ),
    )

    manifest = _load(parent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-not-found"
    assert issues[0].location == "SKILL.md:phases.think.validator"


# Cohesion plan follow-up (2026-04-26): LLMPhase.steps is restored as
# list[str] prompt structure, not executable tool references. The earlier
# fixtures here exercised tool_paths walking through object-shaped
# phase.steps; those regression cases collapse into the normal phase-level
# agent_tools / validator walks above.


def test_fatal_when_logic_phase_execute_steps_missing(tmp_path: Path) -> None:
    parent_path = _write_graph_with_phases(
        tmp_path,
        name="parent",
        phases_yaml=("  - name: render\n    mode: logic\n    execute_steps:\n      - missing.fn\n"),
    )

    manifest = _load(parent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-not-found"
    assert issues[0].location == "SKILL.md:phases.render.execute_steps.0"


def test_fatal_when_logic_phase_validator_missing(tmp_path: Path) -> None:
    parent_path = _write_graph_with_phases(
        tmp_path,
        name="parent",
        phases_yaml=(
            "  - name: render\n"
            "    mode: logic\n"
            "    execute_steps:\n"
            "      - builtin.parallel_map\n"
            "    validator: missing.validate\n"
        ),
    )

    manifest = _load(parent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-not-found"
    assert issues[0].location == "SKILL.md:phases.render.validator"


def test_fatal_when_logic_step_imports_run_skill(tmp_path: Path) -> None:
    py_file = _stage_local_tool(tmp_path, dotted="script.runner")
    py_file.write_text(
        "from graph_agent.core.runner import run_skill\n\n"
        "def prepare(ctx):\n"
        "    return run_skill('child/SKILL.md')\n",
        encoding="utf-8",
    )
    parent_path = _write_graph_with_phases(
        tmp_path,
        name="parent",
        phases_yaml=(
            "  - name: render\n    mode: logic\n    execute_steps:\n      - script.runner.prepare\n"
        ),
    )

    manifest = _load(parent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "E-NESTED-RUN-SKILL"
    assert issues[0].severity == "FATAL"
    assert issues[0].location == "SKILL.md:phases.render.execute_steps.0"
    assert "DelegatePhase" in issues[0].message


def test_no_issue_when_logic_step_does_not_import_run_skill(tmp_path: Path) -> None:
    py_file = _stage_local_tool(tmp_path, dotted="script.runner")
    py_file.write_text(
        "def prepare(ctx):\n    ctx['prepared'] = True\n",
        encoding="utf-8",
    )
    parent_path = _write_graph_with_phases(
        tmp_path,
        name="parent",
        phases_yaml=(
            "  - name: render\n    mode: logic\n    execute_steps:\n      - script.runner.prepare\n"
        ),
    )

    manifest = _load(parent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert issues == []


def test_no_issue_for_runner_module_import_without_run_skill(
    tmp_path: Path,
) -> None:
    py_file = _stage_local_tool(tmp_path, dotted="script.runner")
    py_file.write_text(
        "import graph_agent.core.runner\n\ndef prepare(ctx):\n    ctx['prepared'] = True\n",
        encoding="utf-8",
    )
    parent_path = _write_graph_with_phases(
        tmp_path,
        name="parent",
        phases_yaml=(
            "  - name: render\n    mode: logic\n    execute_steps:\n      - script.runner.prepare\n"
        ),
    )

    manifest = _load(parent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert issues == []
