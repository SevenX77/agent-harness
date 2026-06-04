---
module: 02-mechanism/04-run-outer/03-checkpoint
doc: baseline
status: drafted（权威在 _migration-src/records/state-checkpoint;本域承外层/base 部分）
---

# 03-checkpoint — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 权威模型:`_migration-src/records/state-checkpoint-storage-model.md`(外层/base 部分;内层 messages 归 08-messages-state)
> - `packages/graph-agent/src/graph_agent/core/checkpointer.py:38-160`(backend/resolve)、`graph_assembler.py:150-151`(`builder.compile(checkpointer=)` 现状传入点)
> - `state.py`(`data` 通道现为普通字段,每 super-step 全量,delta reducer 待补)

待填:当前 checkpointer 传/存现状摘要(细节链接 records,不复制)。
