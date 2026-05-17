"""Unit tests for the persona_resolution validator."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.manifest import (
    SkillManifest,
)
from graph_agent.core.parser import parse_skill_file
from graph_agent.core.personas import PERSONA_PATH_ENV_VAR
from graph_agent.core.validators.persona_resolution import (
    check_persona_resolution,
)
from pydantic import TypeAdapter


def _write_persona_skill(parent_dir: Path, *, name: str) -> Path:
    """Stage a minimal valid PersonaSkillDef under parent_dir/subskills/<name>/SKILL.md."""
    persona_dir = parent_dir / "subskills" / name
    persona_dir.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: persona\n"
        f"name: {name}\n"
        f"description: persona {name} for resolution tests\n"
        "role_profile: |\n"
        "  Test persona for resolution.\n"
        "---\n"
    )
    path = persona_dir / "SKILL.md"
    path.write_text(body, encoding="utf-8")
    return path


def _write_agent_skill(
    parent_dir: Path,
    *,
    name: str,
    adopted_persona: str | None = None,
) -> Path:
    persona_line = f"adopted_persona: {adopted_persona}\n" if adopted_persona is not None else ""
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        f"name: {name}\n"
        f"description: agent {name}\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        f"{persona_line}"
        "---\n"
    )
    path = parent_dir / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _load(parent_path: Path):
    raw = parse_skill_file(parent_path)["frontmatter"]
    return TypeAdapter(SkillManifest).validate_python(raw)


def _write_graph_subskill(parent_dir: Path, *, name: str) -> Path:
    """Stage a graph skill where a persona is expected — for the wrong-type FATAL test."""
    sub_dir = parent_dir / "subskills" / name
    sub_dir.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        f"name: {name}\n"
        f"description: graph (not persona) named {name}\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        "  - name: only\n"
        "    mode: logic\n"
        "    execute_steps:\n"
        "      - graph_agent.callbacks.events.SubgraphEnterEvent\n"
        "---\n"
    )
    path = sub_dir / "SKILL.md"
    path.write_text(body, encoding="utf-8")
    return path


def _write_graph_with_llm_phase(
    parent_dir: Path,
    *,
    name: str,
    phase_name: str,
    adopted_persona: str | None = None,
) -> Path:
    persona_line = (
        f"    adopted_persona: {adopted_persona}\n" if adopted_persona is not None else ""
    )
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        f"name: {name}\n"
        f"description: graph {name}\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        f"  - name: {phase_name}\n"
        "    mode: llm\n"
        "    prompt: do the thing\n"
        f"{persona_line}"
        "---\n"
    )
    path = parent_dir / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_returns_empty_when_agent_persona_resolves(tmp_path: Path) -> None:
    _write_persona_skill(tmp_path, name="reviewer")
    agent_path = _write_agent_skill(
        tmp_path,
        name="my_agent",
        adopted_persona="reviewer",
    )

    manifest = _load(agent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert issues == []


def test_fatal_when_agent_persona_not_found(tmp_path: Path) -> None:
    agent_path = _write_agent_skill(
        tmp_path,
        name="my_agent",
        adopted_persona="missing",
    )

    manifest = _load(agent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "F-persona-not-resolved"
    assert issue.severity == "FATAL"
    assert "missing" in issue.message
    assert issue.location == "SKILL.md:adopted_persona"


def test_fatal_when_agent_persona_resolves_to_wrong_type(tmp_path: Path) -> None:
    _write_graph_subskill(tmp_path, name="not_a_persona")
    agent_path = _write_agent_skill(
        tmp_path,
        name="my_agent",
        adopted_persona="not_a_persona",
    )

    manifest = _load(agent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-persona-not-resolved"
    assert "not_a_persona" in issues[0].message
    assert "PersonaSkillDef" in issues[0].message


def test_returns_empty_when_llm_phase_persona_resolves(tmp_path: Path) -> None:
    _write_persona_skill(tmp_path, name="reviewer")
    parent_path = _write_graph_with_llm_phase(
        tmp_path,
        name="parent",
        phase_name="review_step",
        adopted_persona="reviewer",
    )

    manifest = _load(parent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert issues == []


def test_fatal_when_llm_phase_persona_not_found(tmp_path: Path) -> None:
    parent_path = _write_graph_with_llm_phase(
        tmp_path,
        name="parent",
        phase_name="review_step",
        adopted_persona="missing_persona",
    )

    manifest = _load(parent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "F-persona-not-resolved"
    assert "missing_persona" in issue.message
    assert issue.location == "SKILL.md:phases.review_step.adopted_persona"


def test_returns_empty_when_agent_has_no_persona(tmp_path: Path) -> None:
    agent_path = _write_agent_skill(tmp_path, name="my_agent", adopted_persona=None)

    manifest = _load(agent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert issues == []


def test_returns_empty_when_graph_has_no_llm_persona(tmp_path: Path) -> None:
    parent_path = _write_graph_with_llm_phase(
        tmp_path,
        name="parent",
        phase_name="step",
        adopted_persona=None,
    )

    manifest = _load(parent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert issues == []


def test_validator_resolves_via_env_var_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Validator must use the same default search paths as the loader."""
    base_dir = tmp_path / "skill_root"
    base_dir.mkdir()
    registry = tmp_path / "global_personas"
    registry_persona = registry / "external_reviewer"
    registry_persona.mkdir(parents=True)
    (registry_persona / "SKILL.md").write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: persona\n"
        "name: external_reviewer\n"
        "description: persona only reachable via env var\n"
        "role_profile: |\n"
        "  External reviewer persona.\n"
        "---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, str(registry))

    agent_path = _write_agent_skill(
        base_dir,
        name="my_agent",
        adopted_persona="external_reviewer",
    )
    raw = parse_skill_file(agent_path)["frontmatter"]
    manifest = TypeAdapter(SkillManifest).validate_python(raw)

    issues = check_persona_resolution(manifest, base_dir=base_dir)

    assert issues == []
