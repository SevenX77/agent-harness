---
actions:
  - build_scene_stream
io:
  inputs:
    type: object
    required: [batch_outputs]
    properties:
      batch_outputs:
        type: array
  outputs:
    type: object
    required: [scenes, unified_event_stream]
    properties:
      scenes:
        type: array
      unified_event_stream:
        type: array
---

<action>build_scene_stream</action>
