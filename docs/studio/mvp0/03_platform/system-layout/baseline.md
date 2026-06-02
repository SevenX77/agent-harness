# studio-layout (studio system-level) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: 全局 React Shell 区域切割、Resizable 面板通信、Context 派发
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

当前 Studio layout 是一个桌面 IDE 风格的单页 shell。

它的根组件是 `Workspace`。

外层结构是:

- 顶部 Header。
- 下方主体横向 flex。
- 左侧 48px Toolbar。
- 可选 Left Panel。
- Center Panel。
- 可选 Right Copilot Panel。
- 全局 ConflictDialog。

对应代码:
`apps/studio/frontend/src/components/studio/Workspace.tsx:337`
`apps/studio/frontend/src/components/studio/Workspace.tsx:340`
`apps/studio/frontend/src/components/studio/Workspace.tsx:352`
`apps/studio/frontend/src/components/studio/Workspace.tsx:353`
`apps/studio/frontend/src/components/studio/Workspace.tsx:359`
`apps/studio/frontend/src/components/studio/Workspace.tsx:441`

Header 当前包含:

- 左侧 home/logo 按钮。
- 当前 skill / nav 信息。
- Draft badge。
- Save / Sync / Submit for Review / Release 菜单。
- Copilot toggle。

代码位置:
`apps/studio/frontend/src/components/studio/Header.tsx:25`
`apps/studio/frontend/src/components/studio/Header.tsx:58`
`apps/studio/frontend/src/components/studio/Header.tsx:107`
`apps/studio/frontend/src/components/studio/Header.tsx:111`
`apps/studio/frontend/src/components/studio/Header.tsx:115`
`apps/studio/frontend/src/components/studio/Header.tsx:121`
`apps/studio/frontend/src/components/studio/Header.tsx:132`

Toolbar 是固定宽度左侧工具条。

它的 panel 枚举是:

- `assets`
- `input`
- `timeline`
- `properties`
- `local-history`

代码位置:
`apps/studio/frontend/src/components/studio/Toolbar.tsx:7`
`apps/studio/frontend/src/components/studio/Toolbar.tsx:15`
`apps/studio/frontend/src/components/studio/Toolbar.tsx:20`

Toolbar 点击逻辑是“点已激活图标会隐藏 Left Panel, 点其它图标会切换面板”。

代码位置:
`apps/studio/frontend/src/components/studio/Toolbar.tsx:34`
`apps/studio/frontend/src/components/studio/Toolbar.tsx:37`

Left Panel 不是永远存在。

只有 `activePanel` 非空时才渲染。

代码位置:
`apps/studio/frontend/src/components/studio/Workspace.tsx:364`
`apps/studio/frontend/src/components/studio/Workspace.tsx:366`
`apps/studio/frontend/src/components/studio/Workspace.tsx:372`

Left Panel 的真实组件路由由 `Panels` 完成:
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:19`
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:30`
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:33`
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:36`
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:39`
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:42`

Assets panel 当前是从 `skillDetail.files` 构建的树。

它按文件夹优先、名称排序:
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:33`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:56`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:60`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:82`

Input panel 当前提供 input/schema 文件入口和 JSON schema infer 小工具:
`apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:18`
`apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:72`
`apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:82`
`apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:87`

Timeline panel 当前不是空 stub, 但只是静态 sample traces。

它不读取真实 run 数据:
`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:5`
`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:6`
`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:17`

Properties panel 当前只看选中节点。

它显示节点 label、模式、依赖、role、tools、subagents、文件路径:
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:83`
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:97`
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:103`
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:108`
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:109`

Audit High-003 的真实状态:

Properties panel 里没有 Context Inspector。

没有任何 `edge payload`、`edge data packet`、`Context Dictionary` 的 panel 态。

`GraphCanvas` 当前也没有 edge click handler。

因此旧 UX 文档中“点击连线数据包后 Properties 切换为 Context Inspector”的说法不符合当前代码。

Center Panel 是主工作区。

它在四种视图之间互斥:

- SettingsPage。
- SplitEditor。
- WelcomePage。
- GraphCanvas。

代码位置:
`apps/studio/frontend/src/components/studio/Workspace.tsx:383`
`apps/studio/frontend/src/components/studio/Workspace.tsx:385`
`apps/studio/frontend/src/components/studio/Workspace.tsx:386`
`apps/studio/frontend/src/components/studio/Workspace.tsx:387`
`apps/studio/frontend/src/components/studio/Workspace.tsx:388`
`apps/studio/frontend/src/components/studio/Workspace.tsx:397`
`apps/studio/frontend/src/components/studio/Workspace.tsx:400`

Center Panel 还叠加了底部 compile 错误面板和中心操作栏:
`apps/studio/frontend/src/components/studio/Workspace.tsx:410`
`apps/studio/frontend/src/components/studio/Workspace.tsx:412`
`apps/studio/frontend/src/components/studio/Workspace.tsx:415`

Right Panel 是 Copilot。

只有 `copilotOpen` 为真时渲染:
`apps/studio/frontend/src/components/studio/Workspace.tsx:426`
`apps/studio/frontend/src/components/studio/Workspace.tsx:429`
`apps/studio/frontend/src/components/studio/Workspace.tsx:435`

## 前端逻辑

当前 layout 使用 `react-resizable-panels` 的本地封装组件。

`Workspace` 导入 `ResizablePanelGroup`、`ResizablePanel`、`ResizableHandle`:
`apps/studio/frontend/src/components/studio/Workspace.tsx:3`

主 shell 是横向 group:
`apps/studio/frontend/src/components/studio/Workspace.tsx:359`
`apps/studio/frontend/src/components/studio/Workspace.tsx:360`
`apps/studio/frontend/src/components/studio/Workspace.tsx:361`

Left Panel 的尺寸配置是:

- default 20%。
- min 14%。
- max 35%。

代码位置:
`apps/studio/frontend/src/components/studio/Workspace.tsx:366`
`apps/studio/frontend/src/components/studio/Workspace.tsx:368`
`apps/studio/frontend/src/components/studio/Workspace.tsx:369`
`apps/studio/frontend/src/components/studio/Workspace.tsx:370`

Center Panel 的尺寸配置是:

- Copilot 打开时 default 60%。
- Copilot 关闭时 default 80%。
- min 30%。

代码位置:
`apps/studio/frontend/src/components/studio/Workspace.tsx:383`

Right Copilot Panel 的尺寸配置是:

- default 20%。
- min 18%。
- max 35%。

代码位置:
`apps/studio/frontend/src/components/studio/Workspace.tsx:429`
`apps/studio/frontend/src/components/studio/Workspace.tsx:431`
`apps/studio/frontend/src/components/studio/Workspace.tsx:432`
`apps/studio/frontend/src/components/studio/Workspace.tsx:433`

当前没有看到显式 localStorage 持久化 panel size 的代码。

`ResizablePanelGroup` 有 id, 但本文件没有 `autoSaveId` 或自定义持久化逻辑。

所以 baseline 只说“可 resize”, 不说“尺寸持久化”。

SplitEditor 内部也用 resizable panels。

它先上下切:

- top editor 70%。
- bottom mini graph 30%。

代码位置:
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:68`
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:73`
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:89`

当 splitMode 开启时, top editor 再左右切:

- left 50%。
- right 50%。

代码位置:
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:75`
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:76`
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:80`

`WorkspaceProvider` 是 layout 内通信的主要 Context。

它包住整个 shell:
`apps/studio/frontend/src/components/studio/Workspace.tsx:338`
`apps/studio/frontend/src/components/studio/Workspace.tsx:448`

Context value 包含:

- currentSkillId。
- navStack。
- active file paths。
- active file details。
- splitMode。
- onFileOpen。
- openSplitEditor。
- closeFile。
- updateFileContent。
- markFileSaved。
- setFileInFlight。
- onSaveConflict。
- reloadOpenFile。
- pushNavSkill。
- popNavTo。

代码位置:
`apps/studio/frontend/src/components/studio/Workspace.tsx:258`
`apps/studio/frontend/src/components/studio/Workspace.tsx:259`
`apps/studio/frontend/src/components/studio/Workspace.tsx:260`
`apps/studio/frontend/src/components/studio/Workspace.tsx:261`
`apps/studio/frontend/src/components/studio/Workspace.tsx:265`
`apps/studio/frontend/src/components/studio/Workspace.tsx:266`
`apps/studio/frontend/src/components/studio/Workspace.tsx:267`
`apps/studio/frontend/src/components/studio/Workspace.tsx:268`
`apps/studio/frontend/src/components/studio/Workspace.tsx:269`
`apps/studio/frontend/src/components/studio/Workspace.tsx:270`
`apps/studio/frontend/src/components/studio/Workspace.tsx:271`
`apps/studio/frontend/src/components/studio/Workspace.tsx:272`
`apps/studio/frontend/src/components/studio/Workspace.tsx:273`
`apps/studio/frontend/src/components/studio/Workspace.tsx:274`
`apps/studio/frontend/src/components/studio/Workspace.tsx:275`
`apps/studio/frontend/src/components/studio/Workspace.tsx:276`

Context 类型定义在 `WorkspaceContext`:
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:22`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:40`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:42`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:44`

AssetsPanel 从 Context 取 `onFileOpen`。

用户点击 FileRow 后会进入编辑器:
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:82`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:83`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:85`

Panels 也从 Context 取 `onFileOpen`, 再传给 InputPanel / PropertiesPanel:
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:20`
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:34`
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:43`

GraphCanvas 通过 optional WorkspaceContext 打开文件。

这样 GraphCanvas 可以在正常 Workspace 中打开文件, 也能在测试或独立渲染时不崩:
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:21`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:58`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:202`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:208`

Copilot context 不是 `WorkspaceContext` 的字段。

它通过 `useCopilotContext` 单独发布:
`apps/studio/frontend/src/components/studio/Workspace.tsx:65`
`apps/studio/frontend/src/components/studio/Workspace.tsx:69`
`apps/studio/frontend/src/components/studio/Workspace.tsx:78`

Header 里的 Save / Sync / Review / Release 走 `useSkillSync`。

这些不改变 layout 切面, 但会影响右上角菜单 loading:
`apps/studio/frontend/src/components/studio/Header.tsx:12`
`apps/studio/frontend/src/components/studio/Header.tsx:34`
`apps/studio/frontend/src/components/studio/Header.tsx:36`
`apps/studio/frontend/src/components/studio/Header.tsx:42`

Settings 是 center overlay 态。

Toolbar 底部按钮只设置 `settingsOpen`, 然后 center 互斥渲染 SettingsPage:
`apps/studio/frontend/src/components/studio/Toolbar.tsx:80`
`apps/studio/frontend/src/components/studio/Toolbar.tsx:85`
`apps/studio/frontend/src/components/studio/Workspace.tsx:54`
`apps/studio/frontend/src/components/studio/Workspace.tsx:356`
`apps/studio/frontend/src/components/studio/Workspace.tsx:385`

## 后端功能

Layout 本身主要是前端结构。

但它依赖后端提供这些数据和事件:

- skill list / detail。
- compile result。
- file change event。
- run stream。
- terminal stream。
- settings / llm 配置。

后端 router 在 app 创建时统一挂载:
`apps/studio/backend/app/main.py:124`
`apps/studio/backend/app/main.py:127`
`apps/studio/backend/app/main.py:129`
`apps/studio/backend/app/main.py:134`
`apps/studio/backend/app/main.py:135`
`apps/studio/backend/app/main.py:138`

`Workspace` 的 view 切换依赖 `SkillDetail`。

后端 `get_skill` 返回 `SkillDetail`:
`apps/studio/backend/app/routers/skills.py:98`
`apps/studio/backend/app/routers/skills.py:105`

`SkillDetail` 包含 `files`。

这让 AssetsPanel 和 editor 不需要 Tauri 直接读目录:
`apps/studio/backend/app/models/skills.py:39`
`apps/studio/backend/app/models/skills.py:46`
`apps/studio/backend/app/models/skills.py:47`

后端 file watcher 负责把磁盘变化转换成 `skill_changed` 事件。

Layout 中打开的编辑器通过这个事件热更新或弹 conflict:
`apps/studio/backend/app/services/file_watcher.py:23`
`apps/studio/backend/app/services/file_watcher.py:64`
`apps/studio/backend/app/services/file_watcher.py:82`
`apps/studio/backend/app/services/file_watcher.py:125`
`apps/studio/backend/app/services/file_watcher.py:126`

后端 websocket router 把事件推给前端:
`apps/studio/backend/app/routers/websockets.py:50`
`apps/studio/backend/app/routers/websockets.py:58`
`apps/studio/backend/app/routers/websockets.py:60`
`apps/studio/backend/app/routers/websockets.py:61`

Compile error panel 的数据来自后端 compile contract。

后端 compile endpoint 成功时返回 `CompileSuccess`, 失败时返回 422 JSON:
`apps/studio/backend/app/routers/skills.py:108`
`apps/studio/backend/app/routers/skills.py:116`
`apps/studio/backend/app/routers/skills.py:118`

## API

Layout 组件不直接定义 API, 但它的渲染状态依赖这些前端 API helper:

`fetcher`

SWR 通用读取函数:
`apps/studio/frontend/src/api/client.ts:56`
`apps/studio/frontend/src/api/client.ts:57`

`getSkillDetail`

用于 WebSocket 外部变化后重新拉取 detail:
`apps/studio/frontend/src/api/client.ts:157`
`apps/studio/frontend/src/components/studio/Workspace.tsx:229`

`writeSkillFile`

用于 LazyMonacoPanel 自动保存:
`apps/studio/frontend/src/api/client.ts:162`
`apps/studio/frontend/src/api/client.ts:169`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:106`

`compileSkill`

用于中心操作栏:
`apps/studio/frontend/src/api/client.ts:81`
`apps/studio/frontend/src/components/studio/Workspace.tsx:297`

`wsUrl`

用于构造 authenticated WebSocket URL:
`apps/studio/frontend/src/api/client.ts:101`
`apps/studio/frontend/src/api/client.ts:106`
`apps/studio/frontend/src/components/studio/Workspace.tsx:220`

Tauri shell API 对 layout 的影响有限。

Header/Welcome 的桌面打开能力通过 `lib/tauri.ts` 封装:
`apps/studio/frontend/src/lib/tauri.ts:4`
`apps/studio/frontend/src/lib/tauri.ts:19`
`apps/studio/frontend/src/lib/tauri.ts:38`
`apps/studio/frontend/src/lib/tauri.ts:64`

Rust 侧只注册 sidecar、open/reveal 相关命令:
`apps/studio/tauri/src/lib.rs:15`
`apps/studio/tauri/src/lib.rs:35`
`apps/studio/tauri/src/lib.rs:62`
`apps/studio/tauri/src/lib.rs:72`
`apps/studio/tauri/src/lib.rs:101`
`apps/studio/tauri/src/lib.rs:150`
`apps/studio/tauri/src/lib.rs:156`

当前不存在一个 Tauri layout provider 或 native panel API。

## Data Model / State

Layout 的一层状态在 `Workspace` 本地:

- `navStack`
- `activePanel`
- `copilotOpen`
- `activeFileDetails`
- `splitMode`
- `settingsOpen`
- `selectedNodeId`
- `selectedNode`
- `inFlight`
- `conflict`

代码位置:
`apps/studio/frontend/src/components/studio/Workspace.tsx:36`
`apps/studio/frontend/src/components/studio/Workspace.tsx:37`
`apps/studio/frontend/src/components/studio/Workspace.tsx:38`
`apps/studio/frontend/src/components/studio/Workspace.tsx:52`
`apps/studio/frontend/src/components/studio/Workspace.tsx:53`
`apps/studio/frontend/src/components/studio/Workspace.tsx:54`
`apps/studio/frontend/src/components/studio/Workspace.tsx:55`
`apps/studio/frontend/src/components/studio/Workspace.tsx:56`
`apps/studio/frontend/src/components/studio/Workspace.tsx:57`
`apps/studio/frontend/src/components/studio/Workspace.tsx:59`

`PanelKind` 是 Left Panel 的状态枚举。

它直接限制 Toolbar 和 Panels 的可选值:
`apps/studio/frontend/src/components/studio/Toolbar.tsx:7`
`apps/studio/frontend/src/components/studio/panels/Panels.tsx:12`

`OpenFile` 是 editor layout 的核心状态。

它记录当前文件来自哪个 skill、内容 hash、title、是否允许保存:
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:6`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:8`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:9`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:10`

`SaveConflict` 是 modal layout 的状态对象。

只要 `conflict` 非空, `ConflictDialog` 打开:
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:13`
`apps/studio/frontend/src/components/studio/ConflictDialog.tsx:19`
`apps/studio/frontend/src/components/studio/ConflictDialog.tsx:21`
`apps/studio/frontend/src/components/studio/Workspace.tsx:441`

GraphCanvas 内部也有局部 layout 状态:

- expandedSubgraphs。
- selectedCanvasNodeId。
- canvasHeight。

代码位置:
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:59`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:60`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:61`

这些状态用于展开 subgraph、设置节点选中态、按高度调 compact ratio:
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:69`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:81`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:130`

Layout 没有集中式 Zustand store。

当前是 React local state + Context + SWR + session/localStorage 的混合模式。

SWR 保存远端 skill list/detail cache:
`apps/studio/frontend/src/hooks/useSkills.ts:7`
`apps/studio/frontend/src/hooks/useSkills.ts:15`

`localStorage` 保存 Recent skills:
`apps/studio/frontend/src/hooks/useRecentSkills.ts:9`
`apps/studio/frontend/src/hooks/useRecentSkills.ts:29`

`sessionStorage` 保存 lint status:
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:17`
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:26`

`SkillDetail` 后端模型是 layout 所有“有 skill 时”视图的数据底座:
`apps/studio/backend/app/models/skills.py:39`
`apps/studio/backend/app/models/skills.py:42`
`apps/studio/backend/app/models/skills.py:43`
`apps/studio/backend/app/models/skills.py:47`

## Cross-feature interaction

本文件记录 shell 和状态派发。

Panel 内具体业务应去对应 feature:

- Assets / editor 文件树: [multi-file-editor baseline](../../asset-explorer/baseline.md)
- GraphCanvas: [canvas-topology baseline](../../canvas-topology/baseline.md)
- Timeline: [trace-visualization baseline](../../trace-inspector/baseline.md)
- Copilot: [copilot-assistance baseline](../../copilot-chat/baseline.md)
- Settings API keys: [llm-provider-config baseline](../../03_platform/llm-gateway/baseline.md)

Audit High-003 在本文件的结论是:

当前 `properties` panel 只定义节点属性面板。

Context Inspector 不是当前 layout 的一个 panel state。
