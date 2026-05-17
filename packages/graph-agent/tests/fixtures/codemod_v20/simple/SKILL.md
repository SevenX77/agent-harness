---
name: hello-world
description: 最简单的打招呼 skill
type: simple
io:
  inputs:
    - name: user_name
      type: str
      source: runtime
---

<phase_config>
name: greet
tier: balanced
tools:
  - script.greet.generate_greeting
</phase_config>

<system_prompt>
你是一个友善的助手。请调用 generate_greeting 工具生成问候语，然后调用 finish_task 结束。
</system_prompt>

<user_prompt>
请为 {user_name} 生成问候语。
</user_prompt>