"""Loader-based smoke tests for the live V2.1 skills."""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.loader import CompiledSkill, SkillLoader
from graph_agent.core.manifest import AgentNodeAST, LogicNodeAST

from tests.conftest import MockSkillResolver

REPO_ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(scope="module")
def compiled_skills() -> dict[str, CompiledSkill]:
    resolver = MockSkillResolver(REPO_ROOT)
    skills = {}
    for skill_id in (
        "event-extraction",
        "batch-analysis",
        "text-segmentation",
        "global-synthesis",
        "story-deconstruction",
    ):
        try:
            skills[skill_id] = SkillLoader(validate_context_writes=False).compile_skill(
                REPO_ROOT / "skills" / skill_id,
                skill_resolver=resolver
            )
        except Exception as exc:
            class FailedMockCompiledSkill:
                def __init__(self, error):
                    self._error = error
                def __getattr__(self, name):
                    raise self._error
            skills[skill_id] = FailedMockCompiledSkill(exc)
    return skills


def test_all_live_skills_compile_from_v21_roots(
    compiled_skills: dict[str, CompiledSkill],
) -> None:
    assert set(compiled_skills) == {
        "event-extraction",
        "batch-analysis",
        "text-segmentation",
        "global-synthesis",
        "story-deconstruction",
    }
    for skill_id, compiled in compiled_skills.items():
        assert compiled.manifest.schema_version == "v0.3.0"
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
        ("text-segmentation", ["setup", "segment", "review"]),
        ("global-synthesis", ["global_analysis", "scene_assembly", "retroactive", "export"]),
        ("story-deconstruction", ["segmentation", "event_extraction", "batch_loop", "global_synthesis"]),
    ],
)
def test_live_skill_topology_matches_graph_md(
    compiled_skills: dict[str, CompiledSkill],
    skill_id: str,
    phase_ids: list[str],
) -> None:
    compiled = compiled_skills[skill_id]

    assert list(compiled.manifest.phases) == phase_ids
    assert {node.phase_name for node in compiled.nodes} == set(phase_ids)


@pytest.mark.parametrize(
    ("skill_id", "phase_id", "action_name", "relative_path"),
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
            "text-segmentation",
            "setup",
            "prepare_chapter",
            "phases/setup/actions/prepare_chapter.py",
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
            "story-deconstruction",
            "segmentation",
            "segment_all_chapters",
            "phases/segmentation/actions/segment_all_chapters.py",
        ),
        (
            "story-deconstruction",
            "event_extraction",
            "extract_all_events",
            "phases/event_extraction/actions/extract_all_events.py",
        ),
        (
            "story-deconstruction",
            "batch_loop",
            "run_batch_loop",
            "phases/batch_loop/actions/run_batch_loop.py",
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
    ("skill_id", "phase_id", "expected_output_property"),
    [
        ("event-extraction", "settings", "event_timeline"),
        ("batch-analysis", "continuity", "continuity_warnings"),
        ("text-segmentation", "review", "segmentation_result"),
        ("global-synthesis", "global_analysis", "climax_ranking"),
    ],
)
def test_final_skill_phases_document_output_contracts(
    compiled_skills: dict[str, CompiledSkill],
    skill_id: str,
    phase_id: str,
    expected_output_property: str,
) -> None:
    compiled = compiled_skills[skill_id]
    node = next(node for node in compiled.nodes if node.phase_name == phase_id)

    assert isinstance(node.ast, AgentNodeAST)
    assert node.ast.io is not None
    assert expected_output_property in node.ast.io.outputs.get("properties", {})

