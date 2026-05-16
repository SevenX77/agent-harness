---
schema_version: '2.1'
name: batch-analysis
description: 'Analyze a single batch (10 chapters) across 7 dimensions with entity
  registration and narrative continuity checking. Star topology: entity+character
  analysis runs first, other paths consume entity list. Use for each batch in story
  deconstruction pipeline.

  '
metadata:
  legacy_type: graph
  context_mapping:
    batch_events: '{input.batch_events}'
    accumulated_context: '{input.accumulated_context}'
    para_text_lookup: '{input.para_text_lookup}'
    dynamic_dimensions: '{input.dynamic_dimensions}'
    chapter_range: '{input.chapter_range}'
    batch_events_text: ''
    accumulated_context_text: ''
    batch_chapter_range: ''
    batch_event_count: ''
    dynamic_dimensions_hint: ''
    character_latest_states_text: ''
    batch_character_changes_text: ''
    tension_results: ''
    character_results: ''
    prop_results: ''
    arc_results: ''
    foreshadowing_results: ''
    spatiotemporal_results: ''
    system_results: ''
    entity_registry: ''
    batch_result: ''
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="prepare" src="phases/prepare" depends_on="" />
<phase id="entity_and_characters" src="phases/entity_and_characters" depends_on="prepare" />
<phase id="parallel_analysis" src="phases/parallel_analysis" depends_on="entity_and_characters" />
<phase id="continuity" src="phases/continuity" depends_on="parallel_analysis" />
<phase id="assemble" src="phases/assemble" depends_on="continuity" />
