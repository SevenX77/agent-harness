---
schema_version: "0.3.0"
name: v030-agent-demo
description: Real V0.3.0 Agent fixture for compiler and runtime smoke coverage.
io:
  inputs:
    type: object
    required: [chapter_content]
    properties:
      chapter_content:
        type: string
  outputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items:
          type: object
phases:
  - id: segment
    src: phases/segment
    depends_on: []
---
