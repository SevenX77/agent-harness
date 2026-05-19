---
status: Living
target_goal: "Studio 桌面端界面布局的单一真相, 所有 UX/feature doc 的 ground truth 参考"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/Workspace.tsx:431
  - apps/studio/frontend/src/components/studio/Header.tsx:32
  - apps/studio/frontend/src/components/studio/Toolbar.tsx:21
  - apps/studio/frontend/src/components/studio/Panels.tsx:258
  - apps/studio/frontend/src/components/copilot/copilot-panel.tsx:1
  - apps/studio/frontend/src/components/studio/SplitEditor.tsx:40
  - apps/studio/frontend/src/components/studio/SettingsPage.tsx:50
  - apps/studio/frontend/src/components/welcome/WelcomePage.tsx:10
linked_specs:
  - .kiro/specs/studio-uikit-redesign/
  - .kiro/specs/studio-frontend-v21-multifile-editor/
last_updated: 2026-05-19
---

# Studio 界面布局规范 (Studio Layout Spec)

## 1. 整体布局总览

整个 Studio 采用现代 IDE 经典的“顶部导航 + 极窄左侧边栏 + 可伸缩主分屏”布局架构。底层依赖 `react-resizable-panels`。

### 布局 ASCII Art

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  顶部顶栏 (Header) [高度: 44px/h-11]                                         │
├────┬───────────────────────┬───────────────────────────────┬─────────────────┤
│ 左 │ 左侧面板 (Left Panel) │ 主工作区 (Main Panel)         │ 右侧抽屉        │
│ 侧 │                       │                               │ (Right Panel)   │
│ 工 │                       │ ┌───────────────────────────┐ │                 │
│ 具 │                       │ │                           │ │                 │
│ 条 │ [Assets / Properties] │ │ Canvas 画布 / Monaco 编辑器 │ │ Copilot Panel │
│    │                       │ │                           │ │                 │
│ 48 │ min 14%, max 35%      │ │  min 30%, default 60/80%  │ │ min 18%, max 35%│
│ px │ default 20%           │ └───────────────────────────┘ │ default 20%     │
│    │                       │ [中心操作栏: Compile/Run 等]  │                 │
│    │                       │                               │                 │
└────┴───────────────────────┴───────────────────────────────┴─────────────────┘
```
*(注意：Settings 页面等浮层会 Overlay 覆盖主工作区。)*

## 2. 区域逐项定义

### 2.1 顶部顶栏 (Header)
- **对应组件**: `Header` (`apps/studio/frontend/src/components/studio/Header.tsx:32`)
- **尺寸**: 固定高度 44px (`h-11`)。
- **显示条件**: Always visible。
- **包含功能**:
  - 左侧：Home 按钮 / Tauri 窗口拖拽区 / Logo。
  - 中部：面包屑导航 (NavStack) 或 Workspace 名称，状态徽章 (Draft)。
  - 右侧：Git/Team 同步按钮组 (Save/Sync/Review/Release)，以及触发 Copilot 的 Toggle 按钮。
- **交互互动**: 点击右侧的 Sparkles 图标，可触发 `copilotOpen` 状态，挤压中侧主面板以显示出最右侧的 Copilot 面板。

### 2.2 左侧工具条 (Toolbar)
- **对应组件**: `Toolbar` (`apps/studio/frontend/src/components/studio/Toolbar.tsx:21`)
- **尺寸**: 固定宽度 48px (`w-12`)。
- **显示条件**: Always visible。
- **包含功能**:
  - 核心切换器组：Assets, Input, Trace Timeline, Properties, Local History。
  - 底部操作组：暗色/亮色切换 (Theme Toggle)，设置按钮 (Settings)。
- **交互互动**: 点击对应的图标切换 `activePanel` 状态，控制紧邻其右侧的 Left Panel 显示何种子组件。再次点击高亮图标可彻底隐藏 Left Panel。

### 2.3 左侧面板 (Left Panel)
- **对应组件**: `Panels` (`apps/studio/frontend/src/components/studio/Panels.tsx:258` 此处指实际容纳的 AssetsPanel 等业务面板)
- **尺寸**: 默认 `20%`，可拖拽缩放，`minSize="14%"`，`maxSize="35%"`。
- **显示条件**: 当 `activePanel` (来自 Toolbar) 不为 `null` 时显示。
- **包含功能**:
  - `AssetsPanel`: 渲染文件树。
  - `TimelinePanel`: (待实现) 瀑布流。
  - `PropertiesPanel`: 当前选中节点的属性。
  - `HistoryPanel`: 本地历史记录。
- **交互互动**: 在 `AssetsPanel` 中点击一个文件，会触发 `onFileOpen`，将该文件加载进 Main Panel 的 SplitEditor 中。

### 2.4 主工作区 (Main Panel / Center)
- **对应组件**: `Workspace` 中的中心渲染区 (`apps/studio/frontend/src/components/studio/Workspace.tsx:431`)
- **尺寸**: 占剩余全部空间（弹性）。如果 Copilot 开启则默认 `60%`，否则默认 `80%`，极限最小宽度 `30%`。
- **显示条件**: Always visible。
- **包含功能 (通过状态互斥渲染)**:
  - `SettingsPage`: Overlay 模式，当 `settingsOpen` 为 true 时遮盖整个 Main Panel。
  - `SplitEditor`: 代码编辑器，当存在已打开文件时 (`hasOpenFile`) 渲染。
  - `WelcomePage`: 极简主页，当没有加载任何 Skill 时 (`currentSkillId === null`) 渲染。
  - `GraphCanvas`: React Flow 主画板。
  - **中心操作栏 (CenterActionBar)**: 底部居中的控制悬浮条，包含 Compile / Predict / Run 按钮。
  - **错误面板 (CompileErrorPanel)**: 底部悬浮的错误报告列表。
- **交互互动**: 在 Canvas 中点击节点，会触发 `onNodeSelect` 并且可能会联动开启左侧的 PropertiesPanel 或改变右侧的 Monaco 光标。

### 2.5 右侧抽屉 (Right Panel / Copilot)
- **对应组件**: `CopilotPanel` (`apps/studio/frontend/src/components/copilot/copilot-panel.tsx:1`)
- **尺寸**: 默认 `20%`，可拖拽缩放，`minSize="18%"`, `maxSize="35%"`。
- **显示条件**: 当 `copilotOpen` 为 true 时显示。
- **包含功能**:
  - 聊天对话框区。
  - 模型切换器与 Prompt 状态上下文（当前锁定的节点信息等）。
- **交互互动**: 受 Header 中的按钮控制；它能够感知 Main Panel 中被选中的 `selectedNodeId`。

## 3. Layout 状态机

Studio 的布局受一系列核心状态控制，构成以下布局矩阵：

1. **No-Skill Loaded (初始态)**
   - **Header**: 只有 Logo 和空的 Nav。
   - **Toolbar**: 隐藏 (通过判定逻辑)。
   - **Main Panel**: 渲染 `WelcomePage`。
   - **Left/Right Panel**: 均不显示。
2. **Skill-Loaded Canvas View (专注画布)**
   - **Header**: 显示完整 Workspace 面包屑。
   - **Toolbar**: 显示，默认激活 `assets`。
   - **Left Panel**: 渲染 `AssetsPanel` (文件树)。
   - **Main Panel**: 渲染 `GraphCanvas`，底部浮现 `CenterActionBar`。
   - **Right Panel**: 根据 `copilotOpen` 决定。
3. **Skill-Loaded Editor View (分屏代码态)**
   - **触发条件**: 从 `AssetsPanel` 中双击了某个文件。
   - **Main Panel**: `GraphCanvas` 被替换为 `SplitEditor`（代码与画布的联动）。
4. **Settings View (全局设置态)**
   - **触发条件**: 点击 Toolbar 底部的齿轮。
   - **Main Panel**: 完全被 `SettingsPage` 覆盖，屏蔽掉后方的 Canvas 或 Editor。
   - **包含组件**: 内部使用 Tab 切换 (General / API Keys / LLM Roles)。在 API Keys 下，由 ProviderCard 列表与 AddProviderForm 组件负责交互。

## 4. View 模式切换
目前前端代码仅实现了一套大一统的 **Edit View (编辑态)**，在此态下通过 Toolbar 切换看属性或资产。
未来关于 *Trace* (追踪态) 或 *Run* (执行观测态) 的模式变迁，其布局变化（例如强行滑出下方的 Timeline 控制台或遮盖左侧栏）由 `trace-and-predict-visibility` spec 进行延伸定义。目前代码中没有独立出专门的路由视角进行切换。

## 5. 已知 layout 反模式 (TODOs)
在审计 `apps/studio/frontend/src/` 代码树时，发现以下 Hygiene 问题，建议在后续实施中重构：
- **`Panels.tsx` 文件过于臃肿**: 里面挤压了 `AssetsPanel`, `PanelHeader`, `FolderRow`, `FileRow` 等多个功能相去甚远的组件。应按照子目录拆分至 `src/components/studio/panels/assets-panel.tsx` 等。
- **`Workspace.tsx` 逻辑过度耦合**: 这个文件近 500 行，承担了 WebSocket 连接、Compile 触发、状态管理和全局布局等过多职责。应该抽离出 `useWorkspaceSockets` 和 `useWorkspaceLayout` 等自定义 hooks。

## 相关 Spec
- [studio-uikit-redesign](../../.kiro/specs/studio-uikit-redesign/design.md)
- [studio-frontend-v21-multifile-editor](../../.kiro/specs/studio-frontend-v21-multifile-editor/design.md)
