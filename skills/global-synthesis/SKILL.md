---
name: global-synthesis
description: >
  Global analysis after all batches complete. Performs climax ranking,
  foreshadowing closure, character ranking, scene assembly, and retroactive correction.
  Use as final stage of story deconstruction pipeline.
type: graph
context_mapping:
  batch_outputs: "{input.batch_outputs}"
  accumulated_context: "{input.accumulated_context}"
  entity_registry: "{input.entity_registry}"
  total_batches: ""
  total_events: ""
  total_characters: ""
  inferred_events_count: ""
  climax_ranking: ""
  character_ranking: ""
  foreshadowing_closure: ""
  unified_event_stream: ""
  scenes: ""
  story_framework: ""
io:
  inputs:
    - name: batch_outputs
      type: list
      source: runtime
    - name: accumulated_context
      type: dict
      source: runtime
    - name: entity_registry
      type: dict
      source: runtime
  outputs:
    - name: story_framework
      type: dict
      target: artifact
---

<phase id="global_analysis">
<ref path="phases/01_global_analysis.md" />
</phase>

<phase id="scene_assembly" depends_on="global_analysis">
<ref path="phases/02_scene_assembly.md" />
</phase>

<phase id="retroactive" depends_on="scene_assembly">
<ref path="phases/03_retroactive.md" />
</phase>

<phase id="export" depends_on="retroactive">
<ref path="phases/04_export.md" />
</phase>
