---
schema_version: "v0.3.0"
name: e2e-expander
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
phases:
  - build
---
<phase depends_on="input" output>build</phase>
