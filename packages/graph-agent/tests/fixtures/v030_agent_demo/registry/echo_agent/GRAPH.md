---
schema_version: "v0.3.0"
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
  - echo
---
<phase depends_on="input" output>echo</phase>
