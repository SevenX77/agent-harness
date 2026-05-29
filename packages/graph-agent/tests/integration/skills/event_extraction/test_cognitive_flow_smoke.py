"""Smoke tests for the legacy event-extraction root corpus layout."""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import AgentNodeAST, LogicNodeAST

REPO_ROOT = Path(__file__).resolve().parents[6]
SKILL_ROOT = REPO_ROOT / "skills/event-extraction"


def test_event_extraction_compiles_from_legacy_v21_root() -> None:
    compiled = SkillLoader(validate_context_writes=False).compile_skill(SKILL_ROOT)

    assert [phase.id for phase in compiled.manifest.phases] == [
        "setup",
        "aggregate",
        "review",
        "settings",
    ]
    assert {node.phase_name for node in compiled.nodes} == {
        "setup",
        "aggregate",
        "review",
        "settings",
    }


def test_event_extraction_setup_action_is_discovered() -> None:
    compiled = SkillLoader(validate_context_writes=False).compile_skill(SKILL_ROOT)
    setup = next(node for node in compiled.nodes if node.phase_name == "setup")

    assert isinstance(setup.ast, LogicNodeAST)
    assert setup.ast.actions == ["format_segments_for_prompt"]
    assert "format_segments_for_prompt" in compiled.actions.for_phase("setup")
    assert (
        compiled.actions.for_phase("setup")["format_segments_for_prompt"].path
        == SKILL_ROOT / "phases/setup/actions/format_segments_for_prompt.py"
    )


def test_event_extraction_final_phase_documents_json_output_contract() -> None:
    compiled = SkillLoader(validate_context_writes=False).compile_skill(SKILL_ROOT)
    settings = next(node for node in compiled.nodes if node.phase_name == "settings")

    assert isinstance(settings.ast, AgentNodeAST)
    assert "## event_timeline" in settings.ast.exit_contract
    assert "```json" in settings.ast.exit_contract
