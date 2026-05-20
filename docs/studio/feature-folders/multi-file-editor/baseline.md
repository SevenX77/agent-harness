# multi-file-editor (studio feature) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: 多文件树、Split Editor、Monaco 编辑、focus state、保存/冲突
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

多文件编辑的核心 UI 是 `SplitEditor`。它使用 `react-resizable-panels`，上方是编辑区，下方是 compact graph，见 `apps/studio/frontend/src/components/studio/SplitEditor.tsx:17` 到 `apps/studio/frontend/src/components/studio/SplitEditor.tsx:101`。当 splitMode 打开时，上方再拆成左右两个 editor panel，左右默认各 50%，见 `apps/studio/frontend/src/components/studio/SplitEditor.tsx:74` 到 `apps/studio/frontend/src/components/studio/SplitEditor.tsx:83`。

单个编辑器由 `LazyMonacoPanel` 渲染。它包含 header、语言标签、split 按钮、close 按钮，以及 Monaco editor 主体，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:181` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:224`。Monaco 配置关闭 minimap、开启 wordWrap、automaticLayout，并通过 `readOnly: !saveEnabled` 控制只读状态，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:211` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:224`。

文件树来自 AssetsPanel。它把 `skillDetail.files` 构造成 folder/file tree，并按 folder 优先、名称排序，见 `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:33` 到 `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:62`。FolderRow 支持展开/收起，见 `apps/studio/frontend/src/components/studio/panels/_shared/FolderRow.tsx:13` 到 `apps/studio/frontend/src/components/studio/panels/_shared/FolderRow.tsx:26`；FileRow 点击打开文件，见 `apps/studio/frontend/src/components/studio/panels/_shared/FileRow.tsx:16` 到 `apps/studio/frontend/src/components/studio/panels/_shared/FileRow.tsx:19`。

当前没有显式 active focus side UI。Workspace 打开文件时，如果 splitMode 且左侧已有文件，默认把新文件放右侧；否则放左侧，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:113` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:114`。这不是完整的“当前聚焦 pane”模型。

## 前端逻辑

WorkspaceContext 暴露 `splitMode`、`openSplitEditor`、`closeFile`、`updateFileContent`、`markFileSaved`、`setFileInFlight` 和 conflict 回调，见 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:22` 到 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:44`。`SplitEditor` 通过 context 读取 open files 和保存状态，见 `apps/studio/frontend/src/components/studio/SplitEditor.tsx:26` 到 `apps/studio/frontend/src/components/studio/SplitEditor.tsx:35`。

保存逻辑在 `LazyMonacoPanel`。内容变化后先更新 draft，再设置 1500ms debounce 保存，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:163` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:179`。切换 filePath 或卸载时会 flush 未保存内容，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:146` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:161`。

实际写文件调用 `writeSkillFile(skillId, filePath, draft, savedHash)`，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:97` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:144`。409 冲突会构造 conflict 对象并交给上层处理，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:117` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:129`；其他失败会 toast 并保留 in-flight 状态恢复，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:134` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:140`。

右侧 panel 文件列表通过 `panel-files.ts` 从 `SkillDetail` 推导。manifest files 优先返回真实文件列表，否则 fallback 到 `SKILL.md`、`skill-manifest.json` 和选中节点文件，见 `apps/studio/frontend/src/components/studio/panels/panel-files.ts:33` 到 `apps/studio/frontend/src/components/studio/panels/panel-files.ts:64`。输入输出文件由 `inputFiles` 生成，见 `apps/studio/frontend/src/components/studio/panels/panel-files.ts:66` 到 `apps/studio/frontend/src/components/studio/panels/panel-files.ts:88`。

语言识别目前是简单路径后缀映射：json/python/markdown，否则 text，见 `apps/studio/frontend/src/components/studio/panels/panel-files.ts:5` 到 `apps/studio/frontend/src/components/studio/panels/panel-files.ts:9`。文件元数据类型只有 path/language/content，见 `apps/studio/frontend/src/components/studio/file-types.ts:1` 到 `apps/studio/frontend/src/components/studio/file-types.ts:5`。

## 后端功能

后端提供 skill 文件读取、写入和冲突保护。前端 `writeSkillFile` 对应 `PUT /skills/{skill_id}/files/{path}`，客户端定义见 `apps/studio/frontend/src/api/client.ts:162` 到 `apps/studio/frontend/src/api/client.ts:173`。响应包含 content hash，类型见 `apps/studio/frontend/src/api/types.ts:403` 到 `apps/studio/frontend/src/api/types.ts:406`。

Workspace 文件系统的全局边界，包括目录型 skill、导入目录、写文件原子性和 watcher，详见 [workspace-file-system baseline](../../system-level/workspace-file-system/baseline.md)。本 feature 只覆盖用户可见的多文件打开、编辑、split、保存和冲突体验。

## API

核心 API：

- `GET /api/skills/{skill_id}` 提供 `SkillDetail.files`，后端 endpoint 见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:105`。
- `PUT /api/skills/{skill_id}/files/{path}` 由 `writeSkillFile` 调用，前端 client 见 `apps/studio/frontend/src/api/client.ts:162` 到 `apps/studio/frontend/src/api/client.ts:173`。
- `POST /api/skills/{skill_id}/compile` 用于编辑后编译反馈，见 `apps/studio/backend/app/routers/skills.py:108` 到 `apps/studio/backend/app/routers/skills.py:118`。

API 的冲突语义通过 hash 实现。`LazyMonacoPanel` 保存时携带 `initialHash/savedHash`，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:65` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:76`；保存成功后刷新 hash 并标记保存，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:106` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:116`。

## Data Model / State

编辑器 open file state 使用左右 pane：`EditorSide` 是 `left | right`，`OpenFile` 扩展 `FileMeta` 并带 `savedHash`，见 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:4` 到 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:13`。`WorkspaceContextValue` 保存当前 splitMode、activeFileDetails 和回调，见 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:22` 到 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:44`。

`LazyMonacoPanel` 内部维护 draft、savedValue、savedHash、debounce timer、inFlightRef，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:65` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:76`。当外部 value 或 filePath 改变时，它会重置 draft 与 hash，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:85` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:95`。

冲突状态由 `SaveConflict` 表达，包含 side/path/localContent/remoteContent/baseHash/errorMessage，见 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:13` 到 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:21`。冲突弹窗组件在 `apps/studio/frontend/src/components/studio/ConflictDialog.tsx:19`。

## Cross-feature interaction

与 Canvas：双击 Canvas 节点会打开对应文件并切换 panel，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:198` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:210`。Canvas baseline 见 [canvas-topology baseline](../canvas-topology/baseline.md)。

与 Copilot：Copilot 工具可以写文件，但前端没有把当前 pane/path 显式放进 message payload；上下文只通过 view snapshot 间接同步，见 `apps/studio/frontend/src/hooks/useCopilotContext.ts:48` 到 `apps/studio/frontend/src/hooks/useCopilotContext.ts:62`。Copilot baseline 见 [copilot-assistance baseline](../copilot-assistance/baseline.md)。

与 compile/run：编辑保存后用户可触发 compile，Workspace 会把 compile stage 和错误写入状态，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:292` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:322`。系统层布局和工作流见 [studio-layout baseline](../../system-level/studio-layout/baseline.md)。
