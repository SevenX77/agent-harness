---
schema_version: "v0.3.0"
name: Chained Reasoning
description: Demonstrates a two-phase reasoning chain where phase B reviews phase A.
type: graph
metadata:
  tags:
    - template
    - reasoning
context_mapping:
  question: "{input.question}"
  analysis: ""
  final_answer: ""
io:
  inputs:
    - name: question
      type: str
      source: runtime
  outputs:
    - name: final_answer
      type: dict
      target: artifact
phases:
  - name: analyze
    mode: llm
    llm_role: analyst
    prompt: |
      Break down the question into assumptions, evidence, and candidate answers.
      Question: {question}
  - name: synthesize
    mode: llm
    llm_role: analyst
    prompt: |
      Use the analysis from the prior phase to produce a final answer.
      Include risks and confidence.
---

# Chained Reasoning

