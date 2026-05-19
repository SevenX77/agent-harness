# Studio Frontend V2 Technical Research

> 核心目标：填补 requirements.md 与即将出具的 design.md 之间的“未知”鸿沟。本文件非架构设计方案，亦非产品需求，而是基于当前 Frontend (apps/studio/frontend/src)、UIKit (apps/studio/uikit/src) 与 Backend (apps/studio/backend/app) 现状进行的最严苛的实证调研与 Gap 摸底分析。

## 1. 现状摸底与 Gap 分析

### 1.1 Frontend 旧组件处置清单 (V2 搬迁策略)
通过遍历 apps/studio/frontend/src/components/，以下是每一个老旧组件的 V2 命运裁决：

| 现有组件 (Frontend) | 当前状态与功能描述 | V2 处置决定 | 替换来源 (UIKit / 新建) | 技术理由与风险 |
|---|---|---|---|---|
| App.tsx (根入口) | 长达 907 行的巨石应用组件，内部纠缠了所有的 Modal 状态、面板显示隐藏逻辑及全局配置。 | **彻底重写** | uikit/workspace.tsx 的路由切分版 | 当前耦合极深，无法维护。V2 必须采用 React Router 拆分为 / (Home) 与 /skill/:id (Workspace) 两个完全隔离的顶级组件。 |
| WelcomeScreen.tsx | 提供最近打开列表及快捷入口，作为进入工作流的初始遮罩或视图。 | **重写并提级** | 简化后作为 / 独立路由页 | 目前它只是一个条件渲染组件，未来将作为 Dashboard 页面级入口，解耦核心工作区的加载负担。 |
| GraphCanvas.tsx | 基于 @xyflow/react 封装的画板组件，包含了基础的节点连线逻辑。 | **重写/合体** | uikit/canvas.tsx + uikit/panels.tsx (部分) | 原组件样式破败。V2 的 Canvas-first 策略要求引入高密度的节点样式、新的交互 Handle，以及在画板上对节点进行直接的弹窗或侧栏呼出。 |
| HeaderBar.tsx | 原版纯手工打磨的顶部导航，功能稀疏。 | **丢弃/替换** | uikit/header.tsx | UIKit 提供了基于 44px (h-11) 规范、蕴含复杂工具栏及 Theme 切换的高质量顶栏，需直接替代。 |
| SkillSidebar.tsx | 全局的技能列表侧边栏。 | **拆分重塑** | uikit/toolbar.tsx + uikit/panels.tsx | 根据 UX 契约，强隔离模式下不允许在工作区显示全局列表。左栏必须重塑为纯净的 Icon Toolbar + 可折叠属性面板。 |
| MonacoPanel.tsx | 编辑代码的载体，当前可能随页面一并打包。 | **保留底层/改造UI**| 融入 uikit/code-editor.tsx 逻辑 | 核心引擎不可丢，但调用层需剥离。因为将其嵌入不同 Panel 或弹窗内需要解决 Monaco 在重渲染时的高度塌陷和首次拉起的巨大耗时延迟问题。 |
| TracePanel.tsx | 用于呈现 WebSocket 推送回来的运行日志。 | **废弃重建** | 基于 uikit/panels.tsx (TimelinePanel) | 旧版多为横屏日志形式，V2 规范强制要求在竖直抽屉中渲染分层的树状 timeline 历史。 |
| SettingsPanel.tsx | 简单的配置面板。 | **升级替换** | 转换为 Settings Modal | V2 要求在 Modal 中提供全局模型配 Key 的界面，不再作为右侧常驻面板。 |
| PromptInspector.tsx | 查看 Prompt 解析详情的组件。 | **改造** | 原有组件套 Shadcn 外壳 | 逻辑复用，但 DOM 结构必须切入 ResizablePanel 或 Dialog 框架内。 |
| RightPanel.tsx | 旧版放置各种侧边小部件的容易。 | **抛弃** | uikit/panels.tsx | 原有的 Tab 管理与视觉极度不规范，改用 Resizable 拆分。 |
| RuntimeGate.tsx | 守护运行环境及依赖安装的组件。 | **保留逻辑** | - | 逻辑抽离，不再作为一个占据页面的全屏 Modal 阻塞渲染，而是以弹窗或静默 Banner 形态出现。 |
| TerminalPanel.tsx | 控制台输出容器。 | **拆分/融入 Trace** | 整合至 Trace 视图内 | 不再单独割裂为独立面板，降低用户注意力涣散。 |
| ToastStack.tsx | 弱弹窗。 | **抛弃** | sonner / Shadcn use-toast | 用原生 Shadcn 生态替代，降低维护成本。 |
| creator/* (目录) | 用于新技能向导的各种小组件。 | **合并至 Copilot** | Copilot Chat UI | V2 明确要求通过自然语言 create-skill prompt 生成，繁杂的旧向导作废。 |
| phaseform/* (目录) | 对应于节点属性的表单配置容器。 | **全面翻新** | uikit/panels.tsx (PropertiesPanel) | 抛弃原生表单样式，重写为高密度的 Shadcn Form。 |
| diff/* (目录) | 用于比较节点改动的弹窗或面板。 | **升级** | 独立 Compare View | 结合 uikit/split-editor.tsx 提供并排视图。 |

### 1.2 Frontend 旧 Hook 复用率评估
apps/studio/frontend/src/hooks/ 包含 18 个 hook：
- **可直接复用的数据流 Hook (约 40%)**: useSkills, useTemplates, useRunHistory, useGoldenDiff, useBatchRun。这些依赖 axios，契约稳定。
- **需重构的状态/UI Hook (约 60%)**: 
  - useTheme.ts: 废弃，改用 uikit 的 useSyncExternalStore 模式，确保跨 Tauri WebView 的无感同步。
  - useFocusTrap.ts / useTraceSelection.ts / useVirtualScroll.ts: 随着 UI 面板从手搓 div 转为 ResizablePanel 和 Dialog，此类手动管理 DOM 的 hook 大多需要被对应第三方库 (如 radix-ui) 替代。
  - usePhaseForm.ts / usePhaseSync.ts: 需要做轻微重构，以适配 Monaco 编辑器脱离全局 state 的组件内部状态流转。

### 1.3 Copilot V1 接口与 Requirements AC Gap 对照

| Requirements AC | 当前后端状态 | 前端需完成的支持 | 风险 / 备注 |
|---|---|---|---|
| **AC_CP_1** (切模型清 session) | 支持 PUT /credentials (T1.2) | 需在 Frontend 拦截切换，先清理 UI state 再发 PUT。 | 无明显风险。 |
| **AC_CP_2** (无 Key 灰显) | 支持 GET /credentials (T1.2) | ModelPicker 初始化需预载状态，依赖 React Suspense 或预检 API。 | 需确保阻断向未配置的 LLM 发起连接。 |
| **AC_CP_3** (View Context 防抖更新) | 支持 POST /context (T3.3) | 新增 useCopilotContext hook，监听 Router/SelectedNode。 | **需决策**: 防抖更新的 Payload 截断，建议超过 2KB 传引用。 |
| **AC_CP_4** (Tool Use UI) | 后端转译为 tool_use_start/result | 需重写 ChatBubble 组件来专门化渲染特殊 Message Block。 | React Markdown 对 HTML 混排的渲染可能与该 Block 冲突。 |
| **AC_CP_5** (V1.5 占位) | (纯前端展现) | UI 组件中硬编码 Disabled 选项和 Badge。 | 低风险。 |
| **AC_CP_6** (非编程问题兼容) | 后端 System Prompt 已调 (T2.5) | 前端不需要过滤问题。 | 低风险。 |
| **AC_CP_7** (双端直连路由) | 后端 copilot.py base_url (T2.2) | 仅需传递正确的 active_backend enum。 | 低风险。 |

### 1.4 Gap 分析表 (requirements.md 全 30 AC vs 当前 codebase)

通过逐一梳理 requirements.md 中的 30 项 AC，以下列出所有需解决的实施前障点：

| AC 编号与内容摘要 | 当前 Codebase 支持度 | V2 需要执行的动作及实证路径 |
|---|---|---|
| **AC_UI_1** (Radix-Mira Token 对齐) | 错乱 (旧版是 sky/slate 色调) | 彻底抛弃旧的 index.css，引入 UIKit 中的自定义主题。替换原有的 tailwind 配置体系。 |
| **AC_UI_2** (字体与标尺) | 缺失 (系统字体为主) | 引入 Inter 和 JetBrains Mono Variable 字体文件。全局清理并替换非标 margin/padding 为 gap-2 或 p-4。 |
| **AC_UI_3** (动画与交互反馈) | 缺失 | 补全 Tailwind animate-in 类群。为 React Flow Canvas 中的 running node 绑定 pulse-primary class。 |
| **AC_UI_4** (Z-index 栈纪律) | 混乱 (各写各的) | 建立全局 CSS Variables 约束 z-0 至 z-60。重构 Modal 与 Toolbar 时严查遮挡问题。 |
| **AC_UI_5** (外壳 44px/48px 与 Resizable 拆分) | 缺失 (Flex 硬拆) | 使用 react-resizable-panels 重写整个 Shell，设定 Header h-11，Toolbar w-12 的固定宽高限制。 |
| **AC_UI_6** (按钮与组件严苛标尺) | 漂移严重 | 搜索现有 apps/studio/frontend/src/components/，全局替换原有的不标准 Button 为 uikit Redesign 版本 (如 Toolbar 按 32px 限定)。 |
| **AC_FN_1** (强隔离双路由) | 缺失 (单页系统) | 配置 React Router v6+，设立 / 和 /skill/:id。原 App.tsx 作废。 |
| **AC_FN_2** (静默防抖 Compile + 红绿灯护栏) | 部分支持 (usePhaseSync) | 当 Monaco 失焦或键入停顿 800ms 后，触动 POST /lint。在顶部拦绘制 compilation 状态指示灯，用状态量锁定 Predict 的 disabled 属性。 |
| **AC_FN_3** (竖版 Timeline 与微观透视) | 缺失 (旧版横屏列表) | 将 TracePanel.tsx 推倒重来。结合 WebSocket 增量压入 List，实现点击 List Item 向侧边或 Modal 展开详情。 |
| **AC_FN_4** (Agent-Loop 下钻至 Prompt) | 局部支持 (PromptInspector) | 将 Prompt Inspector 的 3 Tab (Template/Vars/Rendered) 无缝挂载到 React Flow 节点的 OnClick 或 Tooltip 中。 |
| **AC_FN_5** (断点篡改与 Resume 恢复) | 缺失 | 在 Error/Pause 时，React Flow 的对应 Node 应呈现橘黄色。Edge 连线上应悬浮按钮，点击后利用 Monaco 呈现 Context JSON，支持保存并发起 POST /resume。 |
| **AC_FN_6** (Compare Diff 面板与一键 Publish) | 部分支持 (useGoldenDiff) | 重组视觉，左侧渲染现状，右侧渲染基准，并对接 git 的后端 API，成功后载入 canvas-confetti。 |
| **AC_CP_1** (常驻 Copilot 与会话生命周期) | 假消息数组状态 (frontend 现有代码 mock 测试数据) | 消除原有的假消息数组，将 Right Panel 固定划拨给 Copilot。监听模型切换事件，清空本地 messages 数组并触发 reset API。 |
| **AC_CP_2** (ModelPicker 鉴权呈现) | 缺失 | 载入并根据 GET /credentials 的返回，用 disable 属性锁定尚未配置 API Key 的 DropdownItem。 |
| **AC_CP_3** (View Context 防抖与历史隔离) | 缺失 | Frontend 需撰写钩子监听全局 Router 和 Active Node State。 |
| **AC_CP_4** (解析 tool_use 视觉) | 缺失 | 新写 React 组件拦截 WebSocket JSON，如果是 Tool 调用，渲染类似 Notion 的折叠栏。 |
| **AC_CP_5** (V1.5 占位符) | 缺失 | 前端代码硬编码 Gemini 和 OpenAI 并渲染徽章即可。 |
| **AC_CP_6** (通用问答前端不拦截) | 无动作要求 | 后端处理，前端只需如实呈现。 |
| **AC_CP_7** (双端直连) | 无动作要求 | 后端处理，前端只要请求时挂对枚举值。 |
| **AC_API_1** (旧钩子 useSkills/Recent) | 高度重构 | 需要将这些孤岛般的 Hook 与 React Flow Context Provider 及 React Router Loader 函数结合。 |
| **AC_API_2** (useTemplates) | 部分支持 | 只作为脚手架供 Copilot 调用，不再用作显式大表单向导。 |
| **AC_API_3** (useRunHistory) | 部分支持 | 对齐 Timeline 竖版重构进行数据映射。 |
| **AC_API_4** (useInputPlayground) | 部分支持 | 面板触发改为基于 Predict 按钮旁边的弹窗。 |
| **AC_API_5** (useGoldenDiff) | 部分支持 | 从抽屉剥离，放在独立的 Compare 主视口全屏页面进行查看。 |
| **AC_API_6** (useBatchRun/DraftPersist) | 部分支持 | 增加防抖保存配置的落盘校验逻辑。 |
| **AC_API_7** (useGlobalShortcuts) | 部分支持 | 拦截热键作用域，避免在 Monaco 内键入 / 或 ? 触发命令菜单。 |
| **AC_TR_1** (Tauri 外部 IDE 一键拉起) | 缺失 | Frontend 需调用 @tauri-apps/api/shell 的 Command.spawn() 拉起本地终端与 Cursor。 |
| **AC_TR_2** (配置透传至后端规避前端 FS 写) | 缺失 | 所有 Settings Modal 的保存行为必须映射至 PUT /api/copilot/credentials。严禁在 Frontend 使用 Tauri fs.writeTextFile 修改权限隔离文件。 |
| **AC_TR_3** (禁止 RTL 与 Logical Properties) | 局部风险 | 进行全局扫描，将硬编码的 ml-, mr- 以及 pr-, pl- 重构为 ms-, me-, ps-, pe-，确保拓展性。 |
| **AC_TR_4** (Tauri 拖拽抓手) | 缺失 | 在 Header 组件的顶级容器注入 data-tauri-drag-region 属性。 |

## 2. 关键技术点深度调研 (Must-Resolve for Design Phase)

### 2.1 React Router 架构选型实证
- **目标**: 将 900 行的 App.tsx 大杂烩切分为可路由、强隔离的多页面体系，确保 Tauri 环境下的极佳用户体验。
- **选型分析**:
  - BrowserRouter (基于 H5 History API): 路径美观 (/skill/123)，但在 Tauri 桌面打包（通过 file:// 协议或无服务端重定向机制加载 index.html）时，如果在该路由上尝试刷新（Cmd+R），会导致白屏 404，因为静态托管找不到该实际文件。
  - MemoryRouter (基于内存): 不受平台环境影响，完全不会 404，但缺陷是无法通过 URL 追踪状态，也不方便未来扩展 Deeplink（比如从通知栏一键拉起某个工程）。
  - HashRouter (基于井号锚点): 路径表现为 /#/skill/123。天然绕开 Tauri 文件系统刷新拦截，且能在当前实例的 session 中保留页面状态和栈回退能力。
- **调研决议**: **推荐采用 createHashRouter 结合 React Router v6.4+ 的 Data API 模式**。这能够既享受 loader 预获取数据的快感，又彻底免疫 Tauri 环境的 F5 刷新灾难。

### 2.2 ResizablePanelGroup 的多页面尺寸持久化
- **目标**: 用户在 Skill_A 调节的侧边栏宽度，如果在退出后进入 Skill_B 会丢失，极度影响心智。
- **底层支持**: @radix-ui/react-resizable-panels 默认支持通过 autoSaveId 向 localStorage 落盘面板宽高比例，其落盘 key 格式固定。
- **应对策略**: 必须在 workspace.tsx 的布局组件中，将当前技能的唯一标识符直接注入：
  ```tsx
  <ResizablePanelGroup autoSaveId={`workspace-layout-${skill_id}`} ...>
  ```
- **附加隐患**: 如果用户在多个项目中拖曳，localStorage 会积攒数百个布局废料，需在全局 WelcomeScreen 的 useEffect 中提供清理过期配置的小脚本。

### 2.3 Copilot Context (大视图数据量优化) 策略
- **问题 (Q1)**: 当我们在含有超大 Markdown 或 JSON 的视图（如几万字的日志 Trace 面板）停留时，每 500ms 发送全量文本会挤爆后端 Context 或浪费 Token。
- **推荐策略 (Threshold-based Reference)**: 
  - 前端拦截: 计算将要发送的 context_string 的长度。
  - 长度未及 2000 字符: 发送全量 content。
  - 长度超越 2000 字符: 发送 summary (前200字) 并在尾部追加提示：[内容被截断，请使用 Read 工具读取文件 /path/to/skill.md 或查询详细 run_id]。让后端 Agent 自己决定是否调工具溯源。

### 2.4 WebSocket 接入与重连
- **现有基建**: api/client.ts 已经有了 wsUrl helper，但这只解决了路径转换。
- **重连库**: 不建议手写重连。引入 react-use-websocket 或者手动封装一套带有 Exponential Backoff 的 hook (useRobustWebSocket)。Tauri 端因为休眠唤醒很容易断掉 socket。

### 2.5 撒花特效 (Publish)
- **选型**: 采用轻量级库 canvas-confetti (被广泛用于类似 Vercel 的部署特效中)。
- **兼容性**: 它是纯基于 HTML5 Canvas 的库，完美兼容 Tauri WebView，且在暗色模式下不会有边框撕裂。

### 2.6 Monaco Editor 的 Tauri 冷启动延迟灾难
- **问题探明**: monaco-editor 全量引入 (~5-10MB JS)，不仅极大拖慢 Vite 打包后的首屏 Parse 时间，还会导致 Tauri 应用白屏期加长。由于是桌面端，不再有网络 CDN 加载的延迟，真正的痛点在于引擎实例化时的内存分配阻塞。
- **应对方案 (React Lazy + Skeleton)**:
  - 必须强制使用 React.lazy 将 Editor 面板切包。
  - 核心包裹：
  ```tsx
  const MonacoCore = React.lazy(() => import("@monaco-editor/react"));
  export const LazyMonacoPanel = () => (
      <React.Suspense fallback={<div className="animate-pulse bg-muted h-full w-full" />}>
         <MonacoCore />
      </React.Suspense>
  )
  ```
  - 通过骨架屏 (Skeleton) 进行视觉缓冲，缓解卡顿的焦躁感。

### 2.7 React Flow 版本对齐与自定节点复用
- **现状**: 现 frontend 与 uikit 均使用 @xyflow/react。
- **行动**: V2 中可直接将 uikit 里写好的 SkillNode 作为独立模块迁移，需要补充针对 data.status 绑定的动画和语义类（即根据 Redesign Token 表应用正确的 tailwind classes）。这比在老代码上打补丁稳妥。

### 2.8 Schema 自动推导 (US-2.2) 选型
- **选项**: 纯前端 genson-js vs 调用后端的 /schema/infer (若有)。
- **决议建议**: 纯前端使用类似 genson-js 或手写的小型解析函数，避免为了简单的 JSON 结构推导而增加网络往返延迟。

### 2.9 Predict 后端 LLM 调用路径 (US-3.2)
- **现状**: copilot-v1 backend (T1-T3 已实现) 已接通 OpenRouter (Anthropic 兼容) + DeepSeek (Anthropic 兼容) 两条管线, 位于 `apps/studio/backend/app/services/copilot.py` + `routers/copilot/`。
- **User 决议 (2026-05-11)**: 砍掉 Mock LLM 整条特性, Predict 直接调真实 LLM API, 复用 copilot-v1 已接通的端点。Predict ↔ Run 仅在 UX 维度有别 (打磨 vs 完整 Trace), LLM 真实性维度无差别。
- **行动**: 前端 Predict 触发 = `POST /api/skills/{skill_id}/predict` (backend 路由复用), backend 内部走 copilot-v1 已有的 LLM client。**不需要前端单独建 mock=true / mock 端点**。该问题已 resolve, 从 Open Questions 移除。

### 2.10 全局快捷键在焦点冲突下的处置
- **风险**: useGlobalShortcuts 监听了键盘快捷键（如 / 或 ?）。但是，在 Monaco 代码编辑区内，用户同样可能键入 / 或 ?。
- **解决机制**: 必须在 Hook 层拦截 event.target。
  ```ts
  if (["INPUT", "TEXTAREA"].includes(document.activeElement.tagName) || document.activeElement.closest(".monaco-editor")) {
      return; // 放弃拦截，将按键交还给富文本层
  }
  ```

## 3. 风险与未知项清单 (Open Questions 梳理)

本节列出可能严重阻碍开发并在后续 Design 阶段必须给出最终一锤定音裁决的风险点。

1. **Trace Timeline 的高频更新 CPU 负荷 (Must-Fix)**
   - *源头*: 当 Agent-Loop 连续发起多轮检索，WebSocket 可能以 30Hz 的极高频注入更新状态。
   - *风险*: React 频繁 diff 将使得整个时间线树重排，致使 UI 僵死。
   - *方案预研*: 前端能否将推送状态缓冲到内存队列，通过 requestAnimationFrame 每 100ms 拉取最新的合并快照交给 React 重绘？这在 Design 阶段需要确立架构图。
2. **CopilotEvent 前后端模型漂移风险**
   - *源头*: 后端 Python 中 copilot.py 中定义的联合类型如果随模型能力增强增加新的变种（例如除了 text_delta 又多出个 image_delta）。
   - *风险*: 前端 TypeScript 的强类型检查一旦遇上未知字段可能导致整个气泡组件崩溃白屏。
   - *方案预研*: 必须在前端类型定义中允许并接纳 UnknownEvent 类型，并为其书写一个简单的备用 JSON 渲染降级兜底方案。
3. **多开 WebView 导致的 Tauri 同步撕裂**
   - *源头*: 用户通过点击开启了 2 个窗口分别编辑两个不相关 Skill。如果在 A 窗口使用全局 Settings 更改了 DeepSeek 的 API Key。
   - *风险*: 由于配置缓存在单例 Context 中，B 窗口的内存不知情，可能仍在用旧 Key 失败报错。
   - *方案预研*: useSyncExternalStore 能否挂载在浏览器的跨 Tab BroadcastChannel 机制上，从而实现对本进程内所有 Webview 的状态分发广播？

## 4. 历史 Spec 的决策遗产硬约束 (不可推翻法则)

本次 V2 的设计与重构行为必须不可动摇地承接以下既定共识：

1. **[studio-frontend-f4-api] - 审计脱离**: 完全剔除了与追踪溯源挂钩的企业级 Audit Stub (MVP3 顺延事项)。前端页面中不允许存在多余的 Audit Log 按钮、记录或任何埋点查询端点。
2. **[tauri-t2 & tauri-t3] - 本地操作系统约束**: 前端不能依赖跨端的网络缓存，所有的配置写操作交由 Python 的后端代理 (PUT /credentials 实施 chmod 600)，坚决不通过前端调用任何的 Tauri FileSystem API 干扰操作系统底层凭据策略。
3. **[studio-uikit-redesign] - Mono 黑白颜色体系与标尺**: 在 tokens.md 中经历两轮血辩最终落盘的实测结果：Demo 系统是 Mono 黑白的变种。前端绝不可以重新回到“以大紫为基调”的荒谬路径。深紫的主题色（Active Sidebar 等）在特定暗色组件中必须极致克制地按照 oklch(0.398 0.195 277.366) (Dark 模式) 和 oklch(0.511 0.262 276.966) (Light 模式) 进行渲染。
4. **[ux_workflow-01] - Home/Workspace 孤岛隔离**: 这是产品在首轮确定的用户心智核心理念。绝不可为了复用页面结构而将所有的导航打通。工作区内没有退出和查看其他项目的菜单列表。必须使用独立的路由页面挂载，这同样奠定了之前抛弃 BrowserRouter 的论点。
