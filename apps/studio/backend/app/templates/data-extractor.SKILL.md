---
schema_version: "2.0"
name: Data Extractor
description: Extract structured JSON fields from unstructured text.
type: graph
metadata:
  tags:
    - template
    - extraction
context_mapping:
  document_text: "{input.document_text}"
  extraction_goal: "{input.extraction_goal}"
  extracted_data: ""
io:
  inputs:
    - name: document_text
      type: str
      source: runtime
    - name: extraction_goal
      type: str
      source: runtime
  outputs:
    - name: extracted_data
      type: dict
      target: file
      path: "output/extracted_data.json"
phases:
  - name: extract
    mode: llm
    llm_role: analyst
    output_schema_md: |
      {
        "fields": {
          "summary": "string",
          "entities": "array",
          "confidence": "number"
        }
      }
    prompt: |
      Extract structured data from {document_text}.
      Goal: {extraction_goal}
      Return JSON with summary, entities, and confidence.
---

# Data Extractor

