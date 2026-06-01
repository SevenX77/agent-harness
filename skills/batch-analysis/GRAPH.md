---
schema_version: "v0.3.0"
name: batch-analysis
description: Analyze a single batch (10 chapters) across 7 dimensions with entity registration and narrative continuity checking.
io:
  inputs:
    type: object
    required: [batch_events, accumulated_context, para_text_lookup, dynamic_dimensions, chapter_range]
    properties:
      batch_events:
        type: array
        items:
          type: object
      accumulated_context:
        type: object
      para_text_lookup:
        type: object
      dynamic_dimensions:
        type: array
        items:
          type: string
      chapter_range:
        type: array
        items:
          type: integer
  outputs:
    type: object
    required: [batch_result, updated_accumulated]
    properties:
      batch_result:
        type: array
        items:
          type: object
      updated_accumulated:
        type: object
phases: [prepare, entity_and_characters, parallel_analysis, continuity, assemble]
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare">entity_and_characters</phase>
<phase depends_on="entity_and_characters">parallel_analysis</phase>
<phase depends_on="parallel_analysis">continuity</phase>
<phase depends_on="continuity" output>assemble</phase>
