---
schema_version: "v0.3.0"
name: global-synthesis
description: Global analysis after all batches complete. Performs climax ranking, foreshadowing closure, character ranking, scene assembly, and retroactive correction.
io:
  inputs:
    type: object
    required: [batch_outputs, accumulated_context, entity_registry]
    properties:
      batch_outputs:
        type: array
        items:
          type: object
      accumulated_context:
        type: object
      entity_registry:
        type: object
  outputs:
    type: object
    required: [story_framework]
    properties:
      story_framework:
        type: object
phases: [global_analysis, scene_assembly, retroactive, export]
---
<phase depends_on="input">global_analysis</phase>
<phase depends_on="global_analysis">scene_assembly</phase>
<phase depends_on="scene_assembly">retroactive</phase>
<phase depends_on="retroactive" output>export</phase>
