---
module: 02-mechanism/03-assemble
doc: baseline
status: drafted（现状待迁自 _migration-src/01-agent-loop + 代码）
---

# 03-assemble — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 装配期时序:mvp0 `12-compile-runtime-flow-spec.md`(装配流)
> - 迁移源:`_migration-src/01-agent-loop/{baseline,mvp1-alignment}.md`(_build_skill_node + create_agent 迁移)
> - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`(_build_skill_node 现状入口 437-479、all_tools 构造 479-480、当前 live 手写 ReAct loop 510-562、checkpointer 传入 150-151)

待填:当前装配/闭包构造实情 + 手写 loop 代码位置 + 与 create_agent 目标差异。
