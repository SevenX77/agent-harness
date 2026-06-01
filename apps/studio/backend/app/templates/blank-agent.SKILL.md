---
schema_version: "v0.3.0"
name: Blank Agent
description: A single-step agent template for focused text work.
type: agent
metadata:
  tags:
    - template
    - agent
context_mapping:
  input_text: "{input.input_text}"
agent_profile:
  role: analyst
  goal: Complete the requested task from the provided input.
  steps:
    - Read the input carefully
    - Produce a concise answer
    - Call finish_task when complete
  constraints:
    - Keep the answer grounded in the input
  llm_role: analyst
user_prompt_template: |
  Use the following input to complete the task:

  {input_text}
---

# Blank Agent

