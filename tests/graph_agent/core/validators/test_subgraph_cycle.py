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
