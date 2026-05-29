---
schema_version: "v0.3.0"
name: e2e-echo
io:
  inputs:
    type: object
    required: [note]
    properties:
      note:
        type: string
  outputs:
    type: object
    required: [echoed]
    properties:
      echoed:
        type: string
phases:
  - echo
---
<phase depends_on="input" output>echo</phase>
