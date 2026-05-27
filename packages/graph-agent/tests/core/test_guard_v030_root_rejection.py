"""V0.3 root guard tests for legacy schema-2.0 roots."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader


def _write_legacy_skill(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """---
schema_version: "2.0"
name: legacy
description: legacy root
type: agent
legacy_marker: true
---
""",
        encoding="utf-8",
    )


def test_schema_20_root_skill_file_is_rejected(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_legacy_skill(tmp_path / "SKILL.md")

    with pytest.raises(SkillLoadError, match="schema 2.0 root SKILL.md is not supported"):
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)


def test_subskill_skill_md_does_not_make_missing_graph_root_valid(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_legacy_skill(tmp_path / "subskills" / "legacy" / "SKILL.md")

    with pytest.raises(SkillLoadError, match="missing required GRAPH.md"):
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)


def test_absolute_skill_file_path_is_not_a_v030_skill_root(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    skill_file = tmp_path / "elsewhere" / "SKILL.md"
    _write_legacy_skill(skill_file)

    with pytest.raises(SkillLoadError, match="expects a skill root directory"):
        SkillLoader().compile_skill(skill_file, skill_resolver=mock_skill_resolver)
