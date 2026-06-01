---
actions:
  - run_batch_loop
io:
  inputs:
    type: object
    required: [all_events, total_events, total_chapters]
    properties:
      all_events:
        type: array
        items:
          type: object
      total_events:
        type: integer
      total_chapters:
        type: integer
  outputs:
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
---
<action>run_batch_loop</action>
