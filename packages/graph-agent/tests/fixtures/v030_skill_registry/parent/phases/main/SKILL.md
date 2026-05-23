---
name: main
mode: agent
phase_config:
  io:
    inputs:
      type: object
      required: [brief]
      properties:
        brief:
          type: string
    outputs:
      type: object
      properties:
        answer:
          type: string
  tools:
    - finish_task
  subagents:
    - name: echo_expert
      target_skill: echo_agent
      description: Echoes a short answer for registry tests.
  subgraphs: []
  references: []
  examples: []
---
<role>
You are a parent test Agent.
</role>

<goal>
Use @subagent:echo_expert when a brief needs a second pass.
</goal>

<step id="S1" name="ask_subagent">
Ask @subagent:echo_expert for a concise response.
</step>

<protocol id="P1">
Keep answers short.
</protocol>

<exit_contract>
Call finish_task with answer.
</exit_contract>
