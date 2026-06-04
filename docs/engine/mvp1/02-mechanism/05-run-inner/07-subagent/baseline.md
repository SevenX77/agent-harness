---
module: 02-mechanism/05-run-inner/07-subagent
doc: baseline
status: drafted（迁自 _migration-src/05-subagent-dispatch）
---

# 07-subagent — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/05-subagent-dispatch/{baseline,mvp1-alignment}.md`
> - `core/graph_assembler.py:692-699`(tool naming)、`:1120-1155`(runtime map)、`:1057-1277`(depth/校验/child config)、`:1254-1277`(parent_run_id/subagent_depth/tags)
> - `core/subagents.py:24-34/150-157`(SubagentValidationFailure/depth)
> - 参考:`temp/deepagents/.../middleware/subagents.py:27-69`(middleware 提供 subagent tool 范式)

待填:当前派发 helper 实情(已存在,未挂 create_agent middleware)+ lifecycle 事件缺口。
