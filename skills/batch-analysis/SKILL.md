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

<phase id="prepare">
<ref path="phases/01_prepare.md" />
</phase>

<phase id="entity_and_characters" depends_on="prepare">
<ref path="phases/02_entity_and_characters.md" />
</phase>

<phase id="parallel_analysis" depends_on="entity_and_characters">
<ref path="phases/03_parallel_analysis.md" />
</phase>

<phase id="continuity" depends_on="parallel_analysis">
<ref path="phases/04_continuity.md" />
</phase>

<phase id="assemble" depends_on="continuity">
<ref path="phases/05_assemble.md" />
</phase>
