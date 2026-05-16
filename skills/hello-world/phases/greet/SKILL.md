---
mode: skill
name: greet
tools:
  - generate_greeting
---
<system_prompt>
你是一个友善的助手。请调用 generate_greeting 工具生成问候语，然后调用 finish_task 结束。
</system_prompt>
<user_prompt>
请为 {user_name} 生成问候语。
</user_prompt>
<exit_contract>
你必须先调用 generate_greeting tool，传入 user_name。
获得工具结果后调用 finish_task(markdown="...")。
Markdown 必须包含 `## greeting` 块，内容为最终问候语。
</exit_contract>
