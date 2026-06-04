---
module: 02-mechanism/02-resolver
doc: baseline
status: drafted（现状散在 mvp0 + 代码）
---

# 02-resolver — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 协议契约:mvp0 `10-skill-resolver-protocol-spec.md`(FROZEN)
> - `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:33-93`(resolve_skill + require_skill_resolver `[F-v3-resolver-missing]`)
> - `core/loader.py:528-545/595-615`(SUBGRAPH/AgentNode 经 resolver 递归 compile)、`graph_assembler.py:95-104`(assemble_graph 要求 skill_resolver)
> - DI 约束:`_migration-src/records/uncovered-areas.md §2`

待填:当前解析路径、local_workspace 现状。
