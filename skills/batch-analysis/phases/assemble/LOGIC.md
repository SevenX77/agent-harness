---
actions:
  - assemble_batch
io:
  inputs:
    type: object
    required: [batch_events, tension_results, system_results, character_results, prop_results, arc_results, foreshadowing_results, spatiotemporal_results, accumulator]
    properties:
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
      foreshadowing_results:
        type: array
      spatiotemporal_results:
        type: array
      accumulator:
        type: object
  outputs:
    type: object
    required: [batch_result, updated_accumulated]
    properties:
      batch_result:
        type: array
      updated_accumulated:
        type: object
---

<action>assemble_batch</action>
