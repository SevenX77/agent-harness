---
doc: 00-architecture-overview
role: summary
status: living
authority: ./INDEX.md
updated: 2026-08-27
---

# Graph Agent MVP1 架构总览

本文是**当前 Graph Agent MVP1** 的一页摘要，权威模块地图是 [`INDEX.md`](./INDEX.md)。它不定义独立拆仓后的未来包名、文件格式或 executor 契约。

Engine MVP1 文档按三层组织：

1. Contract layer: 声明式文件、编译规则、数据契约。
2. Mechanism layer: compile / resolve / assemble / runtime 的实现机制。
3. API contract layer: engine 与 Studio 的操作边界。

完整模块列表见 [`INDEX.md`](./INDEX.md)。

独立 Python runtime/PyPI 包的未来目标见 [`docs/engine/graph-skill-runtime/v1-alignment.md`](../graph-skill-runtime/v1-alignment.md)。该文档目前为 `drafted`，尚未替代本页描述的当前 MVP1。

## Format SSOT

`graph_skill` 文件格式模板的唯一真相源是：

[`docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`](../skill-spec/00-FORMAT-GROUND-TRUTH.md)

MVP1 alignment 文档只写职责、边界和跨模块关系，不重复模板。

## Migration Source

历史迁移目录 `docs/engine/mvp1/_migration-src/` 已删除。正式模块文档是当前阅读入口；历史迁移细节通过 git 历史追溯。
