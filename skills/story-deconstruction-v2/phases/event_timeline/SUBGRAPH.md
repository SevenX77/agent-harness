---
target_skill: event-timeline
validator: false
io:
  inputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [global_timeline]
    properties:
      global_timeline: {type: object}
---
