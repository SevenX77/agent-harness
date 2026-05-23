---
schema_version: "0.3.0"
name: parent_skill
io:
  inputs:
    type: object
    required: [brief]
    properties:
      brief:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - id: main
    src: phases/main
    depends_on: []
---
