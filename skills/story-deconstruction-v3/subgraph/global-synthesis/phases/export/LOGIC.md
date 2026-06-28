---
actions:
  - export_story_framework
validator: false
io:
  inputs:
    type: object
    required: [climax_ranking, foreshadowing_closure, character_ranking, scenes, unified_event_stream, entity_registry]
    properties:
      climax_ranking:
        type: array
      foreshadowing_closure:
        type: array
      character_ranking:
        type: array
      scenes:
        type: array
      unified_event_stream:
        type: array
      entity_registry:
        type: object
  outputs:
    type: object
    required: [story_framework]
    properties:
      story_framework:
        type: object
---

<action>export_story_framework</action>
