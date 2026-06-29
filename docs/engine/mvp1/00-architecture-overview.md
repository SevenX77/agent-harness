---
doc: 00-architecture-overview
status: active
updated: 2026-06-28
---

# Graph Agent MVP1 架构总览

Engine MVP1 文档按三层组织：

1. Contract layer: 声明式文件、编译规则、数据契约。
2. Mechanism layer: compile / resolve / assemble / runtime 的实现机制。
3. API contract layer: engine 与 Studio 的操作边界。

完整模块列表见 [`INDEX.md`](./INDEX.md)。

## Format SSOT

`graph_skill` 文件格式模板的唯一真相源是：

[`docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`](../skill-spec/00-FORMAT-GROUND-TRUTH.md)

MVP1 alignment 文档只写职责、边界和跨模块关系，不重复模板。

## Migration Source

历史迁移目录 `docs/engine/mvp1/_migration-src/` 已删除。正式模块文档是当前阅读入口；历史迁移细节通过 git 历史追溯。
