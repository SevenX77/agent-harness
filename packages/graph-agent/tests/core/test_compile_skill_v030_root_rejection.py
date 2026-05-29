"""V0.3 compile facade rejects file paths as skill roots."""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError


def test_compile_skill_rejects_legacy_schema_20_file_path(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    skill_file = tmp_path / "my_agent.md"
    skill_file.write_text(
        """---
schema_version: "2.0"
type: agent
name: my_agent
legacy_marker: true
---
""",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError, match="expects a skill root directory"):
        compile_skill(skill_file, cache=False, skill_resolver=mock_skill_resolver)
