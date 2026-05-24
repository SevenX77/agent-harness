---
schema_version: "0.3.0"
name: Data Extractor
description: Extract structured JSON fields from unstructured text.
io:
  inputs:
    type: object
    properties:
      document_text:
        type: string
      extraction_goal:
        type: string
    required: [document_text, extraction_goal]
    additionalProperties: true
  outputs:
    type: object
    properties:
      extracted_data:
        type: object
    required: [extracted_data]
    additionalProperties: true
phases:
  - id: extract
    src: phases/extract
    depends_on: []
---

# Data Extractor
