---
mode: skill
name: main
subagents:
  - name: echo_expert
    target_skill: fixture.echo_expert
    description: Echoes text from a child expert skill.
---
<system_prompt>
Decide when to call the echo expert.
</system_prompt>
<exit_contract>
Call finish_task when done.
</exit_contract>
