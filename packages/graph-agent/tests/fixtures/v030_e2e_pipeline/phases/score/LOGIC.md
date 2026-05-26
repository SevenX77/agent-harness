---
io:
  inputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items:
          type: object
  outputs:
    type: object
    required: [report]
    properties:
      report:
        type: string
actions: [score]
validator: false
---
<action>score</action>
