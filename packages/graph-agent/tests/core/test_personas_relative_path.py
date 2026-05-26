"""V2.1 cutover tests for removed schema-2.0 persona resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader


def _write_legacy_persona(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """---
schema_version: "2.0"
name: p
description: legacy persona
type: persona
role_profile: legacy
---
""",
        encoding="utf-8",
    )


def test_root_persona_skill_file_is_rejected(tmp_path: Path, mock_skill_resolver: object) -> None:
    _write_legacy_persona(tmp_path / "SKILL.md")

    with pytest.raises(SkillLoadError, match="schema 2.0 root SKILL.md is not supported"):
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)


def test_subskills_persona_does_not_make_v21_root_valid(tmp_path: Path, mock_skill_resolver: object) -> None:
    _write_legacy_persona(tmp_path / "subskills" / "p" / "SKILL.md")

    with pytest.raises(SkillLoadError, match="missing required GRAPH.md"):
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)


def test_absolute_persona_file_path_is_not_a_v21_skill_root(tmp_path: Path, mock_skill_resolver: object) -> None:
    persona = tmp_path / "elsewhere" / "SKILL.md"
    _write_legacy_persona(persona)

    with pytest.raises(SkillLoadError, match="expects a skill root directory"):
        SkillLoader().compile_skill(persona, skill_resolver=mock_skill_resolver)
