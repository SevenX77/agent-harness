"""Tests for ``parse_skill_file`` — schema 2.0 parser entry (Task 0.3 Step 1).

Covers:
* Round-trip with ``serialize_skill``: dump a manifest, write to disk,
  parse back, validate, re-dump → byte-equal. This is the Studio UI ↔
  Git sync contract.
* Human body preservation: arbitrary markdown after the closing fence
  survives into ``human_body`` verbatim.
* Error paths: missing frontmatter, invalid YAML, non-dict frontmatter.

The parser deliberately does NOT perform semantic validation — that
belongs to ``SkillManifest.model_validate()``. These tests confirm
that separation of concerns by feeding the raw dict through Pydantic
*after* parse.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.manifest import SkillManifest
from graph_agent.core.parser import parse_skill_file
from graph_agent.core.serialize import serialize_skill

_SKILL_ADAPTER = TypeAdapter(SkillManifest)


class TestRoundTripWithSerialize:
    """serialize → write → parse_skill_file → validate → serialize == original."""

    def test_persona_round_trip(self, tmp_path):
        manifest_dict = {
            "name": "producer",
            "description": "Short-drama producer persona.",
            "type": "persona",
            "role_profile": (
                "You are a veteran short-drama producer.\n"
                "You focus on pacing and hooks.\n"
                "You are blunt but constructive."
            ),
            "few_shot_examples": [
                "Q: slow opening\nA: cut 30 seconds.",
            ],
        }
        m1 = _SKILL_ADAPTER.validate_python(manifest_dict)
        s1 = serialize_skill(m1)

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(s1, encoding="utf-8")

        parsed = parse_skill_file(skill_file)
        m2 = _SKILL_ADAPTER.validate_python(parsed["frontmatter"])
        s2 = serialize_skill(m2)

        assert s1 == s2

    def test_agent_round_trip(self, tmp_path):
        manifest_dict = {
            "name": "reviewer",
            "description": "Code reviewer agent.",
            "type": "agent",
            "agent_profile": {
                "role": "Senior reviewer",
                "goal": "Find defects.",
                "steps": ["Read diff", "Check invariants"],
            },
            "agent_tools": ["read_file", "grep_repo"],
            "adopted_persona": "producer",
        }
        m1 = _SKILL_ADAPTER.validate_python(manifest_dict)
        s1 = serialize_skill(m1)

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(s1, encoding="utf-8")

        parsed = parse_skill_file(skill_file)
        m2 = _SKILL_ADAPTER.validate_python(parsed["frontmatter"])
        assert serialize_skill(m2) == s1

    def test_graph_two_phase_modes_round_trip(self, tmp_path):
        """Round-trip with both supported modes (``logic`` + ``llm``).
        The 1.x ``delegate`` mode was removed in MVP-0 B1 (2026-04-28).
        """
        manifest_dict = {
            "name": "pipeline",
            "description": "Two-mode graph pipeline.",
            "type": "graph",
            "io": {
                "inputs": [{"name": "x", "source": "runtime"}],
                "outputs": [{"name": "y", "target": "artifact"}],
            },
            "phases": [
                {"mode": "logic", "name": "prep", "execute_steps": ["s.prep"]},
                {
                    "mode": "llm",
                    "name": "plan",
                    "prompt": "Line 1\nLine 2",
                    "agent_tools": ["t1"],
                },
            ],
        }
        m1 = _SKILL_ADAPTER.validate_python(manifest_dict)
        s1 = serialize_skill(m1)

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(s1, encoding="utf-8")

        parsed = parse_skill_file(skill_file)
        m2 = _SKILL_ADAPTER.validate_python(parsed["frontmatter"])
        assert serialize_skill(m2) == s1


class TestHumanBodyPreservation:
    def test_empty_body_when_no_trailing_content(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: x\ndescription: d\ntype: persona\nrole_profile: r\n---\n",
            encoding="utf-8",
        )
        parsed = parse_skill_file(skill_file)
        assert parsed["human_body"] == ""

    def test_body_preserved_verbatim(self, tmp_path):
        body_text = (
            "# Rationale\n"
            "This persona was chosen after PM review.\n"
            "\n"
            "## Changelog\n"
            "- 2026-04-20: initial draft\n"
            "- 2026-04-22: rubrics tightened\n"
        )
        content = (
            "---\n"
            "name: x\ndescription: d\ntype: persona\nrole_profile: r\n"
            "---\n"
            + body_text
        )
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(content, encoding="utf-8")

        parsed = parse_skill_file(skill_file)
        assert parsed["human_body"].strip() == body_text.strip()


class TestErrorPaths:
    def test_missing_frontmatter_raises(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Just a markdown file\n", encoding="utf-8")
        with pytest.raises(SkillLoadError):
            parse_skill_file(skill_file)

    def test_unclosed_frontmatter_raises(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\nname: x\ndescription: d\n", encoding="utf-8")
        with pytest.raises(SkillLoadError):
            parse_skill_file(skill_file)

    def test_invalid_yaml_raises(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: x\n  bad: indent: here\n---\n", encoding="utf-8"
        )
        with pytest.raises(SkillLoadError):
            parse_skill_file(skill_file)

    def test_non_dict_frontmatter_raises(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n- just\n- a\n- list\n---\n", encoding="utf-8"
        )
        with pytest.raises(SkillLoadError):
            parse_skill_file(skill_file)


class TestParserDoesNotValidate:
    """Separation of concerns: parser returns raw dict, Pydantic validates."""

    def test_invalid_manifest_not_flagged_by_parser(self, tmp_path):
        """``type: nonsense`` should pass parse but fail validate."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: x\ndescription: d\ntype: nonsense\n"
            "---\n",
            encoding="utf-8",
        )
        parsed = parse_skill_file(skill_file)
        # Parser accepts anything that's valid YAML.
        assert parsed["frontmatter"]["type"] == "nonsense"
        # But Pydantic rejects unknown discriminator value.
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _SKILL_ADAPTER.validate_python(parsed["frontmatter"])
