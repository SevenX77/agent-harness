"""Smoke tests for the legacy text-segmentation corpus layout."""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.loader import CompiledSkill, SkillLoader
from graph_agent.core.manifest import AgentNodeAST, LogicNodeAST

from ....conftest import MockSkillResolver
from .._fixture_corpus import write_legacy_v21_corpus


def _compile_text_segmentation(tmp_path: Path) -> tuple[CompiledSkill, Path]:
    corpus_root = write_legacy_v21_corpus(tmp_path)
    skill_root = corpus_root / "skills" / "text-segmentation"
    compiled = SkillLoader(validate_context_writes=False).compile_skill(
        skill_root,
        skill_resolver=MockSkillResolver(corpus_root),
    )
    return compiled, skill_root


def test_text_segmentation_compiles_from_legacy_v21_root(tmp_path: Path) -> None:
    compiled, _skill_root = _compile_text_segmentation(tmp_path)

    assert list(compiled.manifest.phases) == ["setup", "segment", "review"]
    assert {node.phase_name for node in compiled.nodes} == {"setup", "segment", "review"}


def test_text_segmentation_setup_action_is_discovered(tmp_path: Path) -> None:
    compiled, skill_root = _compile_text_segmentation(tmp_path)
    setup = next(node for node in compiled.nodes if node.phase_name == "setup")

    assert isinstance(setup.ast, LogicNodeAST)
    assert setup.ast.actions == ["prepare_chapter"]
    assert "prepare_chapter" in compiled.actions.for_phase("setup")
    assert (
        compiled.actions.for_phase("setup")["prepare_chapter"].path
        == skill_root / "phases/setup/actions/prepare_chapter.py"
    )


def test_text_segmentation_review_documents_json_output_contract(tmp_path: Path) -> None:
    compiled, _skill_root = _compile_text_segmentation(tmp_path)
    review = next(node for node in compiled.nodes if node.phase_name == "review")

    assert isinstance(review.ast, AgentNodeAST)
    assert review.ast.io is not None
    assert "segmentation_result" in review.ast.io.outputs.get("properties", {})
