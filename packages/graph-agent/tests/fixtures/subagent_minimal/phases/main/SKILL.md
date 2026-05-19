---
mode: skill
name: main
phase_config:
  subagents:
    - name: echo_expert
      path: subskills/echo_expert
      description: Echoes text from a child expert skill.
---
<system_prompt>
Decide when to call the echo expert.
</system_prompt>
<exit_contract>
Call finish_task when done.
</exit_contract>
