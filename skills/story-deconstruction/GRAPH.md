---
schema_version: "v0.3.0"
name: story-deconstruction
description: Complete story deconstruction pipeline orchestrator. Segments chapters, extracts events, runs batch analysis with LLM-driven loop, then global synthesis. Use for full novel/screenplay analysis.
io:
  inputs:
    type: object
    required: [chapters, project_id]
    properties:
      chapters:
        type: array
        items:
          type: object
      project_id:
        type: string
  outputs:
    type: object
    required: [story_framework]
    properties:
      story_framework:
        type: object
phases: [segmentation, event_extraction, batch_loop, global_synthesis]
---
<phase depends_on="input">segmentation</phase>
<phase depends_on="segmentation">event_extraction</phase>
<phase depends_on="event_extraction">batch_loop</phase>
<phase depends_on="batch_loop" output>global_synthesis</phase>
