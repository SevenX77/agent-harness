---
schema_version: "v0.3.0"
name: round14-e2e-pipeline
description: Full V0.3.0 graph skill exercising agent + logic + subgraph nodes end to end.
io:
  inputs:
    type: object
    required: [chapter_content]
    properties:
      chapter_content:
        type: string
  outputs:
    type: object
    required: [report]
    properties:
      report:
        type: string
phases:
  - segment
  - score
  - expand
---
<phase depends_on="input">segment</phase>
<phase depends_on="segment">score</phase>
<phase depends_on="score" output>expand</phase>
