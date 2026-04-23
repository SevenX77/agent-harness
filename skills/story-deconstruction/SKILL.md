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

<phase id="segmentation">
<ref path="phases/01_segmentation.md" />
</phase>

<phase id="event_extraction" depends_on="segmentation">
<ref path="phases/02_event_extraction.md" />
</phase>

<phase id="batch_loop" depends_on="event_extraction">
<ref path="phases/03_batch_loop.md" />
</phase>

<phase id="global_synthesis" depends_on="batch_loop">
<ref path="phases/04_global_synthesis.md" />
</phase>
