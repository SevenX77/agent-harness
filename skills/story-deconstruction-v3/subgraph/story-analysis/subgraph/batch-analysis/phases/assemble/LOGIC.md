---
actions:
  - assemble_batch
validator: false
io:
  inputs:
    type: object
    required: [current_batch, batch_events, tension_results, system_results, character_results, prop_results, arc_results, foreshadow_results, spatiotemporal_results, continuity_warnings, accumulator_state]
    properties:
      current_batch:
        type: object
      batch_events:
        type: array
      tension_results:
        type: array
      system_results:
        type: array
      character_results:
        type: array
      prop_results:
        type: array
      arc_results:
        type: array
      foreshadow_results:
        type: array
      spatiotemporal_results:
        type: array
      continuity_warnings:
        type: array
      accumulator_state:
        type: object
      entity_registry:
        type: object
      entity_aliases:
        type: object
  outputs:
    type: object
    required: [updated_state]
    properties:
      updated_state:
        type: object
---

<action>assemble_batch</action>
