---
schema_version: "v0.3.0"
name: story-analysis
description: Adaptive dimension discovery, event batching, then sequential batch analysis loop with cross-batch accumulated context.
io:
  inputs:
    type: object
    required: [global_timeline, segmentation_result]
    properties:
      global_timeline: {type: object}
      segmentation_result: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [batch_outputs, accumulated_context, entity_registry]
    properties:
      batch_outputs: {type: array, items: {type: object}}
      accumulated_context: {type: object}
      entity_registry: {type: object}
phases: [discover_dimensions, prepare_batches, analyze_batches, finalize]
---

<phase depends_on="input">discover_dimensions</phase>
<phase depends_on="discover_dimensions">prepare_batches</phase>
<phase depends_on="prepare_batches">analyze_batches</phase>
<phase depends_on="analyze_batches" output>finalize</phase>
