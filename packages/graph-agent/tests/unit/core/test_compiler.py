from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentError, SkillCompilationError


def test_skill_compilation_error_formats_structured_context() -> None:
    err = SkillCompilationError(
        "Invalid phase",
        skill_path=Path("SKILL.md"),
        line=11,
        field_path="phases.0.name",
        suggestion="Provide a non-empty phase name.",
    )

    assert isinstance(err, GraphAgentError)
    assert err.skill_path == Path("SKILL.md")
    assert err.line == 11
    assert err.field_path == "phases.0.name"
    assert err.suggestion == "Provide a non-empty phase name."
    assert str(err) == (
        "Invalid phase\n"
        "  at SKILL.md:11\n"
        "  field: phases.0.name\n"
        "  suggestion: Provide a non-empty phase name."
    )


def test_compile_skill_pydantic_issue_includes_field_path(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "name: bad\n"
        "description: x\n"
        "type: graph\n"
        "io:\n"
        "  inputs: []\n"
        "  outputs: []\n"
        "phases:\n"
        "  - mode: llm\n"
        '    name: ""\n'
        "    prompt: hi\n"
        "---\n",
        encoding="utf-8",
    )

    result = compile_skill(skill)

    assert not result.passed
    messages = "\n".join(issue.message for issue in result.fatals)
    assert f"at {skill}:" in messages
    assert "field:" in messages
    assert "phases.0" in messages
