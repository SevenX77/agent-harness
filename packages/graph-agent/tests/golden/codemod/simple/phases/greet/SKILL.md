---
mode: skill
name: greet
tools:
- script.greet.generate_greeting
metadata: {}
---
<!--TODO: CODEMOD_REVIEW: missing exit_contract; generated default candidate-->
<system_prompt>
你是一个友善的助手。请调用 generate_greeting 工具生成问候语，然后调用 finish_task 结束。
</system_prompt>
<user_prompt>
请为 {user_name} 生成问候语。
</user_prompt>
<exit_contract>
Review migrated prompt, then call finish_task when the phase is complete.
</exit_contract>
