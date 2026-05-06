"""Cohesion plan 方针 4.1 (2026-04-26): when a sub-persona file's
frontmatter is malformed, ``resolve_persona`` raises
``pydantic.ValidationError`` (not ``SkillLoadError``). The validator
only caught ``SkillLoadError``, so the ValidationError leaked through
``compile_skill`` and turned a graceful CompileResult into a hard
Python exception — breaking the aggregation contract.

The validator now catches both, so any persona resolution issue
(missing file, wrong type, malformed frontmatter) becomes a
``F-persona-not-resolved`` fatal in the CompileResult.
"""
from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill


def test_malformed_persona_frontmatter_yields_compile_fatal(tmp_path: Path) -> None:
    """A persona file whose frontmatter fails Pydantic validation
    must surface as a F-persona-not-resolved fatal, not a raw
    ValidationError out of compile_skill."""
    # Bare-name persona placed under ``<host>/subskills/<name>/SKILL.md``
    # (the skill-local convention used by ``resolve_persona``).
    bad_persona_dir = tmp_path / "subskills" / "broken_persona"
    bad_persona_dir.mkdir(parents=True)
    # Missing the required ``role_profile`` field (PersonaSkillDef
    # mandates min_length=1) — ValidationError, not SkillLoadError.
    (bad_persona_dir / "SKILL.md").write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "name: broken_persona\n"
        "description: persona without role_profile\n"
        "type: persona\n"
        "---\n",
        encoding="utf-8",
    )

    host_skill = tmp_path / "SKILL.md"
    host_skill.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "name: host\n"
        "description: agent referencing a malformed persona\n"
        "type: agent\n"
        "agent_profile:\n"
        "  role: r\n"
        "  goal: g\n"
        "adopted_persona: broken_persona\n"
        "---\n",
        encoding="utf-8",
    )

    # The cohesion-broken behavior is: compile_skill raises ValidationError
    # before reaching CompileResult. Post-fix: compile_skill returns a
    # CompileResult with one F-persona-not-resolved fatal.
    result = compile_skill(host_skill)
    assert not result.passed, (
        "Malformed persona frontmatter must produce a fatal, not a "
        "passing result."
    )
    rule_ids = [f.rule_id for f in result.fatals]
    assert "F-persona-not-resolved" in rule_ids, (
        "Persona resolution failures must aggregate as "
        f"F-persona-not-resolved; got {rule_ids}"
    )
