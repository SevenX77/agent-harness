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
  - .kiro/specs/copilot-context-design/
  - .kiro/specs/split-editor-focus-enhancement/
last_updated: 2026-05-19
---

# Studio 界面布局规范 (Studio Layout Spec)

## 0. Studio 设计原则 (Design Principles)

### 0.1 本地文件 = 单一真相 (Single Source of Truth)
Studio 是 Tauri 桌面单机应用。**本地磁盘文件是唯一真相, Studio UI 永远跟随本地文件状态渲 染**。任何程序 (Studio API / VS Code / git checkout / 自动化脚本) 修改了本地文件, Studio 界面立刻 hot reload 反映最新文件内容, 不弹 conflict 警告, 不询问用户。这是 Studio 设计的 根本前提。

推论:
- **不存在 conflict 概念**。文件被改了就是被改了, 没有 "我正在编辑没保存 vs 外部改了" 的 race condition 需要解决。
- **WebSocket `skill_changed` 事件应直接驱动 UI hot reload**, 绝不弹 ConflictDialog 阻断 用户 (当前代码中的 ConflictDialog 是错误的产品假设, 应砍除, 见 §5)。

### 0.2 OS Title Bar 跨平台策略 (MVP0)
Studio 桌面端 (Tauri) 保留 OS 标准窗口装饰 (`decorations: true` 默认): macOS 左上角红绿灯 (close/minimize/maximize), Windows 右上角三键 (`—` / `□` / `×`)。Header (44px) 位于 OS 标题栏之 下, 跨平台 (macOS / Windows / Linux / Browser) 布局一致, 不做平台分支。

**MVP0 设计取舍**: 不学 VS Code 将 Header 合并进 OS Title Bar (Windows title bar 上承载系统 menu bar, 合并需复杂跨平台适配). MVP1+ 评估是否做合并 (见 [Task #31](../../) 设计参考)。

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
- **尺寸**: 固定高度 44px (`h-11`)。位于 OS 标题栏 (含红绿灯 / Windows 三键, Tauri 默认 `decorations: true`) 之下, 跨平台保持统一 (MVP0 不做 OS Title Bar 合并, 见 §0.2)。
- **显示条件**: Always visible。
- **包含功能**:
  - 左侧：Logo (点击返回 welcome page, Tauri 与 Browser 模式行为统一) + "GSkill Studio" 文字 。
  - 中部：当前顶层 Workspace (Skill) 名称, 状态徽章 (Draft)。*(注意：全局面包屑已移至 Canvas, 见 §2.4)*
  - 右侧：Git/Team 同步按钮组 (Save / Sync / Review / Release), 以及触发 Copilot 的 Toggle 按钮 (Sparkles 图标)。
- **交互互动**: 
  - 点击 Logo: 返回 welcome page (`onHome` 回调)
  - 点击右侧 Sparkles 图标: 触发 `copilotOpen` 状态, 挤压中侧主面板以显示出最右侧的 Copilot  面板

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
  - `GraphCanvas`: React Flow 主画板。其顶部存在悬浮的面包屑导航条 (Breadcrumbs), 专用于展示从父级进入 Subgraph 子图时的层级路径 (仅 Subgraph 下钻态显示, 见 §3)。
  - **中心操作栏 (CenterActionBar)**: 底部居中的控制悬浮条，包含 Compile / Predict / Run 按钮。
  - **错误面板 (CompileErrorPanel)**: 底部悬浮的错误报告列表。
- **交互互动**: 在 Canvas 中, 节点交互按触发方式严格区分:
  - `单击 / 拖拽`: 仅在画布层面选中高亮并触发光标更新, **不**自动切换左侧 Panel
  - `双击 I/O 节点 (globalInput / globalOutput)`: 自动在 SplitEditor 中打开对应的 `io/inputs.json` 或 `io/outputs.json` 文件, 并强制将左侧 Panel 切换至 `Input` 栏
  - `双击普通 Phase 节点 (skill)`: 自动在 SplitEditor 打开节点对应的 Markdown 文件 (`phases/<id>/<kind>.md`), 并强制将左侧 Panel 切换至 `Properties` 栏

### 2.5 右侧抽屉 (Right Panel / Copilot)
- **对应组件**: `CopilotPanel` (`apps/studio/frontend/src/components/copilot/copilot-panel.tsx:1`)
- **尺寸**: 默认 `20%`，可拖拽缩放，`minSize="18%"`, `maxSize="35%"`。
- **显示条件**: 当 `copilotOpen` 为 true 时显示。
- **包含功能**:
  - 聊天对话框区。
  - 模型切换器。Copilot 上下文的渐进式披露逻辑及 @ 引用交互体系不在 Layout 范畴内定义, 详见独立 spec [TBD: copilot-context-design]。
- **交互互动**: 受 Header 中的按钮控制；它能够感知 Main Panel 中被选中的 `selectedNodeId`。

## 3. Layout 状态机

Studio 的布局受一系列核心状态控制，构成以下布局矩阵：

1. **No-Skill Loaded (初始态)**
   - **Header**: 只有 Logo 和空的 Nav。
   - **Toolbar**: 始终保持显示 (提供 Settings 全局设置入口)。
   - **Main Panel**: 渲染 `WelcomePage`。
   - **Left Panel**: 隐藏。Right Panel: 根据 copilotOpen 状态决定显示与否 (即使没有加载 Skill, 用户仍可唤起 Copilot 询问全局问题)。
2. **Skill-Loaded Canvas View (顶层视图)**
   - **Header**: 仅显示顶层 Workspace 名称 (无面包屑)。
   - **Toolbar**: 显示，默认激活 `assets`。
   - **Left Panel**: 渲染 `AssetsPanel` (文件树)。
   - **Main Panel**: 渲染 GraphCanvas, 顶部面包屑隐藏, 底部浮现 CenterActionBar。
   - **Right Panel**: 根据 `copilotOpen` 决定。
3. **Skill-Loaded Subgraph View (下钻视图)**
   - **触发条件**: 从父级画布双击 Subgraph 节点下钻 (代码现状: `pushNavSkill` 已实现但暂无调 用点, 实现见后续 canvas-micro-topology-v1 spec)。
   - **Header**: 保持顶层 Workspace 名称。
   - **Main Panel**: Canvas 渲染子图, 顶部**显现面包屑导航条** (如 `Home Skill > Data Extractor Node`), 用户可点面包屑某段回退到该层。
4. **Skill-Loaded Editor View (代码编辑态)**
   - **4.a 默认单 Editor 态**:
     - **触发条件**: 从 AssetsPanel 中**单击**某个文件。
     - **Main Panel**: 渲染 Monaco 单一全屏编辑窗口, GraphCanvas 被替换。
   - **4.b Split Editor 态 (双屏对比)**:
     - **触发条件**: 在单 Editor 态下, 用户点击**编辑器右上角的 Split 分屏按钮** (`SplitEditor.tsx:59` 的 `onSplit`)。
     - **Main Panel**: 切分为左右双 Editor 槽位, 左侧保持当前文件, 右侧开辟新槽位供双文件对比。
     - **注**: 两窗口的 focus state 与"选中窗口点击文件就在该窗口打开"的高阶交互见独立 spec [TBD: split-editor-focus-enhancement]。
5. **Settings View (全局设置态)**
   - **触发条件**: 点击 Toolbar 底部的齿轮。
   - **Main Panel**: 完全被 `SettingsPage` 覆盖，屏蔽掉后方的 Canvas 或 Editor。
   - **包含组件**: 内部使用 Tab 切换 (General / API Keys / LLM Roles)。在 API Keys 下，由 ProviderCard 列表与 AddProviderForm 组件负责交互。

## 4. View 模式切换
当前仅有单一的 Edit View。Run 执行时, Trace 瀑布流的呈现将占据 Left Panel 中的一个平级标签页 (Trace Timeline, 与 Assets / Properties 平级, 通过 Toolbar 的 Trace Timeline 图标切换), 不强制触发横向全屏遮盖模式。Timeline 当前是 stub (`Panels.tsx:353` "Timeline view coming soon"), 具体渲染细节见 trace-and-predict-visibility 规范。

## 5. 已知 layout 反模式 (TODOs)
在审计 `apps/studio/frontend/src/` 代码树时，发现以下 Hygiene 问题，建议在后续实施中重构：
- **`Panels.tsx` 文件过于臃肿**: 里面挤压了 `AssetsPanel`, `PanelHeader`, `FolderRow`, `FileRow` 等多个功能相去甚远的组件。应按照子目录拆分至 `src/components/studio/panels/assets-panel.tsx` 等。
- **`Workspace.tsx` 逻辑过度耦合**: 这个文件近 500 行，承担了 WebSocket 连接、Compile 触发、状态管理和全局布局等过多职责。应该抽离出 `useWorkspaceSockets` 和 `useWorkspaceLayout` 等自定义 hooks。
- **[TODO: 砍除 ConflictDialog 与整个 conflict 机制]**: 按 §0.1 设计原则 "本地文件 = 唯一真相", 当前代码中的 `ConflictDialog` (`apps/studio/frontend/src/components/studio/ConflictDialog.tsx` + `WorkspaceContext.tsx` 的 `SaveConflict` 类型 + `Workspace.tsx:234` 的 `setConflict`  触发) 整个机制都是基于错误产品假设构建的, 应整体彻底砍除。WebSocket 接收到 `skill_changed` 事件应直接驱动 UI 无感 hot reload, 不弹任何提示。
- **[TODO: 清理连带的 inFlight 保存与 diff 逻辑]**: 既然 SSoT 是本地文件且没有 conflict 概念, `inFlight` 在途保存防并发竞争的检测机制也失去了存在意义。随着 ConflictDialog 的砍除, 其挂载 的副作用函数 `handleViewDiff` (`Workspace.tsx:186`) 及相关的 Editor Diff 模式也变为死代码 (Dead Code), 应当一并顺势清理。

## 相关 Spec
- [studio-uikit-redesign](../../.kiro/specs/studio-uikit-redesign/design.md)
- [studio-frontend-v21-multifile-editor](../../.kiro/specs/studio-frontend-v21-multifile-editor/design.md)
- [copilot-context-design](../../.kiro/specs/copilot-context-design/requirements.md)
- [split-editor-focus-enhancement](../../.kiro/specs/split-editor-focus-enhancement/requirements.md)
