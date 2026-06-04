---
module: 02-mechanism/05-run-inner/08-messages-state
doc: baseline
status: drafted（现状散见 state-checkpoint + 01 + 代码）
---

# 08-messages-state — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 权威(messages 部分):`_migration-src/records/state-checkpoint-storage-model.md`(§2.4 messages 行)
> - 迁移源(summarization):`_migration-src/01-agent-loop/`
> - `state.py:214`(messages DeltaChannel,snapshot_frequency=50)、`middleware/cognitive_flow.py:292`(`interrupt()` 挂点)
> - ⚠️ summarization 搁浅 legacy:`phase_nodes/llm_phase_node.py:809`/`phase_executor.py`(assemble_graph 路径无 compaction,待搬回 live)

待填:messages 持久化/summarization/HITL 现状(细节链接 records,不复制)。
