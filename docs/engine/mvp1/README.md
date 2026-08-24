---
milestone: MVP1
status: living
updated: 2026-06-28
---

# Engine MVP1 文档入口

架构入口见 [`00-architecture-overview.md`](00-architecture-overview.md)；模块索引见 [`INDEX.md`](INDEX.md)。

## 结构

- `01-contract/`: 声明式契约层。
- `02-mechanism/`: 引擎实现机制层。
- `03-api-contract/`: engine 与 Studio 的操作 API 契约。

## 格式模板唯一真相源

`graph_skill` 文件格式模板不再写在 MVP1 alignment 里。唯一真相源是：

[`docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`](../skill-spec/00-FORMAT-GROUND-TRUTH.md)

## 迁移源状态

`docs/engine/mvp1/_migration-src/` 已在 2026-06-28 删除。已迁内容以正式模块文档为准；需要历史细节时看 git 历史。
