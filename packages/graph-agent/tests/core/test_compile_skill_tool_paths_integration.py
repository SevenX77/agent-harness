"""V2.1 compile facade rejects legacy agent tool-path SKILL.md files."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError


def test_compile_skill_rejects_legacy_agent_tool_path_file(tmp_path: Path) -> None:
    skill_file = tmp_path / "my_agent.md"
    skill_file.write_text(
        """---
schema_version: "2.0"
type: agent
name: my_agent
agent_tools:
  - missing_module.fn
---
""",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError, match="expects a skill root directory"):
        compile_skill(skill_file, cache=False)
