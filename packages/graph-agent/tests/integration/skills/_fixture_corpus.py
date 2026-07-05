from __future__ import annotations

from pathlib import Path


def write_legacy_v21_corpus(root: Path) -> Path:
    """Write the minimal legacy corpus the loader smoke tests exercise."""
    skills_root = root / "skills"
    _write_event_extraction(skills_root / "event-extraction")
    _write_batch_analysis(skills_root / "batch-analysis")
    _write_text_segmentation(skills_root / "text-segmentation")
    _write_global_synthesis(skills_root / "global-synthesis")
    _write_story_deconstruction(skills_root / "story-deconstruction")
    return root


def _write_event_extraction(root: Path) -> None:
    _write_graph(root, "event-extraction", ["setup", "aggregate", "review", "settings"])
    _write_logic(root, "setup", "format_segments_for_prompt")
    _write_agent(root, "aggregate", "events")
    _write_agent(root, "review", "reviewed_events")
    _write_agent(root, "settings", "event_timeline")


def _write_batch_analysis(root: Path) -> None:
    _write_graph(
        root,
        "batch-analysis",
        ["prepare", "entity_and_characters", "parallel_analysis", "continuity", "assemble"],
    )
    _write_logic(root, "prepare", "prepare_batch")
    _write_agent(root, "entity_and_characters", "entities")
    _write_agent(root, "parallel_analysis", "analysis")
    _write_agent(root, "continuity", "continuity_warnings")
    _write_logic(root, "assemble", "assemble_batch")


def _write_text_segmentation(root: Path) -> None:
    _write_graph(root, "text-segmentation", ["setup", "segment", "review"])
    _write_logic(root, "setup", "prepare_chapter")
    _write_agent(root, "segment", "segments_summary")
    _write_agent(root, "review", "segmentation_result")


def _write_global_synthesis(root: Path) -> None:
    _write_graph(root, "global-synthesis", ["global_analysis", "scene_assembly", "retroactive", "export"])
    _write_agent(root, "global_analysis", "climax_ranking")
    _write_logic(root, "scene_assembly", "build_scene_stream")
    _write_agent(root, "retroactive", "retroactive_notes")
    _write_logic(root, "export", "export_story_framework")


def _write_story_deconstruction(root: Path) -> None:
    _write_graph(root, "story-deconstruction", ["segmentation", "event_extraction", "batch_loop", "global_synthesis"])
    _write_logic(root, "segmentation", "segment_all_chapters")
    _write_logic(root, "event_extraction", "extract_all_events")
    _write_logic(root, "batch_loop", "run_batch_loop")
    _write_subgraph(root, "global_synthesis", "subskills/global-synthesis")
    _write_global_synthesis(root / "subskills" / "global-synthesis")


def _write_graph(root: Path, name: str, phases: list[str]) -> None:
    phase_list = ", ".join(phases)
    phase_body = "\n".join(
        f'<phase depends_on="{_phase_dependency(index, phases)}"{_output_flag(index, phases)}>{phase}</phase>'
        for index, phase in enumerate(phases)
    )
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: {name}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases: [{phase_list}]
---
{phase_body}
""",
    )


def _phase_dependency(index: int, phases: list[str]) -> str:
    if index == 0:
        return "input"
    return phases[index - 1]


def _output_flag(index: int, phases: list[str]) -> str:
    if index == len(phases) - 1:
        return " output"
    return ""


def _write_logic(root: Path, phase: str, action_name: str) -> None:
    _write(
        root / "phases" / phase / "LOGIC.md",
        f"""---
actions:
  - {action_name}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
---
<action>{action_name}</action>
""",
    )
    _write(
        root / "phases" / phase / "actions" / f"{action_name}.py",
        f"""def {action_name}(inputs):
    return dict(inputs or {{}})
""",
    )


def _write_agent(root: Path, phase: str, output_property: str) -> None:
    _write(
        root / "phases" / phase / "SKILL.md",
        f"""---
llm_role: analyst
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties:
      {output_property}:
        type: object
tools:
  - finish_task
---
<role>
Fixture analyst.
</role>
<goal>
Produce the {output_property} output.
</goal>
<step id="S1" name="finish">
Call finish_task with the requested output.
</step>
""",
    )


def _write_subgraph(root: Path, phase: str, relative_path: str) -> None:
    _write(
        root / "phases" / phase / "SUBGRAPH.md",
        f"""---
name: {phase}
path: {relative_path}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
---
""",
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
