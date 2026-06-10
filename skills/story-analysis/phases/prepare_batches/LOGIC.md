---
io:
  inputs:
    type: object
    required: [global_timeline, segmentation_result]
    properties:
      global_timeline: {type: object}
      segmentation_result: {type: array, items: {type: object}}
      batch_size: {type: integer, default: 10}
  outputs:
    type: object
    required: [event_batches, para_text_lookup]
    properties:
      event_batches:
        type: array
        items:
          type: object
          required: [batch_index, chapter_range, events]
          properties:
            batch_index: {type: integer}
            chapter_range: {type: array, items: {type: integer}}
            events: {type: array, items: {type: object}}
      para_text_lookup: {type: object}
actions: [prepare_batches]
validator: false
---

<action>prepare_batches</action>
