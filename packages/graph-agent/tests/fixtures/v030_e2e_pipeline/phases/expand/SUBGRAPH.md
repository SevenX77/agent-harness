---
target_skill: e2e.expander
allow_sequential_overwrite: [report]
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
validator: false
---
