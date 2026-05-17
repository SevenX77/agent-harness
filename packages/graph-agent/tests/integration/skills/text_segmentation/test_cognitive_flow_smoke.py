"""V2.1 smoke tests for the live text-segmentation skill layout."""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import LogicNodeAST, SkillNodeAST

REPO_ROOT = Path(__file__).resolve().parents[6]
SKILL_ROOT = REPO_ROOT / "skills/text-segmentation"


def test_text_segmentation_compiles_from_v21_root() -> None:
    compiled = SkillLoader(validate_context_writes=False).compile_skill(SKILL_ROOT)

    assert [phase.id for phase in compiled.manifest.phases] == ["setup", "segment", "review"]
    assert {node.phase_name for node in compiled.nodes} == {"setup", "segment", "review"}


def test_text_segmentation_setup_action_is_discovered() -> None:
    compiled = SkillLoader(validate_context_writes=False).compile_skill(SKILL_ROOT)
    setup = next(node for node in compiled.nodes if node.phase_name == "setup")

    assert isinstance(setup.ast, LogicNodeAST)
    assert setup.ast.python_callable == "prepare_chapter"
    assert "prepare_chapter" in compiled.actions.for_phase("setup")
    assert (
        compiled.actions.for_phase("setup")["prepare_chapter"].path
        == SKILL_ROOT / "phases/setup/actions/prepare_chapter.py"
    )


def test_text_segmentation_review_documents_json_output_contract() -> None:
    compiled = SkillLoader(validate_context_writes=False).compile_skill(SKILL_ROOT)
    review = next(node for node in compiled.nodes if node.phase_name == "review")

    assert isinstance(review.ast, SkillNodeAST)
    assert "## segmentation_result" in review.ast.exit_contract
    assert "```json" in review.ast.exit_contract
