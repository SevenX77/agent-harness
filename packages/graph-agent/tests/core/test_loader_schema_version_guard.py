"""Regression: ``load_workflow_from_md`` must NOT silently return None
for SKILL.md files whose ``schema_version`` is not ``"2.0"``.

Pre-fix bug (2.3 in 2026-04-26 cohesion plan): the loader's outer
function had a single ``if frontmatter.get("schema_version") == "2.0"``
branch holding the entire build path. Anything else fell off the bottom
of the function and returned ``None``. ``runner.py`` then treated
``None`` as a valid harness handle and crashed with a ``NoneType has no
attribute 'run'`` later, miles away from the real cause (a typo'd
``schema_version`` like ``"2"`` or ``2.0`` floating-point parse).

Fixed contract: any non-``"2.0"`` ``schema_version`` raises
``SkillLoadError`` immediately at load time, with a message reusing the
``F-schema-version`` wording the compiler already produces, so callers
get a single clear failure mode.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import load_workflow_from_md


def _write_skill(path: Path, schema_version_literal: str) -> None:
    path.write_text(
        f"---\n"
        f"schema_version: {schema_version_literal}\n"
        'name: x\n'
        'description: x\n'
        'type: agent\n'
        'agent_profile:\n'
        '  role: r\n'
        '  goal: g\n'
        "---\n",
        encoding="utf-8",
    )


class TestSchemaVersionGuard:
    def test_unknown_schema_version_raises_skill_load_error(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        _write_skill(skill, '"1.5"')

        with pytest.raises(SkillLoadError) as excinfo:
            load_workflow_from_md(skill)

        msg = str(excinfo.value)
        assert "schema_version" in msg or "2.0" in msg, (
            "The error must mention schema_version / 2.0 so the author "
            "can fix the SKILL.md frontmatter; got "
            f"{msg!r}"
        )

    def test_missing_schema_version_raises_skill_load_error(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\n"
            "name: x\n"
            "description: x\n"
            "type: agent\n"
            "agent_profile:\n"
            "  role: r\n"
            "  goal: g\n"
            "---\n",
            encoding="utf-8",
        )

        with pytest.raises(SkillLoadError):
            load_workflow_from_md(skill)
