---
schema_version: "0.3.0"
name: demo-echo-agent
io:
  inputs:
    type: object
    required: [note]
    properties:
      note:
        type: string
  outputs:
    type: object
    properties:
      echoed_note:
        type: string
phases:
  - id: echo
    src: phases/echo
    depends_on: []
---
