"""V0.3 root guard rejects legacy schema-2.0 file entrypoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError


def test_legacy_schema_20_skill_file_is_not_compilable_v030_root(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    host_skill = tmp_path / "SKILL.md"
    host_skill.write_text(
        """---
schema_version: "2.0"
name: host
type: agent
legacy_marker: true
---
""",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError, match="expects a skill root directory"):
        compile_skill(host_skill, cache=False, skill_resolver=mock_skill_resolver)
