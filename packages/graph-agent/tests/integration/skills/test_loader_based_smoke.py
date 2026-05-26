"""Loader-based smoke tests for the live V2.1 skills."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.loader import CompiledSkill, SkillLoader
from graph_agent.core.manifest import AgentNodeAST, LogicNodeAST

pytest.skip(
    "by-design: V1 layout skill awaiting user V2.1 cutover (Phase 1 baseline)",
    allow_module_level=True,
)

REPO_ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(scope="module")
def compiled_skills() -> dict[str, CompiledSkill]:
    return {
        skill_id: SkillLoader(validate_context_writes=False).compile_skill(
            REPO_ROOT / "skills" / skill_id
        )
        for skill_id in (
            "event-extraction",
            "batch-analysis",
            "global-synthesis",
            "text-segmentation",
        )
    }


def test_all_live_skills_compile_from_v21_roots(
    compiled_skills: dict[str, CompiledSkill],
) -> None:
    assert set(compiled_skills) == {
        "event-extraction",
        "batch-analysis",
        "global-synthesis",
        "text-segmentation",
    }
    for skill_id, compiled in compiled_skills.items():
        assert compiled.manifest.schema_version == "2.1"
        assert compiled.manifest.name
        assert compiled.nodes, skill_id
        assert all(
            not node.path.name == "SKILL.md" or "phases" in node.path.parts
            for node in compiled.nodes
        )


@pytest.mark.parametrize(
    ("skill_id", "phase_ids"),
    [
        ("event-extraction", ["setup", "aggregate", "review", "settings"]),
        (
            "batch-analysis",
            ["prepare", "entity_and_characters", "parallel_analysis", "continuity", "assemble"],
        ),
        ("global-synthesis", ["global_analysis", "scene_assembly", "retroactive", "export"]),
        ("text-segmentation", ["setup", "segment", "review"]),
    ],
)
def test_live_skill_topology_matches_graph_md(
    compiled_skills: dict[str, CompiledSkill],
    skill_id: str,
    phase_ids: list[str],
) -> None:
    compiled = compiled_skills[skill_id]

    assert [phase.id for phase in compiled.manifest.phases] == phase_ids
    assert {node.phase_name for node in compiled.nodes} == set(phase_ids)


@pytest.mark.parametrize(
    ("skill_id", "phase_id", "callable_name", "relative_path"),
    [
        (
            "event-extraction",
            "setup",
            "format_segments_for_prompt",
            "phases/setup/actions/format_segments_for_prompt.py",
        ),
        ("batch-analysis", "prepare", "prepare_batch", "phases/prepare/actions/prepare_batch.py"),
        (
            "batch-analysis",
            "assemble",
            "assemble_batch",
            "phases/assemble/actions/assemble_batch.py",
        ),
        (
            "global-synthesis",
            "scene_assembly",
            "build_scene_stream",
            "phases/scene_assembly/actions/build_scene_stream.py",
        ),
        (
            "global-synthesis",
            "export",
            "export_story_framework",
            "phases/export/actions/export_story_framework.py",
        ),
        (
            "text-segmentation",
            "setup",
            "prepare_chapter",
            "phases/setup/actions/prepare_chapter.py",
        ),
    ],
)
def test_logic_actions_are_discovered_from_v21_phase_dirs(
    compiled_skills: dict[str, CompiledSkill],
    skill_id: str,
    phase_id: str,
    action_name: str,
    relative_path: str,
) -> None:
    compiled = compiled_skills[skill_id]
    node = next(node for node in compiled.nodes if node.phase_name == phase_id)

    assert isinstance(node.ast, LogicNodeAST)
    assert node.ast.actions == [action_name]
    assert action_name in compiled.actions.for_phase(phase_id)
    assert compiled.actions.for_phase(phase_id)[action_name].path == (
        REPO_ROOT / "skills" / skill_id / relative_path
    )


@pytest.mark.parametrize(
    ("skill_id", "phase_id", "required_exit_text"),
    [
        ("event-extraction", "settings", "## event_timeline"),
        ("batch-analysis", "continuity", "## continuity_warnings"),
        ("global-synthesis", "retroactive", "## retroactive_corrections"),
        ("text-segmentation", "review", "## segmentation_result"),
    ],
)
def test_final_skill_phases_document_output_contracts(
    compiled_skills: dict[str, CompiledSkill],
    skill_id: str,
    phase_id: str,
    required_exit_text: str,
) -> None:
    compiled = compiled_skills[skill_id]
    node = next(node for node in compiled.nodes if node.phase_name == phase_id)

    assert isinstance(node.ast, AgentNodeAST)
    assert required_exit_text in node.ast.exit_contract
