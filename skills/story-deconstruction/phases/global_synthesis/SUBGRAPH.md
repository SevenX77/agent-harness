---
name: global_synthesis
path: subskills/global-synthesis
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
---
