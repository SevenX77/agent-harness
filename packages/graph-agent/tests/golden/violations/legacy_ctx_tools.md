# 现役 schema 2.0 ctx-signature 违规清单 (T2.x 迁移 checklist)

## Framework builtin (T1.2b 不动, 全 codebase 重写时一并迁)

- `packages/graph-agent/src/graph_agent/tools/builtin/context_access.py:24` `query_working_memory(ctx, ...)`
- `packages/graph-agent/src/graph_agent/tools/builtin/context_access.py:32` `read_artifact(ctx, ...)`
- `packages/graph-agent/src/graph_agent/tools/builtin/read_file.py:58` `read_file(ctx, path)`

## _v2_pending out-of-scope tools (R0 pending 继续 pending)

- `skills/_v2_pending/adaptation_v1/tools/writer_dispatcher.py:9` `dispatch_writer_drafting(ctx, ...)`
- `skills/_v2_pending/adaptation_v1/tools/technical_io.py:7` `load_chapter_text(ctx, ...)`
- `skills/_v2_pending/adaptation_v1/tools/scene_builder.py:9` `build_objective_scenes(ctx, ...)`
- `skills/_v2_pending/adaptation_v1/tools/beat_dispatcher.py:19` `extract_beats_concurrently(ctx, ...)`
- `skills/_v2_pending/adaptation_v1/tools/producer_dispatcher.py:9` `dispatch_producer_strategy(ctx, ...)`
- `skills/_v2_pending/adaptation_v1/tools/save_tools.py:9` `save_beats(ctx, ...)`

## skills/*/script/*.py (T2.x 各 skill 迁移时分类: Action / Tool / 删)

### text-segmentation (6)

- `skills/text-segmentation/script/segmenter.py:20` `prepare_chapter(context, ...)`
- `skills/text-segmentation/script/segmenter.py:42` `parse_segmentation_output(raw_output, context, ...)`
- `skills/text-segmentation/script/segmenter.py:135` `store_segments(context, ...)`
- `skills/text-segmentation/script/segmenter.py:213` `log_ambiguous_segments(segment_index, reason, confidence, context, ...)`
- `skills/text-segmentation/script/segmenter.py:233` `detect_scene_breaks(content, context, ...)`
- `skills/text-segmentation/script/segmenter.py:275` `validate_segmentation(context, ...)`

### event-extraction (10)

- `skills/event-extraction/script/extractor.py:10` `format_segments_for_prompt(context, ...)`
- `skills/event-extraction/script/extractor.py:33` `parse_events(raw_output, context, ...)`
- `skills/event-extraction/script/extractor.py:107` `parse_paragraph_indices(text, context, ...)`
- `skills/event-extraction/script/extractor.py:144` `store_events(context, ...)`
- `skills/event-extraction/script/extractor.py:186` `backup_event_timeline(context, ...)`
- `skills/event-extraction/script/extractor.py:197` `safe_review_store_events(context, ...)`
- `skills/event-extraction/script/extractor.py:226` `parse_settings(raw_output, context, ...)`
- `skills/event-extraction/script/extractor.py:269` `merge_settings_into_events(context, ...)`
- `skills/event-extraction/script/extractor.py:315` `finalize_event_timeline(context, ...)`
- `skills/event-extraction/script/extractor.py:329` `log_ambiguous_events(event_id, reason, confidence, context, ...)`

### batch-analysis (18)

- `skills/batch-analysis/script/entity.py:9` `register_entity(name, entity_type, description, initial_state, context, ...)`
- `skills/batch-analysis/script/entity.py:44` `resolve_alias(alias, canonical_entity_id, context, ...)`
- `skills/batch-analysis/script/entity.py:56` `get_entity_registry_summary(context, ...)`
- `skills/batch-analysis/script/continuity.py:9` `check_continuity(context, ...)`
- `skills/batch-analysis/script/continuity.py:53` `log_continuity_warning(entity_id, field, expected, actual, context, ...)`
- `skills/batch-analysis/script/accumulator.py:13` `load_accumulated_state(context, ...)`
- `skills/batch-analysis/script/accumulator.py:41` `build_batch_context_text(context, ...)`
- `skills/batch-analysis/script/accumulator.py:65` `update_accumulator(context, ...)`
- `skills/batch-analysis/script/accumulator.py:134` `save_accumulated_state(context, ...)`
- `skills/batch-analysis/script/paths.py:21` `format_batch_events(context, ...)`
- `skills/batch-analysis/script/paths.py:38` `analyze_tension_emotion_vibe(context, ...)`
- `skills/batch-analysis/script/paths.py:60` `analyze_system_evolution(context, ...)`
- `skills/batch-analysis/script/paths.py:86` `analyze_character_changes(context, ...)`
- `skills/batch-analysis/script/paths.py:103` `analyze_prop_changes(context, ...)`
- `skills/batch-analysis/script/paths.py:120` `analyze_emotional_arcs(context, ...)`
- `skills/batch-analysis/script/paths.py:137` `analyze_foreshadowing(context, ...)`
- `skills/batch-analysis/script/paths.py:154` `analyze_spatiotemporal(context, ...)`
- `skills/batch-analysis/script/paths.py:171` `assemble_batch_results(context, ...)`

### batch-analysis validators (1)

- `skills/batch-analysis/script/validators.py:9` `validate_batch_analysis(ctx, ...)`

### global-synthesis (8)

- `skills/global-synthesis/script/synthesis.py:14` `rank_climaxes(context, ...)`
- `skills/global-synthesis/script/synthesis.py:54` `close_foreshadowing(context, ...)`
- `skills/global-synthesis/script/synthesis.py:95` `rank_characters(context, ...)`
- `skills/global-synthesis/script/scene_builder.py:13` `build_unified_event_stream(context, ...)`
- `skills/global-synthesis/script/scene_builder.py:90` `export_story_framework(context, ...)`
- `skills/global-synthesis/script/retroactive.py:22` `scan_anchor_points(context, ...)`
- `skills/global-synthesis/script/retroactive.py:68` `apply_corrections(context, ...)`
- `skills/global-synthesis/script/validators.py:12` `validate_global_synthesis(ctx, ...)`
