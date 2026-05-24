---
mode: agent
name: blank-agent
role: analyst
goal: Complete the requested task from the provided input.
exit_contract: Return a concise final answer.
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
    additionalProperties: true
---
<step id="read-input">Read the input carefully.</step>
<step id="answer">Produce a concise answer.</step>

# Blank Agent
