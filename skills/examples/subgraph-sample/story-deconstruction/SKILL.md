---
name: story-deconstruction-subgraph
description: >
  Reference composition of the four-stage story deconstruction pipeline
  using `subgraph:` declarations. Each phase delegates to a self-contained
  sub-skill via context_bridge, with no Python glue code in between.
  Shipped as an example — Studio and new authors should start from this
  shape rather than the orchestrator.py-style dispatcher pattern kept in
  `skills/story-deconstruction/` for host-project continuity.
type: graph
schema_version: "2.0"
context_mapping:
  chapters: "{input.chapters}"
  project_id: "{input.project_id}"
  segmented_chapters: ""
  events_by_chapter: ""
  batch_outputs: ""
  accumulated_context: ""
  entity_registry: ""
  story_framework: ""
io:
  inputs:
    - name: chapters
      type: list
      source: runtime
      description: "Raw chapter list — each item has chapter_number + chapter_content."
    - name: project_id
      type: str
      source: runtime
      description: "Opaque project identifier used by the storage layer."
  outputs:
    - name: story_framework
      type: dict
      target: artifact_manager
      description: "Final composed story framework produced by global-synthesis."
---

<phase id="segmentation">
<phase_config>
name: segmentation
subgraph: ../../../text-segmentation/SKILL.md
context_bridge:
  inputs:
    chapters: "{context.chapters}"
  outputs:
    segmented_chapters: "{subgraph.segmentation_result}"
</phase_config>
</phase>

<phase id="event_extraction" depends_on="segmentation">
<phase_config>
name: event_extraction
subgraph: ../../../event-extraction/SKILL.md
context_bridge:
  inputs:
    segmentation_result: "{context.segmented_chapters}"
  outputs:
    events_by_chapter: "{subgraph.event_timeline}"
</phase_config>
</phase>

<phase id="batch_analysis" depends_on="event_extraction">
<phase_config>
name: batch_analysis
subgraph: ../../../batch-analysis/SKILL.md
context_bridge:
  inputs:
    batch_events: "{context.events_by_chapter}"
    accumulated_context: "{context.accumulated_context}"
  outputs:
    batch_outputs: "{subgraph.batch_result}"
    entity_registry: "{subgraph.entity_registry}"
</phase_config>
</phase>

<phase id="global_synthesis" depends_on="batch_analysis">
<phase_config>
name: global_synthesis
subgraph: ../../../global-synthesis/SKILL.md
context_bridge:
  inputs:
    batch_outputs: "{context.batch_outputs}"
    accumulated_context: "{context.accumulated_context}"
    entity_registry: "{context.entity_registry}"
  outputs:
    story_framework: "{subgraph.story_framework}"
</phase_config>
</phase>
