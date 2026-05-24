---
schema_version: "0.3.0"
name: v030-minimal
description: Minimal V0.3.0 graph fixture.
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
    required: [topic]
  outputs:
    type: object
    properties:
      answer:
        type: string
    required: [answer]
phases:
  - id: prepare
    src: phases/prepare
    depends_on: []
  - id: write
    src: phases/write
    depends_on: [prepare]
  - id: child
    src: phases/child
    depends_on: [prepare]
---

