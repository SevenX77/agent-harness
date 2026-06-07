---
doc: _ARCHIVED
status: archived（2026-06-06;迁移源已全部迁入正式模块,留底不删、不作 SSOT）
---

# 🗄️ ARCHIVED — 迁移源(留底,勿当现状)

本目录(`_migration-src/`)是 Graph Agent mvp1 设计的**迁移源**——旧 concern 文档(01–13)+ `records/` + `api-engine-studio-contract.md`。**内容已全部迁入正式模块**(逐源去向见 [`../INDEX.md` §3.2](../INDEX.md));本目录**留底备查、不删除、不作 SSOT**。

## 重要:忽略各文件内的"核对进度 / 未迁 N"计数器
各文件 frontmatter / 顶部的 `<!-- 核对进度:已迁 X / 未迁 Y -->` 与 `⚠️ 未迁入` 块标记是 **2026-06-04 归档前的快照**,**已被 `INDEX.md §3.2`(2026-06-06「已迁」)取代**——以 INDEX §3.2 为准,本目录内标记**作废勿信**(避免"源侧说没迁完"的误导)。

## 现状 SSOT 在哪
- 正式模块:`../01-contract/`、`../02-mechanism/`、`../03-api-contract/` 的 `mvp1-alignment.md`(目标)+ `baseline.md`(现状)。
- 横切映射 + 迁移追溯:`../INDEX.md`(§1 单元表、§3.2 迁移源去向)。
- 决策留底(轴①):`records/`(state-checkpoint / change-invalidation / uncovered-areas)保留更深决策细节,供回填,但**实现 SSOT 已在正式模块**。

> 退役性质:本目录可随时物理移走/删除而不影响正式 mvp1 设计的完整性(内容已迁、溯源在 INDEX);保留仅为决策考古。
