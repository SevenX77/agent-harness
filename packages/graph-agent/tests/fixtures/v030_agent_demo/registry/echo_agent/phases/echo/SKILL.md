---
io:
  inputs:
    type: object
    required: [note]
    properties:
      note:
        type: string
  outputs:
    type: object
    properties:
      echoed_note:
        type: string
tools:
  - finish_task
subagents: []
subgraphs: []
references: []
examples: []
---
<role>
You echo review notes for the parent Agent.
</role>

<goal>
Return a concise review note.
</goal>

<step id="S1" name="echo">
Echo the provided note.
</step>

<protocol id="P1">
Keep the response brief.
</protocol>
