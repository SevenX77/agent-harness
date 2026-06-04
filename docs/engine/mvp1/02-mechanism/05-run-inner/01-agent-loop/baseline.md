---
module: 02-mechanism/05-run-inner/01-agent-loop
doc: baseline
status: drafted（迁自 _migration-src/01-agent-loop）
---

# 01-agent-loop — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/01-agent-loop/{baseline,mvp1-alignment}.md`
> - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:483-576`(需替换的 live 手写 ReAct loop)、`:581-603`(`_resolve_phase_chat_model`)
> - `.venv/.../langchain/agents/factory.py:658-673`(create_agent 支持参数)

待填:当前手写 loop 实情 + create_agent 目标差异。
