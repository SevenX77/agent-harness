# 03_regions — UI 区域维 (维度 ③)

> 治理规则见 [../INDEX.md](../INDEX.md)。本 tier 拥有 **UI 组件**的结构/状态/props/API, 区域间 MECE(一个组件只属一个区域)。跨组件流程归 `02_capabilities`, 只在此被链接。文档模板见 INDEX §7 region 模板。
> **状态**: 骨架占位。以下文档待迁移/新建。4 个 ⚠ 是冲突热点(P1 先做)。

## 计划文档 (12)

| 文档 | 状态 | 关键组件 | 迁移来源 |
|---|---|---|---|
| `welcome.md` | 待创建 | WelcomePage, NewSkillDialog | 旧 system-layout + workspace-fs(前端) |
| `shell-layout.md` | 待创建 | Workspace, Header, Toolbar | 旧 system-layout(主体) |
| `center-action-bar.md` | ⚠ 待创建 (P1) | center-action-bar, CompileErrorPanel | 旧 system-layout + skill-lifecycle |
| `canvas.md` | ⚠ 待创建 (P1) | GraphCanvas, ContextEdge, SkillNode | 旧 canvas-topology(组件) |
| `editor.md` | 待创建 | SplitEditor, LazyMonacoPanel | 旧 asset-explorer(编辑器/split) |
| `assets.md` | 待创建 | AssetsPanel | 旧 asset-explorer(文件树) + system-layout(panels) |
| `input.md` | 待创建 | InputPanel, PredictInputDialog | 旧 asset-explorer(笼统), 实为无主 |
| `properties.md` | ⚠ 待创建 (P1, 最严重) | PropertiesPanel, phase-frontmatter | 旧 asset-explorer + trace-inspector(分) |
| `timeline.md` | ⚠ 待创建 (P1) | TimelinePanel(历史), TracePanel(流式·未挂载) | 旧 trace-inspector(组件) |
| `local-history.md` | 待创建 | BatchSummary, RunDetailDrawer | 旧 workspace-fs(前端), 薄 |
| `copilot.md` | 待创建 | CopilotPanel, ModelPicker | 旧 copilot-chat(组件) |
| `settings.md` | 待创建 | SettingsPage, ProviderCard, LlmRolesTab | 无 region 文档, 旧 llm-gateway 只覆盖后端 |
