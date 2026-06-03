# Studio docs — MVP1 / 新设计(重设计目标)

> **新设计文档**(MVP1 重设计目标)的三维体系。旧设计(MVP0 当前实现)baseline 在 [`../mvp0/`](../mvp0/)。
> 治理总纲 [`../INDEX.md`](../INDEX.md); 设计来源 = `.kiro/specs/studio-feature-*` + [`../_reorg/workflow-action-catalog.md`](../_reorg/workflow-action-catalog.md)。

- `01_workflows/` — ① 用户旅程脊柱(7 节点, 含 `00_settings` 运行底座)。
- `02_capabilities/` — ② 能力(14, 跨区域数据流/行为)。
- `03_regions/` — ③ UI 区域(12, 组件结构/状态)。
- `04_platform/` — 基础设施: 后端三分 + state-engine(D10) + i18n 横切。

> **MVP1 内的延后项(deferred)**: copilot brain 场景 / canvas REQ-8 策略开关 / trace REQ-7 结构化 diff / debug-resume DEF-005 —— 在各文档内标 `target-design` 且依赖引擎, 见 catalog。
