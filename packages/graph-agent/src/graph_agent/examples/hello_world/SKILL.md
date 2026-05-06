---
name: hello-world
description: |
  Minimal example skill for verifying graph_agent installation.
  Uses a simple greet tool and finishes.
type: simple
---

<phase_config>
name: greet
llm_role: fast
tools:
  - script.greet.greet
</phase_config>

<system_prompt>
You are a friendly assistant. Your task is to:
1. Call the greet tool to get a greeting message
2. Call finish_task to end the phase

Make sure to call update_working_memory first to record your plan.
</system_prompt>

<user_prompt>
Please generate a greeting message for the user.
</user_prompt>
