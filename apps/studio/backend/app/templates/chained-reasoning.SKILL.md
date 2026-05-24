---
schema_version: "0.3.0"
name: Chained Reasoning
description: A two-phase reasoning chain where synthesis follows analysis.
io:
  inputs:
    type: object
    properties:
      question:
        type: string
    required: [question]
    additionalProperties: true
  outputs:
    type: object
    properties:
      final_answer:
        type: object
    additionalProperties: true
phases:
  - id: analyze
    src: phases/analyze
    depends_on: []
  - id: synthesize
    src: phases/synthesize
    depends_on: [analyze]
---

# Chained Reasoning
