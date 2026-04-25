"""Unit tests for the context_bridge validator."""
from __future__ import annotations

import textwrap
from pathlib import Path

from pydantic import TypeAdapter

from graph_agent.core.manifest import GraphSkillDef, SkillManifest
from graph_agent.core.validators.context_bridge import (
    check_context_bridge,
)


def _write_child_graph(
    tmp_path: Path,
    *,
    name: str,
    inputs: list[str],
    outputs: list[str],
) -> Path:
    """Stage a minimal valid GraphSkillDef SKILL.md and return its path.

    Hand-built column-0 string instead of textwrap.dedent. Mixing a
    dedented template with f-string-interpolated nested-indent blocks
    makes textwrap.dedent see different common-leading-whitespace and
    produces a left-shifted ``---`` line that breaks the frontmatter
    delimiter. Don't switch to dedent without reproving.
    """
    inputs_lines = "\n".join(
        f"    - name: {n}\n      source: runtime" for n in inputs
    )
    outputs_lines = "\n".join(
        f"    - name: {n}\n      target: artifact" for n in outputs
    )
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        f"name: {name}\n"
        "description: child graph for context_bridge tests\n"
        "io:\n"
        "  inputs:\n"
        f"{inputs_lines}\n"
        "  outputs:\n"
        f"{outputs_lines}\n"
        "phases:\n"
        "  - name: only_phase\n"
        "    mode: logic\n"
        "    execute_steps:\n"
        "      - graph_agent.callbacks.events.SubgraphEnterEvent\n"
        "---\n"
    )
    path = tmp_path / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _build_parent(
    *,
    child_path: Path,
    bridge_inputs: dict[str, str],
    bridge_outputs: dict[str, str],
) -> GraphSkillDef:
    """Construct a valid parent GraphSkillDef in-memory pointing at ``child_path``."""
    raw = {
        "schema_version": "2.0",
        "type": "graph",
        "name": "parent",
        "description": "parent graph for context_bridge tests",
        "io": {"inputs": [], "outputs": []},
        "phases": [
            {
                "name": "delegate_phase",
                "mode": "delegate",
                "subgraph": child_path.name,
                "context_bridge": {
                    "inputs": bridge_inputs,
                    "outputs": bridge_outputs,
                },
            }
        ],
    }
    return TypeAdapter(SkillManifest).validate_python(raw)


def test_returns_empty_when_inputs_and_outputs_align(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path,
        name="child",
        inputs=["alpha", "beta"],
        outputs=["gamma"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_a": "alpha", "parent_b": "beta"},
        bridge_outputs={"gamma": "parent_g"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert issues == []


def test_fatal_when_child_input_undeclared(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path, name="child", inputs=["alpha"], outputs=["gamma"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_typo": "alphaa"},  # 'alphaa' not in child.io.inputs
        bridge_outputs={"gamma": "parent_g"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "F-context-bridge-input-undeclared"
    assert issue.severity == "FATAL"
    assert "alphaa" in issue.message
    assert "alpha" in issue.message  # the available declared name appears in the help
    assert issue.location.endswith("inputs.parent_typo")


def _write_child_agent(tmp_path: Path, *, name: str) -> Path:
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        f"name: {name}\n"
        "description: child agent skill\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        "---\n"
    )
    path = tmp_path / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _write_child_persona(tmp_path: Path, *, name: str) -> Path:
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: persona\n"
        f"name: {name}\n"
        "description: child persona skill\n"
        "role_profile: |\n"
        "  A test persona used as a (forbidden) delegate child.\n"
        "---\n"
    )
    path = tmp_path / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_fatal_when_child_path_missing(tmp_path: Path) -> None:
    parent = _build_parent(
        child_path=tmp_path / "nonexistent.md",
        bridge_inputs={"parent_a": "alpha"},
        bridge_outputs={"gamma": "parent_g"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-context-bridge-child-missing"
    assert issues[0].severity == "FATAL"
    assert "nonexistent.md" in issues[0].message


def test_fatal_when_child_frontmatter_invalid(tmp_path: Path) -> None:
    bad_child = tmp_path / "bad.md"
    bad_child.write_text(
        textwrap.dedent(
            """\
            ---
            schema_version: "2.0"
            type: graph
            name: bad
            description: missing-required-io
            phases:
              - name: x
                mode: logic
                execute_steps:
                  - some.path
            ---
            """
        ),
        encoding="utf-8",
    )
    parent = _build_parent(
        child_path=bad_child,
        bridge_inputs={"p": "x"},
        bridge_outputs={"y": "p"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert any(i.rule_id == "F-context-bridge-child-invalid" for i in issues)
    invalid = next(i for i in issues if i.rule_id == "F-context-bridge-child-invalid")
    assert invalid.severity == "FATAL"
    assert str(bad_child) in invalid.location


def test_warning_when_child_is_agent_skill(tmp_path: Path) -> None:
    child = _write_child_agent(tmp_path, name="agent_child")
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_x": "anything"},
        bridge_outputs={"anything_back": "parent_y"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "W-context-bridge-agent-child"
    assert issues[0].severity == "WARNING"
    assert "agent" in issues[0].message.lower()
    assert "delegate_phase" in issues[0].location


def test_fatal_when_child_is_persona_skill(tmp_path: Path) -> None:
    child = _write_child_persona(tmp_path, name="persona_child")
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_x": "anything"},
        bridge_outputs={"anything_back": "parent_y"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-context-bridge-persona-child"
    assert issues[0].severity == "FATAL"
    assert "persona" in issues[0].message.lower()


def test_returns_empty_when_parent_has_no_delegate_phases(tmp_path: Path) -> None:
    raw = {
        "schema_version": "2.0",
        "type": "graph",
        "name": "all_logic",
        "description": "no delegate phases at all",
        "io": {"inputs": [], "outputs": []},
        "phases": [
            {
                "name": "logic_only",
                "mode": "logic",
                "execute_steps": ["some.module.fn"],
            },
            {
                "name": "llm_only",
                "mode": "llm",
                "prompt": "do the thing",
            },
        ],
    }
    parent = TypeAdapter(SkillManifest).validate_python(raw)

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert issues == []


def test_accumulates_input_and_output_issues_in_one_phase(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path, name="child", inputs=["alpha"], outputs=["gamma"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"p_a": "alpha", "p_typo": "alfa"},
        bridge_outputs={"gamma": "p_g", "delta": "p_d"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    rule_ids = sorted(i.rule_id for i in issues)
    assert rule_ids == [
        "F-context-bridge-input-undeclared",
        "F-context-bridge-output-undeclared",
    ]


def test_fatal_when_child_output_undeclared(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path, name="child", inputs=["alpha"], outputs=["gamma"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_a": "alpha"},
        bridge_outputs={"gammma": "parent_g"},  # typo: child has 'gamma'
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "F-context-bridge-output-undeclared"
    assert issue.severity == "FATAL"
    assert "gammma" in issue.message
    assert "gamma" in issue.message
    assert issue.location.endswith("outputs.gammma")
