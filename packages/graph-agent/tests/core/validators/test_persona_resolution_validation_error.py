"""V2.1 cutover rejects legacy persona frontmatter before persona resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError


def test_legacy_persona_frontmatter_file_is_not_compilable_v21_root(tmp_path: Path) -> None:
    host_skill = tmp_path / "SKILL.md"
    host_skill.write_text(
        """---
schema_version: "2.0"
name: host
type: agent
adopted_persona: broken_persona
---
""",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError, match="expects a skill root directory"):
        compile_skill(host_skill, cache=False)
