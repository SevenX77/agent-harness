"""Unit tests for the persona_resolution validator."""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from graph_agent.core.manifest import (
    AgentSkillDef,
    GraphSkillDef,
    SkillManifest,
)
from graph_agent.core.parser import parse_skill_file
from graph_agent.core.validators.persona_resolution import (
    check_persona_resolution,
)


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
    parent_dir: Path, *, name: str, adopted_persona: str | None = None,
) -> Path:
    persona_line = (
        f"adopted_persona: {adopted_persona}\n"
        if adopted_persona is not None else ""
    )
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


def test_returns_empty_when_agent_persona_resolves(tmp_path: Path) -> None:
    _write_persona_skill(tmp_path, name="reviewer")
    agent_path = _write_agent_skill(
        tmp_path, name="my_agent", adopted_persona="reviewer",
    )

    manifest = _load(agent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert issues == []
