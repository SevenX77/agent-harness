from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentError, SkillCompilationError, SkillLoadError


def test_skill_compilation_error_formats_structured_context() -> None:
    err = SkillCompilationError(
        "Invalid phase",
        skill_path=Path("GRAPH.md"),
        line=11,
        field_path="phases.0.id",
        suggestion="Provide a non-empty phase id.",
    )

    assert isinstance(err, GraphAgentError)
    assert str(err) == (
        "Invalid phase\n"
        "  at GRAPH.md:11\n"
        "  field: phases.0.id\n"
        "  suggestion: Provide a non-empty phase id."
    )


def test_compile_skill_file_path_is_rejected_for_v21(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: old\n---\n", encoding="utf-8")

    with pytest.raises(SkillLoadError, match="expects a skill root directory"):
        compile_skill(skill, cache=False)
