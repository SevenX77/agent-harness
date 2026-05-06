"""End-to-end: compile_skill on an agent with a missing adopted_persona surfaces F-persona-not-resolved."""
from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill


def test_compile_skill_propagates_persona_not_resolved(tmp_path: Path) -> None:
    agent_path = tmp_path / "my_agent.md"
    agent_path.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        "name: my_agent\n"
        "description: agent for persona resolution integration\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        "adopted_persona: nonexistent_persona\n"
        "---\n",
        encoding="utf-8",
    )

    result = compile_skill(agent_path)

    rule_ids = sorted(i.rule_id for i in result.fatals)
    assert "F-persona-not-resolved" in rule_ids
    assert result.passed is False
