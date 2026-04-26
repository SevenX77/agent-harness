"""Cohesion plan 方针 3.3 (2026-04-26): ``schema_version: 2.0``
(unquoted) is YAML-parsed as a float, and the previous
``frontmatter.get("schema_version").strip()`` call AttributeError'd
on the float — turning a perfectly authorable manifest into an opaque
Python crash. Both compile_skill (compiler.py) and load_workflow_from_md
(loader.py) must coerce the value to str before comparing, so the
manifest either parses cleanly (when it really is "2.0") or fails with
the documented F-schema-version fatal.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import load_workflow_from_md


def _write(path: Path, schema_version_literal: str) -> None:
    """Write a minimal SKILL.md with the given (unquoted) schema_version."""
    path.write_text(
        f"---\n"
        f"schema_version: {schema_version_literal}\n"
        "name: x\n"
        "description: x\n"
        "type: agent\n"
        "agent_profile:\n"
        "  role: r\n"
        "  goal: g\n"
        "---\n",
        encoding="utf-8",
    )


class TestCompilerSchemaVersionTolerance:
    def test_unquoted_2_0_parses_as_valid(self, tmp_path: Path) -> None:
        """When the YAML literal ``2.0`` parses as a float, the compiler
        must treat that as the supported version, not crash."""
        skill = tmp_path / "SKILL.md"
        _write(skill, "2.0")  # unquoted -> YAML float

        result = compile_skill(skill)
        assert result.passed, (
            "schema_version: 2.0 (unquoted) must compile cleanly — the "
            "value semantically *is* 2.0. Pre-fix the compiler crashed "
            "with AttributeError because float has no .strip(); fatals: "
            f"{[(f.rule_id, f.message) for f in result.fatals]}"
        )

    def test_unquoted_2_0_loads_as_valid(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        _write(skill, "2.0")
        # Should not raise SkillLoadError or AttributeError
        load_workflow_from_md(skill)


class TestCompilerSchemaVersionWrongFloat:
    def test_unquoted_1_5_fatals_cleanly(self, tmp_path: Path) -> None:
        """A wrong-version float must produce the documented
        F-schema-version fatal, not crash with AttributeError."""
        skill = tmp_path / "SKILL.md"
        _write(skill, "1.5")

        result = compile_skill(skill)
        assert not result.passed
        fatal_rules = [f.rule_id for f in result.fatals]
        assert "F-schema-version" in fatal_rules, (
            "Wrong-version float must yield F-schema-version, not a "
            f"Python exception. Got: {fatal_rules}"
        )

    def test_unquoted_1_5_loader_raises_skill_load_error(
        self, tmp_path: Path
    ) -> None:
        skill = tmp_path / "SKILL.md"
        _write(skill, "1.5")
        with pytest.raises(SkillLoadError):
            load_workflow_from_md(skill)
