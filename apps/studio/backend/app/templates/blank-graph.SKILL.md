---
schema_version: "0.3.0"
name: Blank Graph
description: A minimal graph template with runtime input and artifact output.
io:
  inputs:
    type: object
    properties:
      input_text:
        type: string
    required: [input_text]
    additionalProperties: true
  outputs:
    type: object
    properties:
      result:
        type: object
    additionalProperties: true
phases:
  - id: draft
    src: phases/draft
    depends_on: []
---

# Blank Graph
