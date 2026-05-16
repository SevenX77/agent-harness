---
mode: skill
name: write_scenarios
---
<system_prompt>
根据产品亮点，构思 3 个具体的使用场景。
每个场景都要体现用户、使用环境、关键需求以及该产品解决问题的方式。
注意：至少举 3 个具体使用场景。
</system_prompt>
<exit_contract>
完成场景构思后调用 finish_task(markdown="...")。
Markdown 必须包含 `## scenarios` 块，至少给出 3 个具体场景。
</exit_contract>
