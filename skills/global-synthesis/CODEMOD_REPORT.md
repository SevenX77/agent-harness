# CODEMOD_REPORT

- source: `skills/global-synthesis/SKILL.md`
- written candidate files: 8
- initial review markers: 9
- remaining review markers: 0

## Manual decisions

- Global blackboard field flow is declared in `GRAPH.md` metadata `phase_io`.
- `global_analysis` and `retroactive` remain SKILL phases.
- `scene_assembly` and `export` remain LOGIC phases with one V2.1 Action each.
- Legacy `output_schema`, `llm_role`, retry, and validator fields were removed; terminal and intermediate fields are declared in `io/outputs.json`.
- `auditor` is a critic Tool convention in the retroactive phase.

## Script classification

- Actions: `build_scene_stream`, `export_story_framework`
- Tools: none
- Critic: `auditor`
- Removed as schema 2.0 ctx tools or superseded by Actions/finish_task: `rank_climaxes`, `close_foreshadowing`, `rank_characters`, `build_unified_event_stream`, `scan_anchor_points`, `apply_corrections`, `validate_global_synthesis`
