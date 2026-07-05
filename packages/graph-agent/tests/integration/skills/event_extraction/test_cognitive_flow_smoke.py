"""Smoke tests for the legacy event-extraction corpus layout."""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.loader import CompiledSkill, SkillLoader
from graph_agent.core.manifest import AgentNodeAST, LogicNodeAST

from ....conftest import MockSkillResolver
from .._fixture_corpus import write_legacy_v21_corpus


def _compile_event_extraction(tmp_path: Path) -> tuple[CompiledSkill, Path]:
    corpus_root = write_legacy_v21_corpus(tmp_path)
    skill_root = corpus_root / "skills" / "event-extraction"
    compiled = SkillLoader(validate_context_writes=False).compile_skill(
        skill_root,
        skill_resolver=MockSkillResolver(corpus_root),
    )
    return compiled, skill_root


def test_event_extraction_compiles_from_legacy_v21_root(tmp_path: Path) -> None:
    compiled, _skill_root = _compile_event_extraction(tmp_path)

    assert list(compiled.manifest.phases) == [
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


def test_event_extraction_setup_action_is_discovered(tmp_path: Path) -> None:
    compiled, skill_root = _compile_event_extraction(tmp_path)
    setup = next(node for node in compiled.nodes if node.phase_name == "setup")

    assert isinstance(setup.ast, LogicNodeAST)
    assert setup.ast.actions == ["format_segments_for_prompt"]
    assert "format_segments_for_prompt" in compiled.actions.for_phase("setup")
    assert (
        compiled.actions.for_phase("setup")["format_segments_for_prompt"].path
        == skill_root / "phases/setup/actions/format_segments_for_prompt.py"
    )


def test_event_extraction_final_phase_documents_json_output_contract(tmp_path: Path) -> None:
    compiled, _skill_root = _compile_event_extraction(tmp_path)
    settings = next(node for node in compiled.nodes if node.phase_name == "settings")

    assert isinstance(settings.ast, AgentNodeAST)
    assert settings.ast.io is not None
    assert "event_timeline" in settings.ast.io.outputs.get("properties", {})
