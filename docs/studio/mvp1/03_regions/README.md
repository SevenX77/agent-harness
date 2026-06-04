# 03_regions — UI 区域维 (维度 ③)

> 治理规则见 [../INDEX.md](../INDEX.md)。本 tier 拥有 **UI 组件**的结构/状态/props/API, 区域间 MECE(一个组件只属一个区域)。跨组件流程归 `02_capabilities`, 只在此被链接。文档模板见 INDEX §7 region 模板。
> **状态**: 12 个 region 均已落为文件夹制。每个 region 文件夹含 `baseline.md` 与 `mvp1-alignment.md`。4 个 ⚠ 是冲突热点(P1 优先实现)。

## 计划文档 (12)

| 文档 | 状态 | 关键组件 | 迁移来源 |
|---|---|---|---|
| [`welcome/`](./welcome/mvp1-alignment.md) | baseline + alignment | WelcomePage, NewSkillDialog | 旧 system-layout + workspace-fs(前端) |
| [`shell-layout/`](./shell-layout/mvp1-alignment.md) | baseline + alignment | Workspace, Header, Toolbar | 旧 system-layout(主体) |
| [`center-action-bar/`](./center-action-bar/mvp1-alignment.md) | ⚠ baseline + alignment | center-action-bar, CompileErrorPanel | 旧 system-layout + skill-lifecycle |
| [`canvas/`](./canvas/mvp1-alignment.md) | ⚠ baseline + alignment | GraphCanvas, ContextEdge, SkillNode | 旧 canvas-topology(组件) |
| [`editor/`](./editor/mvp1-alignment.md) | baseline + alignment | SplitEditor, LazyMonacoPanel | 旧 asset-explorer(编辑器/split) |
| [`assets/`](./assets/mvp1-alignment.md) | baseline + alignment | AssetsPanel | 旧 asset-explorer(文件树) + system-layout(panels) |
| [`input/`](./input/mvp1-alignment.md) | baseline + alignment | InputPanel, BatchRunner(orphan) | 旧 asset-explorer(笼统), 实为无主 |
| [`properties/`](./properties/mvp1-alignment.md) | ⚠ baseline + alignment | PropertiesPanel, phase-frontmatter | 旧 asset-explorer + trace-inspector(分) |
| [`timeline/`](./timeline/mvp1-alignment.md) | ⚠ baseline + alignment | TimelinePanel(历史), TracePanel(流式·未挂载) | 旧 trace-inspector(组件) |
| [`local-history/`](./local-history/mvp1-alignment.md) | baseline + alignment | HistoryPanel; RunDetailDrawer/BatchSummary ownership待定 | 旧 workspace-fs(前端), 薄 |
| [`copilot/`](./copilot/mvp1-alignment.md) | baseline + alignment | CopilotPanel, ModelPicker | 旧 copilot-chat(组件) |
| [`settings/`](./settings/mvp1-alignment.md) | baseline + alignment | SettingsPage, ProviderCard, LlmRolesTab, CopilotTab | 无 region 文档, 旧 llm-gateway 只覆盖后端 |
