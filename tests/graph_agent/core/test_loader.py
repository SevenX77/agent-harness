"""Loader tests for schema-only phase modes."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.harness import GraphAgentHarness
from graph_agent.core.loader import load_workflow_from_md


def _write_agent_skill(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        textwrap.dedent(
            f"""\
            ---
            schema_version: "2.0"
            name: {name}
            description: {name}
            type: agent
            agent_profile:
              role: reviewer
              goal: review
            ---
            """
        ),
        encoding="utf-8",
    )


def _write_parent_skill(
    path: Path,
    *,
    subgraphs: list[str],
    reducer: str,
) -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            ---
            schema_version: "2.0"
            name: parent
            description: parent
            type: graph
            io:
              inputs: []
              outputs: []
            phases:
              - name: parallel_review
                mode: parallel_delegate
                subgraphs:
            """
        )
        + "".join(f"      - {subgraph}\n" for subgraph in subgraphs)
        + (
            "    context_bridge:\n"
            "      inputs: {}\n"
            "      outputs: {}\n"
            "    tolerance: 0.2\n"
            f"    reducer: {reducer}\n"
            "---\n"
        ),
        encoding="utf-8",
    )


def test_loader_resolves_parallel_delegate_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_agent_skill(tmp_path / "a" / "SKILL.md", "child_a")
    _write_agent_skill(tmp_path / "b" / "SKILL.md", "child_b")
    (tmp_path / "reducers.py").write_text(
        "def reduce_outputs(ctx, child_outputs, errors):\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    parent = tmp_path / "parent.md"
    _write_parent_skill(
        parent,
        subgraphs=["./a/SKILL.md", "./b/SKILL.md"],
        reducer="reducers.reduce_outputs",
    )

    harness = load_workflow_from_md(parent)

    phase = harness.phases[0]
    assert len(phase.parallel_subgraphs) == 2
    assert all(isinstance(child, GraphAgentHarness) for child in phase.parallel_subgraphs)
    assert phase.reducer_path == "reducers.reduce_outputs"
    assert phase.tolerance == 0.2
    assert phase.requires_llm is False


def test_loader_raises_when_subgraph_path_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_agent_skill(tmp_path / "a" / "SKILL.md", "child_a")
    (tmp_path / "reducers.py").write_text(
        "def reduce_outputs(ctx, child_outputs, errors):\n"
        "    return {}\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    parent = tmp_path / "parent.md"
    _write_parent_skill(
        parent,
        subgraphs=["./a/SKILL.md", "./missing/SKILL.md"],
        reducer="reducers.reduce_outputs",
    )

    with pytest.raises(SkillLoadError, match="subgraph not found"):
        load_workflow_from_md(parent)


def test_loader_raises_when_reducer_path_unimportable(tmp_path: Path) -> None:
    _write_agent_skill(tmp_path / "a" / "SKILL.md", "child_a")
    _write_agent_skill(tmp_path / "b" / "SKILL.md", "child_b")
    parent = tmp_path / "parent.md"
    _write_parent_skill(
        parent,
        subgraphs=["./a/SKILL.md", "./b/SKILL.md"],
        reducer="missing.module.fn",
    )

    with pytest.raises(SkillLoadError, match="cannot be imported"):
        load_workflow_from_md(parent)


def test_loader_raises_when_reducer_not_callable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_agent_skill(tmp_path / "a" / "SKILL.md", "child_a")
    _write_agent_skill(tmp_path / "b" / "SKILL.md", "child_b")
    (tmp_path / "not_callable_reducer.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    parent = tmp_path / "parent.md"
    _write_parent_skill(
        parent,
        subgraphs=["./a/SKILL.md", "./b/SKILL.md"],
        reducer="not_callable_reducer.VALUE",
    )

    with pytest.raises(SkillLoadError, match="is not callable"):
        load_workflow_from_md(parent)
