---
name: story-deconstruction
description: >
  Complete story deconstruction pipeline orchestrator. Segments chapters,
  extracts events, runs batch analysis with LLM-driven loop, then global synthesis.
  Use for full novel/screenplay analysis.
type: graph
context_mapping:
  chapters: "{input.chapters}"
  project_id: "{input.project_id}"
  all_segmentations: ""
  all_events: ""
  total_chapters: ""
  total_events: ""
  dynamic_dimensions: ""
  all_batch_results: ""
  accumulated_context: ""
  entity_registry: ""
  story_framework: ""
io:
  inputs:
    - name: chapters
      type: list
      source: runtime
    - name: project_id
      type: str
      source: runtime
  outputs:
    - name: story_framework
      type: dict
      target: artifact
---

<node id="segmentation">
<ref path="nodes/01_segmentation.md" />
</node>

<node id="event_extraction" depends_on="segmentation">
<ref path="nodes/02_event_extraction.md" />
</node>

<node id="batch_loop" depends_on="event_extraction">
<ref path="nodes/03_batch_loop.md" />
</node>

<node id="global_synthesis" depends_on="batch_loop">
<ref path="nodes/04_global_synthesis.md" />
</node>
