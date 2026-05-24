---
mode: logic
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
    required: [topic]
  outputs:
    type: object
    properties:
      prepared_topic:
        type: string
    required: [prepared_topic]
actions: [prepare]
---

