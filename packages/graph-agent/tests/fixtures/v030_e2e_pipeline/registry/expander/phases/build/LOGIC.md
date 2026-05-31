---
io:
  inputs:
    type: object
    required: [brief]
    properties:
      brief:
        type: string
  outputs:
    type: object
    required: [report]
    properties:
      report:
        type: string
actions: [build]
validator: false
---
<action>build</action>
