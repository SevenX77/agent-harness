---
mode: skill
name: synthesize_report
---
<system_prompt>
综合产品亮点和使用场景，写出一份面向消费者、结构清晰、有吸引力的产品说明书。
说明书应避免参数堆砌，突出购买理由、核心体验和适用场景。
</system_prompt>
<exit_contract>
完成产品说明书后调用 finish_task(markdown="...")。
Markdown 必须包含 `## final_manual` 块，内容为最终消费者产品说明书。
</exit_contract>
