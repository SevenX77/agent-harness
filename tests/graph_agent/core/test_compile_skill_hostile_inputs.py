"""Hostile-input regression tests for compile_skill exception aggregation.

Cohesion plan 方针 4 follow-up (2026-04-26): the ``compile_skill``
contract is "never raise — always aggregate diagnostics into
``CompileResult.issues``". These four tests cover the previously
exposed escape paths where an OS- or import-level error could
bypass that contract:

  - ``compiler.compile_skill`` reading SKILL.md
  - ``validators.context_bridge`` parsing a child SKILL.md
  - ``validators.persona_resolution`` resolving an ``adopted_persona``
  - ``validators.tool_paths`` checking a ``builtin.*`` reference via
    ``importlib.util.find_spec``
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from graph_agent.core.compiler import compile_skill
from graph_agent.core.manifest import GraphSkillDef, SkillManifest
from graph_agent.core.validators.context_bridge import check_context_bridge
from graph_agent.core.validators.persona_resolution import check_persona_resolution
from graph_agent.core.validators.tool_paths import check_tool_paths


def test_compile_skill_with_invalid_utf8_returns_fatal_not_raise(
    tmp_path: Path,
) -> None:
    """SKILL.md with invalid UTF-8 bytes must yield a FATAL issue, not raise."""
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_bytes(b"\xff\xfe\x00invalid utf-8 bytes\xc3\x28")

    result = compile_skill(skill_path)

    assert not result.passed
    fatals = result.fatals
    assert len(fatals) >= 1
    assert any(
        f.rule_id == "INTERNAL" and "Failed to read SKILL.md" in f.message
        for f in fatals
    )


def test_context_bridge_child_with_invalid_utf8_returns_fatal_not_raise(
    tmp_path: Path,
) -> None:
    """Child SKILL.md with invalid UTF-8 must surface as F-context-bridge-child-invalid."""
    child_path = tmp_path / "child.md"
    child_path.write_bytes(b"---\n\xff\xfe\x00\n---\n")

    parent_raw = {
        "schema_version": "2.0",
        "type": "graph",
        "name": "parent",
        "description": "parent for hostile child test",
        "io": {"inputs": [], "outputs": []},
        "phases": [
            {
                "name": "delegate_phase",
                "mode": "delegate",
                "subgraph": child_path.name,
                "context_bridge": {"inputs": {}, "outputs": {}},
            }
        ],
    }
    parent = TypeAdapter(SkillManifest).validate_python(parent_raw)
    assert isinstance(parent, GraphSkillDef)

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert any(
        i.rule_id == "F-context-bridge-child-invalid" for i in issues
    ), [(i.rule_id, i.message) for i in issues]


def test_compile_skill_with_invalid_utf8_child_returns_fatal_not_raise(
    tmp_path: Path,
) -> None:
    """compile_skill must aggregate invalid child UTF-8 across all validators."""
    child_path = tmp_path / "child.md"
    child_path.write_bytes(b"---\n\xff\xfe\x00\n---\n")
    parent_path = tmp_path / "SKILL.md"
    parent_path.write_text(
        """---
schema_version: "2.0"
type: graph
name: parent
description: parent for hostile child compile test
io:
  inputs: []
  outputs: []
phases:
  - name: delegate_phase
    mode: delegate
    subgraph: child.md
    context_bridge:
      inputs: {}
      outputs: {}
---
""",
        encoding="utf-8",
    )

    result = compile_skill(parent_path)

    assert not result.passed
    assert any(
        i.rule_id == "F-context-bridge-child-invalid"
        for i in result.fatals
    ), [(i.rule_id, i.message) for i in result.issues]


def test_persona_resolution_with_oserror_returns_fatal_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OSError from resolve_persona must be aggregated, not propagated."""
    from graph_agent.core.validators import persona_resolution as pr_module

    def _raise_os(*args: object, **kwargs: object) -> object:
        raise OSError("simulated unreadable persona file")

    monkeypatch.setattr(pr_module, "resolve_persona", _raise_os)

    agent_raw = {
        "schema_version": "2.0",
        "type": "agent",
        "name": "agent_under_test",
        "description": "agent for hostile persona test",
        "agent_profile": {"role": "tester", "goal": "be tested"},
        "adopted_persona": "broken_persona",
    }
    agent = TypeAdapter(SkillManifest).validate_python(agent_raw)

    issues = check_persona_resolution(agent, base_dir=tmp_path)

    assert any(
        i.rule_id == "F-persona-not-resolved"
        and "simulated unreadable persona file" in i.message
        for i in issues
    ), [(i.rule_id, i.message) for i in issues]


def test_tool_paths_builtin_oserror_returns_fatal_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OSError from importlib.util.find_spec must surface as F-tool-path-not-found."""
    from graph_agent.core.validators import tool_paths as tp_module

    def _raise_os(*args: object, **kwargs: object) -> object:
        raise OSError("simulated find_spec OSError")

    monkeypatch.setattr(tp_module.importlib.util, "find_spec", _raise_os)

    agent_raw = {
        "schema_version": "2.0",
        "type": "agent",
        "name": "agent_under_test",
        "description": "agent for hostile builtin tool test",
        "agent_profile": {"role": "tester", "goal": "be tested"},
        "agent_tools": ["builtin.broken_module.func"],
    }
    agent = TypeAdapter(SkillManifest).validate_python(agent_raw)

    issues = check_tool_paths(agent, base_dir=tmp_path)

    assert any(i.rule_id == "F-tool-path-not-found" for i in issues), [
        (i.rule_id, i.message) for i in issues
    ]
