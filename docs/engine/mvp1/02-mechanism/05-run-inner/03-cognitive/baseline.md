---
module: 02-mechanism/05-run-inner/03-cognitive
doc: baseline
status: drafted（迁自 _migration-src/02/03/07/08）
---

# 03-cognitive — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/02-finish-task-submission/`、`03-finish-task-validation/`、`07-output-format/`、`08-prompt-and-cleanup/`
> - `middleware/cognitive_flow.py:348-512`(wrap_tool_call 截 finish_task/ask_clarification;成功路径现 `goto=END:511` 待改 marker)
> - `cognitive/md2json.py`(简化版,待退役)· `tools/md_to_json.py`(接回目标)

待填:四源 baseline 合并 + prompt/finish/输出/patcher 实情。
