---
name: echo
mode: agent
phase_config:
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
You echo review notes.
</role>

<goal>
Return a short echoed note.
</goal>

<workflow>
  <step id="S1" name="echo">
  Echo the note.
  </step>
</workflow>

<protocol id="P1">
Keep the response brief.
</protocol>

<exit_contract>
Call finish_task with echoed_note.
</exit_contract>
