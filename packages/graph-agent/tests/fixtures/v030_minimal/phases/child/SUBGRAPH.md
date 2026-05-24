---
mode: subgraph
target_skill: child-skill
io:
  inputs:
    type: object
    properties:
      prepared_topic:
        type: string
    required: [prepared_topic]
  outputs:
    type: object
    properties:
      answer:
        type: string
    required: [answer]
---

