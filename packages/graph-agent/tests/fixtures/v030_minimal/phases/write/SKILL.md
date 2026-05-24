---
mode: agent
io:
  inputs:
    type: object
    properties:
      prepared_topic:
        type: string
    required: [prepared_topic]
  outputs:
    type: object
    properties:
      answer:
        type: string
    required: [answer]
max_iterations: 1
---

<role>
Writer
</role>

<goal>
Write a short answer from prepared_topic.
</goal>

<exit_contract>
Return answer.
</exit_contract>

