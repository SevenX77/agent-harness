---
schema_version: "v0.3.0"
name: conflict-demo
description: A mock V0.3.0 skill to demonstrate and test sequential overwrite popover alerts.
io:
  inputs:
    type: object
    properties:
      input_text:
        type: string
  outputs:
    type: object
    properties:
      summary:
        type: string
phases:
  - phase1
  - phase2
---
<phase depends_on="input">phase1</phase>
<phase depends_on="phase1" output>phase2</phase>
