---
schema_version: "2.0"
name: Blank Graph
description: A minimal multi-phase graph template with runtime input and artifact output.
type: graph
metadata:
  tags:
    - template
    - graph
context_mapping:
  input_text: "{input.input_text}"
  draft_result: ""
io:
  inputs:
    - name: input_text
      type: str
      source: runtime
  outputs:
    - name: result
      type: dict
      target: artifact
phases:
  - name: draft
    mode: llm
    llm_role: analyst
    prompt: |
      Analyze {input_text} and produce a structured draft result.
  - name: review
    mode: llm
    llm_role: analyst
    prompt: |
      Review the draft result and call finish_task with the final response.
---

# Blank Graph

