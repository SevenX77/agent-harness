---
io:
  inputs:
    type: object
    required: [accumulated_context, batch_outputs_raw, event_batches]
    properties:
      accumulated_context: {type: object}
      batch_outputs_raw:
        type: array
        items: {type: array, items: {type: object}}
      event_batches: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [entity_registry, batch_outputs]
    properties:
      entity_registry: {type: object}
      batch_outputs:
        type: array
        items:
          type: object
          required: [batch_index, chapter_range, events]
          properties:
            batch_index: {type: integer}
            chapter_range: {type: array, items: {type: integer}}
            events: {type: array, items: {type: object}}
actions: [finalize_outputs]
validator: false
---

<action>finalize_outputs</action>
