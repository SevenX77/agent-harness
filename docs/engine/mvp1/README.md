---
milestone: MVP1
status: drafted（2026-06-03 三层重构;23 模块落位）
ground_truth:
  - packages/graph-agent
  - ../mvp0/skill-spec（FROZEN）
---

# Engine MVP1 — 文档索引

> **架构入口看 [`00-architecture-overview.md`](00-architecture-overview.md)**(设计北极星:三层解耦 + 编译/装配/运行 生命周期 + 23 模块地图 + 关键决策 + 待设计清单)。

## 三层结构

整个系统按 **契约 A / 机制 B / API契约 C** 三层解耦(litmus:skill 语言 / 引擎实现 / 操作 API)。每个模块一个目录,含 `mvp1-alignment.md`(V4 目标设计)+ `baseline.md`(现状/迁移源)。

- **`01-contract/`(A,5)** — 声明式 skill 语言/规则/数据
  `01-physical-layout` · `02-skill-syntax` · `03-compile-rules` · `04-data-contracts` · `05-invalidation`
- **`02-mechanism/`(B,17)** — 引擎实现,按生命周期
  - 编译:`01-compile` · `02-resolver`
  - 装配:`03-assemble`
  - 运行·外层:`04-run-outer/`(`01-graph-exec` · `02-iterate` · `03-checkpoint`)
  - 运行·内层:`05-run-inner/`(`01-agent-loop` · `02-middleware` · `03-cognitive` · `04-tools` · `05-exit-control` · `06-golden-eval` · `07-subagent` · `08-messages-state`)
  - 接缝:`06-seam/`(`01-models` · `02-observability`)
  - 入口:`07-runtime`
- **`03-api-contract/`(C,1)** — engine↔studio 操作边界

## 迁移源(沉底)

- `_migration-src/` = 旧 concern 目录(01–11)+ `records` + `api-engine-studio-contract` 的**迁移源**;各模块 deep file:line 复核完后清理。
- `docs/engine/mvp0/skill-spec/`、`mvp0/workspace-spec/` = **FROZEN 契约基线**(♻️ 链接不复制)。
- 全量备份:`docs/engine/_mvp1-snapshot-2026-06-03/`。

## 阅读顺序
`00-overview`(地图)→ 契约 A(skill 是什么)→ 机制 B(编译→装配→运行 outer→inner→接缝→入口)→ API契约 C(怎么调引擎)。

## 写作规则
1. 代码证据来自实际打开的 `packages/graph-agent` 当前行号,不照抄漂移行号。
2. SSOT:一事实一处 owner,别处只链接;跨切内容写完整逻辑 + 引用 detail + 两侧双向引用。
3. 只写文档;实现/测试/FROZEN 解冻作为待办,归 kiro。
