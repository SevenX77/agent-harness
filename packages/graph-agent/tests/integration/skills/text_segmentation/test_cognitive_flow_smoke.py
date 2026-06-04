"""Smoke tests for the legacy text-segmentation root corpus layout."""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import AgentNodeAST, LogicNodeAST
from tests.conftest import MockSkillResolver

REPO_ROOT = Path(__file__).resolve().parents[6]
SKILL_ROOT = REPO_ROOT / "skills/text-segmentation"


def test_text_segmentation_compiles_from_legacy_v21_root() -> None:
    compiled = SkillLoader(validate_context_writes=False).compile_skill(
        SKILL_ROOT, skill_resolver=MockSkillResolver(REPO_ROOT)
    )

    assert list(compiled.manifest.phases) == ["setup", "segment", "review"]
    assert {node.phase_name for node in compiled.nodes} == {"setup", "segment", "review"}


def test_text_segmentation_setup_action_is_discovered() -> None:
    compiled = SkillLoader(validate_context_writes=False).compile_skill(
        SKILL_ROOT, skill_resolver=MockSkillResolver(REPO_ROOT)
    )
    setup = next(node for node in compiled.nodes if node.phase_name == "setup")

    assert isinstance(setup.ast, LogicNodeAST)
    assert setup.ast.actions == ["prepare_chapter"]
    assert "prepare_chapter" in compiled.actions.for_phase("setup")
    assert (
        compiled.actions.for_phase("setup")["prepare_chapter"].path
        == SKILL_ROOT / "phases/setup/actions/prepare_chapter.py"
    )


def test_text_segmentation_review_documents_json_output_contract() -> None:
    compiled = SkillLoader(validate_context_writes=False).compile_skill(
        SKILL_ROOT, skill_resolver=MockSkillResolver(REPO_ROOT)
    )
    review = next(node for node in compiled.nodes if node.phase_name == "review")

    assert isinstance(review.ast, AgentNodeAST)
    assert review.ast.io is not None
    assert "segmentation_result" in review.ast.io.outputs.get("properties", {})
