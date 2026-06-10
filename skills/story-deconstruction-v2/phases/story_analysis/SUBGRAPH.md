---
target_skill: story-analysis
validator: false
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
---
