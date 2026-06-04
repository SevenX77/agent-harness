---
module: 02-mechanism/05-run-inner/05-exit-control
doc: baseline
status: drafted（迁自 _migration-src/04-exit-control）
---

# 05-exit-control — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/04-exit-control/{baseline,mvp1-alignment}.md`
> - `core/nudge_injector.py:75-151`(standard/selfcheck nudge + 计数,已实现)
> - `middleware/cognitive_flow.py:680-699`(invalid finish_task 回 model;成功路径 `goto=END:511` 待改 marker)
> - 参考:`temp/deepagents/.../middleware/rubric.py:426-670`(after_agent 范式)
> - 未实现:live path 无 after_agent exit gate(手写 loop 自然停止是 break,graph_assembler.py:526-528)

待填:after_agent 闸 + nudge + 显式失败现状/目标。
