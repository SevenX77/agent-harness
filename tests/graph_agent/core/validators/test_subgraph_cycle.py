"""Unit tests for the subgraph_cycle validator."""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from graph_agent.core.manifest import GraphSkillDef, SkillManifest
from graph_agent.core.parser import parse_skill_file
from graph_agent.core.validators.subgraph_cycle import (
    check_subgraph_cycles,
)


def _write_graph_skill(
    tmp_path: Path,
    *,
    name: str,
    subgraphs: list[tuple[str, str]] | None = None,
) -> Path:
    """Stage a minimal valid GraphSkillDef SKILL.md.

    ``subgraphs`` is a list of ``(phase_name, subgraph_path_string)`` tuples.
    Each becomes a DelegatePhase wired up with a no-op context_bridge so the
    parent parses cleanly. If empty, a no-op logic phase is used so the
    Pydantic ``min_length=1`` constraint on ``phases`` is satisfied.
    """
    delegate_phases = ""
    for phase_name, subgraph_path in subgraphs or []:
        delegate_phases += (
            f"  - name: {phase_name}\n"
            f"    mode: delegate\n"
            f"    subgraph: {subgraph_path}\n"
            f"    context_bridge:\n"
            f"      inputs: {{}}\n"
            f"      outputs: {{}}\n"
        )
    if not delegate_phases:
        delegate_phases = (
            "  - name: only_phase\n"
            "    mode: logic\n"
            "    execute_steps:\n"
            "      - graph_agent.callbacks.events.SubgraphEnterEvent\n"
        )
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        f"name: {name}\n"
        f"description: graph skill {name} for subgraph_cycle tests\n"
        "io:\n"
        "  inputs: []\n"
        "  outputs: []\n"
        "phases:\n"
        f"{delegate_phases}"
        "---\n"
    )
    path = tmp_path / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _load_parent(parent_path: Path) -> GraphSkillDef:
    raw = parse_skill_file(parent_path)["frontmatter"]
    return TypeAdapter(SkillManifest).validate_python(raw)


def test_returns_empty_when_no_cycle(tmp_path: Path) -> None:
    leaf = _write_graph_skill(tmp_path, name="leaf")  # noqa: F841
    middle = _write_graph_skill(  # noqa: F841
        tmp_path, name="middle", subgraphs=[("p", "leaf.md")],
    )
    parent_path = _write_graph_skill(
        tmp_path, name="parent", subgraphs=[("p", "middle.md")],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    assert issues == []


def test_fatal_when_self_cycle(tmp_path: Path) -> None:
    parent_path = _write_graph_skill(
        tmp_path, name="parent", subgraphs=[("self_loop", "parent.md")],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-subgraph-cycle"
    assert issues[0].severity == "FATAL"
    assert "parent.md" in issues[0].message
    assert issues[0].location.endswith("phases.self_loop.subgraph")


def test_fatal_when_indirect_cycle(tmp_path: Path) -> None:
    a_path = tmp_path / "a.md"
    b_path = tmp_path / "b.md"
    a_path.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        "name: a\n"
        "description: a\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        "  - name: to_b\n"
        "    mode: delegate\n"
        "    subgraph: b.md\n"
        "    context_bridge:\n"
        "      inputs: {}\n"
        "      outputs: {}\n"
        "---\n",
        encoding="utf-8",
    )
    b_path.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        "name: b\n"
        "description: b\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        "  - name: to_a\n"
        "    mode: delegate\n"
        "    subgraph: a.md\n"
        "    context_bridge:\n"
        "      inputs: {}\n"
        "      outputs: {}\n"
        "---\n",
        encoding="utf-8",
    )

    parent = _load_parent(a_path)
    issues = check_subgraph_cycles(parent, skill_path=a_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-subgraph-cycle"
    assert "a.md" in issues[0].message
    assert "b.md" in issues[0].message
    # Cycle is closed at b's phase to_a, not a's phase to_b.
    assert issues[0].location.endswith("phases.to_a.subgraph")


def test_silently_skips_missing_child(tmp_path: Path) -> None:
    parent_path = _write_graph_skill(
        tmp_path,
        name="parent",
        subgraphs=[("dead_link", "nonexistent.md")],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    # Missing child is context_bridge's concern, not cycle validator's.
    assert issues == []


def test_silently_skips_agent_child(tmp_path: Path) -> None:
    agent_path = tmp_path / "agent.md"
    agent_path.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        "name: agent_child\n"
        "description: child agent\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        "---\n",
        encoding="utf-8",
    )
    parent_path = _write_graph_skill(
        tmp_path, name="parent", subgraphs=[("p", "agent.md")],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    # Agent has no phases → cannot participate in a cycle. Silent skip.
    assert issues == []


def test_cycle_reported_once_for_two_parent_phases(tmp_path: Path) -> None:
    parent_path = _write_graph_skill(
        tmp_path,
        name="parent",
        subgraphs=[
            ("p1", "parent.md"),
            ("p2", "parent.md"),
        ],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    assert len(issues) == 1
    assert issues[0].location.endswith("phases.p1.subgraph")
