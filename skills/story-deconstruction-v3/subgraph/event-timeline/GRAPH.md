---
schema_version: "v0.3.0"
name: event-timeline
description: Per-chapter event extraction (batch) then chapter-by-chapter timeline stitching (loop with boundary merge judgment).
io:
  inputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [global_timeline]
    properties:
      global_timeline:
        type: object
        required: [events]
        properties:
          events: {type: array, items: {type: object}}
phases:
  - extrac
  - stitch
---

<phase depends_on="input">extrac</phase>
<phase depends_on="extrac" output>stitch</phase>
