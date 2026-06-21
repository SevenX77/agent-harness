---
io:
  inputs:
    type: object
    required: [analysis_state]
    properties:
      analysis_state: {type: object}
  outputs:
    type: object
    required: [batch_outputs, accumulated_context, entity_registry]
    properties:
      accumulated_context: {type: object}
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
