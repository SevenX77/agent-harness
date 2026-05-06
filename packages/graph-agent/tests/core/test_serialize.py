"""Round-trip idempotency tests for ``serialize_skill`` (Studio Phase 0 Task 0.2).

Without the parser (Task 0.3) these tests manually reconstruct the
round-trip cycle: a Pydantic model is dumped, the YAML frontmatter is
stripped out of the resulting string, re-loaded via ``yaml.safe_load``,
re-validated through the ``SkillManifest`` adapter, and dumped again.
The assertion is byte-for-byte equality of the two dumps — that's what
Studio UI ↔ Git sync relies on.
"""

from __future__ import annotations

import pytest
import yaml
from graph_agent.core.manifest import SkillManifest
from graph_agent.core.serialize import serialize_skill
from pydantic import TypeAdapter

_SKILL_ADAPTER = TypeAdapter(SkillManifest)


def _round_trip(manifest_dict: dict) -> tuple[str, str]:
    """Validate → serialise → strip frontmatter → load → validate → serialise.

    Returns the two serialised strings; callers assert equality.
    """
    m1 = _SKILL_ADAPTER.validate_python(manifest_dict)
    s1 = serialize_skill(m1)

    # Strip the leading/trailing "---" fences to recover just the YAML.
    assert s1.startswith("---\n")
    assert s1.rstrip().endswith("---")
    yaml_only = s1.split("---\n", 1)[1].rsplit("---", 1)[0]
    reloaded = yaml.safe_load(yaml_only)

    m2 = _SKILL_ADAPTER.validate_python(reloaded)
    s2 = serialize_skill(m2)
    return s1, s2


# =============================================================================
# Frontmatter structure & fences
# =============================================================================


class TestFrontmatterShape:
    def test_output_is_fenced_yaml(self):
        m = _SKILL_ADAPTER.validate_python({
            "name": "x",
            "description": "d",
            "type": "persona",
            "role_profile": "You are X.",
        })
        out = serialize_skill(m)
        assert out.startswith("---\n")
        assert out.rstrip().endswith("---")

    def test_output_ends_with_newline(self):
        m = _SKILL_ADAPTER.validate_python({
            "name": "x",
            "description": "d",
            "type": "persona",
            "role_profile": "You are X.",
        })
        out = serialize_skill(m)
        assert out.endswith("\n")


# =============================================================================
# Round-trip idempotency per artifact type
# =============================================================================


class TestRoundTripAgent:
    def test_minimal_agent_round_trip(self):
        s1, s2 = _round_trip({
            "name": "reviewer",
            "description": "A code reviewer agent.",
            "type": "agent",
            "agent_profile": {
                "role": "Senior reviewer",
                "goal": "Find defects and propose fixes.",
                "steps": ["Read diff", "Check invariants"],
                "constraints": ["No speculative refactors."],
            },
        })
        assert s1 == s2

    def test_agent_with_tools_and_persona(self):
        s1, s2 = _round_trip({
            "name": "plan-reviewer",
            "description": "An agent that reviews plans with producer persona.",
            "type": "agent",
            "agent_profile": {
                "role": "Plan reviewer",
                "goal": "Validate plan feasibility.",
            },
            "agent_tools": ["read_plan", "write_review"],
            "adopted_persona": "producer",
        })
        assert s1 == s2


class TestRoundTripGraph:
    def test_graph_with_two_phase_modes(self):
        """Cover LLM + Logic phases in one manifest. The 1.x ``delegate``
        mode was removed in MVP-0 B1 (2026-04-28)."""
        s1, s2 = _round_trip({
            "name": "complex-pipeline",
            "description": "A graph skill exercising both phase modes.",
            "type": "graph",
            "io": {
                "inputs": [{"name": "chapters", "source": "runtime", "type": "list[str]"}],
                "outputs": [{"name": "segments", "target": "artifact"}],
            },
            "phases": [
                {
                    "mode": "logic",
                    "name": "setup",
                    "execute_steps": ["script.prepare"],
                },
                {
                    "mode": "llm",
                    "name": "segment",
                    "prompt": "Break the chapter into beats.",
                    "agent_tools": ["read_chapter", "store_beat"],
                    "max_iterations": 10,
                    "adopted_persona": "producer",
                },
            ],
        })
        assert s1 == s2


class TestRoundTripPersona:
    def test_persona_with_multiline_profile(self):
        s1, s2 = _round_trip({
            "name": "producer",
            "description": "Short-drama producer persona.",
            "type": "persona",
            "role_profile": (
                "You are a veteran short-drama producer.\n"
                "You focus on pacing, character arcs, and audience hooks.\n"
                "You are blunt but constructive."
            ),
            "evaluation_rubrics": (
                "- Opening hook within 15 seconds\n"
                "- Character arc clarity\n"
                "- Commercial viability"
            ),
            "few_shot_examples": [
                "Input: slow opening\nOutput: Cut 30 seconds, lead with conflict.",
                "Input: exposition dump\nOutput: Show, don't tell — dramatise the backstory.",
            ],
        })
        assert s1 == s2


# =============================================================================
# Block Scalar behaviour for multiline strings
# =============================================================================


class TestBlockScalarStyle:
    def test_multiline_string_becomes_block_scalar(self):
        m = _SKILL_ADAPTER.validate_python({
            "name": "x",
            "description": "d",
            "type": "persona",
            "role_profile": "line one\nline two\nline three",
        })
        out = serialize_skill(m)
        # Literal block scalar marker must appear; plain-string
        # serialisation would instead emit quoted escapes.
        assert "role_profile: |" in out
        assert "line one" in out
        assert "\\n" not in out  # no escaped newlines

    def test_single_line_string_not_block_scalar(self):
        m = _SKILL_ADAPTER.validate_python({
            "name": "x",
            "description": "d",
            "type": "persona",
            "role_profile": "Short one-liner.",
        })
        out = serialize_skill(m)
        assert "role_profile: |" not in out
        assert "role_profile: Short one-liner." in out

    def test_multiline_few_shot_items_block_scalar(self):
        m = _SKILL_ADAPTER.validate_python({
            "name": "x",
            "description": "d",
            "type": "persona",
            "role_profile": "x",
            "few_shot_examples": [
                "Q: question one\nA: answer one.",
                "Short example.",
            ],
        })
        out = serialize_skill(m)
        # List item with newline → block scalar
        assert "- |" in out
        # Single-line item stays inline
        assert "- Short example." in out


# =============================================================================
# Field ordering & dict preservation
# =============================================================================


class TestFieldOrderingAndDicts:
    def test_field_order_matches_pydantic_declaration(self):
        """``sort_keys=False`` must preserve ``name`` before ``description`` etc."""
        m = _SKILL_ADAPTER.validate_python({
            "name": "ordered",
            "description": "d",
            "type": "persona",
            "role_profile": "r",
        })
        out = serialize_skill(m)
        name_idx = out.find("name:")
        desc_idx = out.find("description:")
        type_idx = out.find("type:")
        assert 0 < name_idx < desc_idx < type_idx

    def test_io_nested_dict_preserved(self):
        """Block-style nested dict survives round-trip. Original test used
        DelegatePhase.context_bridge; with delegate mode removed in MVP-0
        B1 (2026-04-28), exercise the analogous structure on
        ``io.inputs`` / ``io.outputs`` instead."""
        s1, s2 = _round_trip({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {
                "inputs": [
                    {"name": "a", "source": "runtime", "type": "str"},
                    {"name": "b", "source": "runtime", "type": "str"},
                ],
                "outputs": [
                    {"name": "c", "target": "artifact", "type": "str"},
                ],
            },
            "phases": [{
                "mode": "logic",
                "name": "only",
                "execute_steps": ["m.fn"],
            }],
        })
        assert s1 == s2
        assert "inputs:\n" in s1
        assert "outputs:\n" in s1
        assert "inputs: {" not in s1
        assert "outputs: {" not in s1


# =============================================================================
# None / empty-collection handling
# =============================================================================


class TestNoneExclusion:
    def test_none_fields_are_excluded(self):
        """exclude_none=True keeps output tight; default ``None`` fields omitted."""
        m = _SKILL_ADAPTER.validate_python({
            "name": "x",
            "description": "d",
            "type": "persona",
            "role_profile": "r",
        })
        out = serialize_skill(m)
        # evaluation_rubrics / license / version / author / metadata all None.
        # Match with leading newline to avoid hitting ``schema_version:``.
        assert "evaluation_rubrics:" not in out
        assert "\nlicense:" not in out
        assert "\nversion:" not in out
        assert "\nauthor:" not in out
        assert "\nmetadata:" not in out


# =============================================================================
# Type-safety of the callable
# =============================================================================


class TestCallableContract:
    def test_non_pydantic_input_rejected(self):
        with pytest.raises(TypeError):
            serialize_skill({"not": "a model"})  # type: ignore[arg-type]
