---
name: batch-analysis
description: >
  Analyze a single batch (10 chapters) across 7 dimensions with entity registration
  and narrative continuity checking. Star topology: entity+character analysis runs first,
  other paths consume entity list. Use for each batch in story deconstruction pipeline.
type: graph
context_mapping:
  batch_events: "{input.batch_events}"
  accumulated_context: "{input.accumulated_context}"
  para_text_lookup: "{input.para_text_lookup}"
  dynamic_dimensions: "{input.dynamic_dimensions}"
  chapter_range: "{input.chapter_range}"
  batch_events_text: ""
  accumulated_context_text: ""
  batch_chapter_range: ""
  batch_event_count: ""
  dynamic_dimensions_hint: ""
  character_latest_states_text: ""
  batch_character_changes_text: ""
  tension_results: ""
  character_results: ""
  prop_results: ""
  arc_results: ""
  foreshadowing_results: ""
  spatiotemporal_results: ""
  system_results: ""
  entity_registry: ""
  batch_result: ""
io:
  inputs:
    - name: batch_events
      type: list
      source: runtime
    - name: accumulated_context
      type: dict
      source: runtime
    - name: para_text_lookup
      type: dict
      source: runtime
    - name: dynamic_dimensions
      type: list
      source: runtime
    - name: chapter_range
      type: list
      source: runtime
  outputs:
    - name: batch_result
      type: dict
      target: artifact
    - name: updated_accumulated
      type: dict
      target: artifact
---

<node id="prepare">
<ref path="nodes/01_prepare.md" />
</node>

<node id="entity_and_characters" depends_on="prepare">
<ref path="nodes/02_entity_and_characters.md" />
</node>

<node id="parallel_analysis" depends_on="entity_and_characters">
<ref path="nodes/03_parallel_analysis.md" />
</node>

<node id="continuity" depends_on="parallel_analysis">
<ref path="nodes/04_continuity.md" />
</node>

<node id="assemble" depends_on="continuity">
<ref path="nodes/05_assemble.md" />
</node>
