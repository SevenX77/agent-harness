# Studio Frontend V2 Implementation Tasks

## §1 总览
- **Scope**: 重写 `apps/studio/frontend/**`；backend 0 改动，直接复用 copilot-v1 T1-T3；`apps/studio/uikit/**` 0 改动，仅作为锁版搬迁源。
- 总工时: **89.3h**，拆为 Stage 0-10。V2 的主要成本在 Router/Shell 重写、Edit/Run 两条主工作流、Copilot V1 四层集成。
- Spec 依据: 背景与工作流见 `.kiro/specs/studio-frontend-v2/requirements.md:3`；30 个 AC 见 `.kiro/specs/studio-frontend-v2/requirements.md:69`；旧组件处置见 `.kiro/specs/studio-frontend-v2/research.md:7`；旧 hook 复用见 `.kiro/specs/studio-frontend-v2/research.md:29`；架构边界见 `.kiro/specs/studio-frontend-v2/design.md:50`；文件清单见 `.kiro/specs/studio-frontend-v2/design.md:264`。
- Frontend 现状边界: `apps/studio/frontend/src/App.tsx` 是 907L monolith，按 `requirements.md:58` 与 `research.md:12` 重写为 `src/routes/`；沿用 `src/api/client.ts`；砍掉或重写 18 个 hooks 中的 UI/DOM 类 hook (`research.md:32`)。
- 关键拍板: Mock LLM 已砍，Predict 直接走真实 `POST /api/skills/{id}/runs/predict` (`research.md:143`, `design.md:318`)；Debug Resume 因无 backend `/resume` 降级为 UI 占位 (`design.md:155`, `design.md:348`)。
- 每个 task 均含路径、AC、估时、依赖、可独立 commit、实施细节；yes 表示完成后 frontend typecheck/lint/smoke 应可独立通过。
- AC 满足追踪见 §6；AC_FN_5 在 V2 只做 UI 完整 + backend OOS 降级。

## §2 Stage 拆分

## Stage 0: 前置环境验证 + 工程脚手架 (3.0h)
- **T0.1 验证依赖版本与安装基线**
  - 路径: `apps/studio/frontend/package.json` (检查 / 必要更新)
  - AC: AC_UI_5 (`requirements.md:76`), AC_FN_1 (`requirements.md:80`)
  - 估时: 0.7h
  - 依赖: 无
  - 可独立 commit: no
  - 实施细节: 验证 React Router v6.4+、`@xyflow/react`、`react-resizable-panels`、Monaco、Tauri API、sonner、canvas-confetti、react-use-websocket；HashRouter 是 Tauri 刷新安全前提 (`design.md:65`, `research.md:88`)。

- **T0.2 迁入 UIKit token / fonts / motion 基线**
  - 路径: `apps/studio/frontend/src/index.css` (重写)
  - AC: AC_UI_1 (`requirements.md:72`), AC_UI_2 (`requirements.md:73`), AC_UI_3 (`requirements.md:74`), AC_UI_6 (`requirements.md:77`)
  - 估时: 1.0h
  - 依赖: T0.1
  - 可独立 commit: yes
  - 实施细节: 迁入 radix-mira oklch、Inter Variable、JetBrains Mono Variable、pulse-primary、animate-in；禁止回退紫蓝主题，遵守 Mono 黑白硬约束 (`research.md:180`)。

- **T0.3 建立 routes / shell / lib / store 目录骨架**
  - 路径: `apps/studio/frontend/src/routes/**`, `src/lib/**`, `src/store/**` (新建)
  - AC: AC_FN_1 (`requirements.md:80`)
  - 估时: 0.8h
  - 依赖: T0.1
  - 可独立 commit: yes
  - 实施细节: 创建 `router.tsx`, `root.tsx`, `home.tsx`, `skill/layout.tsx`, `edit/predict/run/debug/eval.tsx`；目标结构对齐 `design.md:282`。

- **T0.4 建立验证脚本与 smoke 约定**
  - 路径: `apps/studio/frontend/package.json`, `apps/studio/frontend/scripts/**` (新增/更新)
  - AC: AC_UI_4 (`requirements.md:75`), AC_TR_4 (`requirements.md:109`)
  - 估时: 0.5h
  - 依赖: T0.2, T0.3
  - 可独立 commit: yes
  - 实施细节: 固化 typecheck/lint/Playwright/bundle analyze 命令；后续覆盖 Home、Edit、Predict、Run、Copilot、dark mode。

## Stage 1: Router + Layout Shell + Theme (11.0h)
- **T1.1 用 createHashRouter 替换 App.tsx**
  - 路径: `src/main.tsx`, `src/routes/router.tsx`, `src/App.tsx` (重写/删除)
  - AC: AC_FN_1 (`requirements.md:80`)
  - 估时: 1.5h
  - 依赖: T0.3
  - 可独立 commit: yes
  - 实施细节: 路由表包含 `/`, `/skill/:skillId/edit`, `/predict`, `/run/:runId?`, `/debug`, `/eval`, `/settings`；契约见 `design.md:70`。

- **T1.2 实现 RootLayout + Toast + ErrorBoundary**
  - 路径: `src/routes/root.tsx` (新建)
  - AC: AC_UI_4 (`requirements.md:75`), AC_FN_1 (`requirements.md:80`)
  - 估时: 1.0h
  - 依赖: T1.1
  - 可独立 commit: yes
  - 实施细节: Toast/Sonner 挂在 Router 根层，不能嵌入 Workspace，防止切页吞 Toast；设计约束见 `design.md:56`。

- **T1.3 实现 WorkspaceLayout 三栏 Resizable Shell**
  - 路径: `src/routes/skill/layout.tsx` (新建)
  - AC: AC_UI_5 (`requirements.md:76`), AC_FN_1 (`requirements.md:80`), AC_CP_1 (`requirements.md:88`)
  - 估时: 2.0h
  - 依赖: T1.1
  - 可独立 commit: yes
  - 实施细节: Header h-11、Toolbar w-12、left/center/right 三栏，Right rail 固定 Copilot always-on；布局映射见 `design.md:105`。

- **T1.4 搬迁 Header / Toolbar 并改为路由导航**
  - 路径: `src/components/studio/header.tsx`, `src/components/studio/toolbar.tsx` (新建)
  - AC: AC_UI_5 (`requirements.md:76`), AC_UI_6 (`requirements.md:77`), AC_TR_4 (`requirements.md:109`)
  - 估时: 1.7h
  - 依赖: T1.3
  - 可独立 commit: yes
  - 实施细节: Header 提供 Back to Home 与 `data-tauri-drag-region`；Toolbar 只做 workspace 内导航，不显示全局 skill list (`requirements.md:10`, `research.md:181`, `design.md:231`)。

- **T1.5 实现 theme store: useSyncExternalStore + OS dark mode**
  - 路径: `src/store/themeStore.ts`, `src/hooks/useTheme.ts` (新建/替换)
  - AC: AC_UI_1 (`requirements.md:72`)
  - 估时: 1.3h
  - 依赖: T0.2
  - 可独立 commit: yes
  - 实施细节: 废弃旧 hook，使用订阅机制同步 DOM root 与 Tauri/WebView 主题；决策见 `requirements.md:66`, `design.md:222`。

- **T1.6 实现 z-index / A11y / global shortcut 壳**
  - 路径: `src/index.css`, `src/hooks/useGlobalShortcuts.ts`, `src/components/shortcuts/**` (更新)
  - AC: AC_UI_4 (`requirements.md:75`), AC_API_7 (`requirements.md:103`)
  - 估时: 1.5h
  - 依赖: T1.2, T0.2
  - 可独立 commit: yes
  - 实施细节: z-0/10/20/40/50/60 纪律；`/` 打开命令中心、`?` 打开速查表；Monaco/Input 内不拦截 (`design.md:115`, `research.md:148`)。

- **T1.7 实现 Settings Modal credentials 壳**
  - 路径: `src/routes/settings.tsx`, `src/components/studio/settings-modal.tsx` (新建)
  - AC: AC_CP_2 (`requirements.md:89`), AC_TR_2 (`requirements.md:107`)
  - 估时: 1.5h
  - 依赖: T1.2
  - 可独立 commit: yes
  - 实施细节: Settings 只通过 backend GET/PUT credentials；严禁 Tauri FS 写凭据，硬约束见 `research.md:179`, `design.md:197`。

- **T1.8 建立 route-level lazy/code splitting**
  - 路径: `src/routes/router.tsx`, `vite.config.*` (更新)
  - AC: AC_UI_3 (`requirements.md:74`)
  - 估时: 0.5h
  - 依赖: T1.1
  - 可独立 commit: yes
  - 实施细节: 为 Monaco、React Flow、Diff、Copilot 大块预留 route lazy；bundle 预算见 `design.md:245`。

## Stage 2: 工作流 01 Discovery & Init / Home (5.0h)
- **T2.1 重写 Home Dashboard**
  - 路径: `src/routes/home.tsx`, `src/components/WelcomeScreen.tsx` (重写/删除)
  - AC: AC_FN_1 (`requirements.md:80`), AC_API_1 (`requirements.md:97`)
  - 估时: 1.5h
  - 依赖: T0.3
  - 可独立 commit: yes
  - 实施细节: Home 是独立 route，显示 Recent Skills；点击 `navigate("/skill/{id}/edit")`，对应 `design.md:128`。

- **T2.2 复用 useSkills/useRecentSkills loader**
  - 路径: `src/hooks/useSkills.ts`, `src/hooks/useRecentSkills.ts`, `src/routes/home.tsx` (改造)
  - AC: AC_API_1 (`requirements.md:97`)
  - 估时: 0.8h
  - 依赖: T2.1
  - 可独立 commit: yes
  - 实施细节: 数据 hook 保留 axios 契约，Home loader 负责预取；`GET /skills` 已在 `design.md:312` 验证。

- **T2.3 新建 Skill / 目录选择 / Tauri bridge**
  - 路径: `src/routes/home.tsx`, `src/lib/tauri.ts` (新建/更新)
  - AC: AC_FN_1 (`requirements.md:80`), AC_TR_1 (`requirements.md:106`)
  - 估时: 1.1h
  - 依赖: T2.1, T9.1
  - 可独立 commit: yes
  - 实施细节: 用户选目录后调用 `POST /skills` 并跳转 workspace；目录和 shell 行为只封装在 lib 层。

- **T2.4 接入 useTemplates 与空 Workspace Copilot 引导**
  - 路径: `src/hooks/useTemplates.ts`, `src/components/templates/**`, `src/components/copilot/copilot-panel.tsx` (改造)
  - AC: AC_API_2 (`requirements.md:98`), AC_CP_6 (`requirements.md:93`)
  - 估时: 1.1h
  - 依赖: T2.1, T8.5
  - 可独立 commit: yes
  - 实施细节: Templates 只作为可选脚手架，不恢复旧大表单；空 Skill 通过 Copilot create-skill prompt 引导 (`requirements.md:19`)。

- **T2.5 Home 清理过期 layout localStorage**
  - 路径: `src/routes/home.tsx` (更新)
  - AC: AC_FN_1 (`requirements.md:80`)
  - 估时: 0.5h
  - 依赖: T1.3, T2.1
  - 可独立 commit: yes
  - 实施细节: 清理 `workspace-layout-*` 过期 key；避免多 skill 面板比例垃圾累积，风险见 `research.md:96`。

## Stage 3: 工作流 02 Edit & Compile (14.0h)
- **T3.1 重写 GraphCanvas 到 Edit route**
  - 路径: `src/routes/skill/edit.tsx`, `src/components/GraphCanvas.tsx` (重写)
  - AC: AC_FN_2 (`requirements.md:81`), AC_FN_4 (`requirements.md:83`)
  - 估时: 2.0h
  - 依赖: T1.3
  - 可独立 commit: yes
  - 实施细节: 基于 `@xyflow/react` 与 uikit node/canvas 视觉重建；React Flow 复用见 `research.md:135`，Edit 契约见 `design.md:134`。

- **T3.2 实现 SkillNode 状态与 running 动画**
  - 路径: `src/components/studio/skill-node.tsx`, `src/index.css` (新建/更新)
  - AC: AC_UI_1 (`requirements.md:72`), AC_UI_3 (`requirements.md:74`)
  - 估时: 1.2h
  - 依赖: T3.1, T1.6
  - 可独立 commit: yes
  - 实施细节: idle/running/success/error/paused/breakpoint 映射 token；running 绑定 1.4s `pulse-primary`。

- **T3.3 实现 metadata / schema / node properties 面板**
  - 路径: `src/components/studio/properties-panel.tsx`, `src/hooks/usePhaseForm.ts` (改造)
  - AC: AC_FN_2 (`requirements.md:81`), AC_API_6 (`requirements.md:102`)
  - 估时: 1.7h
  - 依赖: T3.1
  - 可独立 commit: yes
  - 实施细节: 配置 name/description/type/Input/Output Schema、knowledge/tools/validator/retry 参数；旧 phaseform 做局部状态重构 (`research.md:35`)。

- **T3.4 实现 JSON 拖拽推导 Input Schema**
  - 路径: `src/lib/schema-infer.ts`, `src/components/studio/input-panel.tsx` (新建)
  - AC: AC_FN_2 (`requirements.md:81`)
  - 估时: 1.0h
  - 依赖: T3.3
  - 可独立 commit: yes
  - 实施细节: V2 先用前端推导 object/array/string/number/bool/null；Q4 复杂策略开工前 spike (`research.md:139`, `design.md:347`)。

- **T3.5 实现 depends_on/连线拓扑编辑 + Inline Expand**
  - 路径: `src/utils/graph.ts`, `src/components/studio/subgraph-inline.tsx` (改造/新建)
  - AC: AC_FN_2 (`requirements.md:81`), AC_FN_4 (`requirements.md:83`)
  - 估时: 2.0h
  - 依赖: T3.1
  - 可独立 commit: yes
  - 实施细节: 连线同步 graph model；子图仅做平层树状展开或新标签页，不做深层下钻，OOS 见 `requirements.md:112`。

- **T3.6 实现 LazyMonacoPanel 与 Agent prompt 编辑**
  - 路径: `src/components/studio/lazy-monaco-panel.tsx`, `src/components/MonacoPanel.tsx` (重写)
  - AC: AC_FN_2 (`requirements.md:81`), AC_UI_3 (`requirements.md:74`)
  - 估时: 1.5h
  - 依赖: T3.1
  - 可独立 commit: yes
  - 实施细节: Monaco 必须 React.lazy + Suspense skeleton，避免 Tauri 冷启动阻塞；方案见 `research.md:120`。

- **T3.7 接入 800ms 防抖 lint 与编译护栏**
  - 路径: `src/hooks/usePhaseSync.ts`, `src/components/studio/compilation-widget.tsx` (改造/新建)
  - AC: AC_FN_2 (`requirements.md:81`), AC_API_6 (`requirements.md:102`)
  - 估时: 2.0h
  - 依赖: T3.3, T3.5, T3.6
  - 可独立 commit: yes
  - 实施细节: onChange 停顿 800ms 或 Monaco blur 调 `POST /skills/{id}/lint`；失败锁 Predict/Run，端点见 `design.md:317`。

- **T3.8 接入 useDraftPersist 与 Edit Copilot context**
  - 路径: `src/hooks/useDraftPersist.ts`, `src/routes/skill/edit.tsx`, `src/hooks/useCopilotContext.ts` (改造)
  - AC: AC_API_6 (`requirements.md:102`), AC_CP_3 (`requirements.md:90`)
  - 估时: 1.6h
  - 依赖: T3.7, T8.4
  - 可独立 commit: yes
  - 实施细节: 本地 draft 与 lint 状态解耦；选中节点/当前文件/lint result 作为 view context，更新不清聊天历史。在本 view route 内接入 `useCopilotContext`, debounce 800ms 同步当前 view 到 backend。

- **T3.9 Edit workflow smoke**
  - 路径: `apps/studio/frontend/tests/e2e/edit.spec.ts` (新建)
  - AC: AC_FN_2, AC_FN_4, AC_UI_3
  - 估时: 1.0h
  - 依赖: T3.1-T3.8
  - 可独立 commit: yes
  - 实施细节: 覆盖连线、lint 绿/红、Monaco lazy、schema infer、subgraph expand、dark mode。

## Stage 4: 工作流 03 Predict & Baseline (9.0h)
- **T4.1 实现 Predict route 与主行动入口**
  - 路径: `src/routes/skill/predict.tsx` (新建)
  - AC: AC_FN_2 (`requirements.md:81`), AC_API_4 (`requirements.md:100`)
  - 估时: 1.0h
  - 依赖: T3.7
  - 可独立 commit: yes
  - 实施细节: Predict 只在 compile success 后解锁；页面契约见 `design.md:142`。

- **T4.2 嵌入 useInputPlayground 简化弹窗**
  - 路径: `src/hooks/useInputPlayground.ts`, `src/components/playground/**` (改造)
  - AC: AC_API_4 (`requirements.md:100`)
  - 估时: 1.3h
  - 依赖: T4.1, T3.4
  - 可独立 commit: yes
  - 实施细节: 文件选择、JSON 输入、schema 校验；输入验证端点 `POST /skills/{id}/validate_input` 见 `design.md:316`。

- **T4.3 接入真实 Predict API，移除 Mock LLM 路径**
  - 路径: `src/api/client.ts`, `src/routes/skill/predict.tsx` (更新)
  - AC: AC_FN_2 (`requirements.md:81`)
  - 估时: 1.2h
  - 依赖: T4.2
  - 可独立 commit: yes
  - 实施细节: 调 `POST /api/skills/{id}/runs/predict`，不传 mock flag、不建 mock endpoint；用户拍板见 `research.md:143`。

- **T4.4 实现 Predict 结果 + Golden 草稿分屏**
  - 路径: `src/components/studio/predict-split.tsx` (新建)
  - AC: AC_FN_6 (`requirements.md:85`), AC_API_5 (`requirements.md:101`)
  - 估时: 1.5h
  - 依赖: T4.3
  - 可独立 commit: yes
  - 实施细节: 左 Predict output，右 Golden draft；视觉复用 uikit split 思路，但业务是 baseline 打磨。

- **T4.5 实现 Save as Golden**
  - 路径: `src/routes/skill/predict.tsx`, `src/api/client.ts` (更新)
  - AC: AC_API_5 (`requirements.md:101`)
  - 估时: 1.0h
  - 依赖: T4.4
  - 可独立 commit: yes
  - 实施细节: 调 `POST /skills/{id}/golden/...` 保存基线；Golden API 见 `design.md:323`。

- **T4.6 Predict Copilot context + cancel 降级**
  - 路径: `src/routes/skill/predict.tsx`, `src/hooks/useCopilotContext.ts` (更新)
  - AC: AC_CP_3 (`requirements.md:90`), AC_CP_6 (`requirements.md:93`)
  - 估时: 1.2h
  - 依赖: T8.4, T4.4
  - 可独立 commit: yes
  - 实施细节: 上报输入、schema、Predict output、Golden draft 指纹；Q3 cancel 无后端则只做 loading/timeout/Toast，不伪造中断 (`design.md:346`)。在本 view route 内接入 `useCopilotContext`, debounce 800ms 同步当前 view 到 backend。

- **T4.7 Predict workflow smoke**
  - 路径: `apps/studio/frontend/tests/e2e/predict.spec.ts` (新建)
  - AC: AC_API_4, AC_API_5, AC_FN_2
  - 估时: 1.8h
  - 依赖: T4.1-T4.6
  - 可独立 commit: yes
  - 实施细节: 覆盖 no key、schema invalid、真实 predict loading、Save as Golden、dark mode。

## Stage 5: 工作流 04 Run & Trace (15.8h)
- **T5.1 实现 Run route 与 run 启动**
  - 路径: `src/routes/skill/run.tsx` (新建)
  - AC: AC_FN_3 (`requirements.md:82`), AC_API_3 (`requirements.md:99`)
  - 估时: 1.3h
  - 依赖: T3.7
  - 可独立 commit: yes
  - 实施细节: 调 `POST /skills/{id}/runs` 后进入 `/run/:runId`；Run API 见 `design.md:318`。

- **T5.2 重写 TracePanel 为竖向 Timeline + History**
  - 路径: `src/components/TracePanel.tsx`, `src/components/trace/**`, `src/hooks/useRunHistory.ts` (重写/改造)
  - AC: AC_FN_3 (`requirements.md:82`), AC_API_3 (`requirements.md:99`)
  - 估时: 2.2h
  - 依赖: T5.1
  - 可独立 commit: yes
  - 实施细节: 竖向 phase timeline 展示工具调用、LLM 耗时、token；History 支持快照回溯和 DELETE 清理 (`research.md:18`, `requirements.md:99`)。

- **T5.3a 接入 Run WebSocket + 100ms 合批 / exponential backoff**
  - 路径: `src/lib/websocket.ts`, `src/hooks/useRunStream.ts` (新建)
  - AC: AC_FN_3 (`requirements.md:82`)
  - 估时: 1.5h
  - 依赖: T5.1, T5.2
  - 可独立 commit: yes
  - 实施细节: 连接 `/ws/runs/{run_id}`；事件先入 queue，每 100ms setState；断流用 exponential backoff，见 `design.md:237`, `design.md:250`, `design.md:330`。

- **T5.3b Timeline 虚拟化 + 滚动定位**
  - 路径: `src/components/trace/VirtualTraceList.tsx` (改造)
  - AC: AC_FN_3 (`requirements.md:82`)
  - 估时: 2.5h
  - 依赖: T5.2, T5.3a
  - 可独立 commit: yes
  - 实施细节: 用 react-virtuoso 或等价虚拟化承载 1000+ trace items；保留按 selected event 滚动定位能力，见 `design.md:240`。

- **T5.4 实现 Micro-Topology + Prompt Inspector**
  - 路径: `src/components/studio/micro-topology-panel.tsx`, `src/components/PromptInspector.tsx` (新建/改造)
  - AC: AC_FN_4 (`requirements.md:83`)
  - 估时: 2.0h
  - 依赖: T5.2
  - 可独立 commit: yes
  - 实施细节: 单击 LLM 节点展示 working_memory/tool_calls/validator；Prompt Inspector 三 tab: Template/Variables/Rendered (`requirements.md:40`, `design.md:152`)。

- **T5.5 实现 Edge Context JSON Viewer**
  - 路径: `src/components/studio/edge-context-viewer.tsx` (新建)
  - AC: AC_FN_3 (`requirements.md:82`), AC_FN_5 (`requirements.md:84`)
  - 估时: 1.5h
  - 依赖: T5.1, T3.6
  - 可独立 commit: yes
  - 实施细节: 点击 Edge 圆点打开 readonly Monaco JSON Viewer；Debug route 中复用为 editable local draft。

- **T5.6 Run 状态同步到 Canvas 节点 + 网络退避**
  - 路径: `src/routes/skill/run.tsx`, `src/components/studio/skill-node.tsx`, `src/components/studio/network-banner.tsx` (更新/新建)
  - AC: AC_FN_3 (`requirements.md:82`), AC_UI_3 (`requirements.md:74`)
  - 估时: 1.5h
  - 依赖: T5.3a, T3.2
  - 可独立 commit: yes
  - 实施细节: WS events 驱动画布 Running/Paused/Failed/Success；断流指数退避 1s→30s，策略见 `design.md:250`。

- **T5.7 Run route Copilot context**
  - 路径: `src/routes/skill/run.tsx`, `src/hooks/useCopilotContext.ts` (更新)
  - AC: AC_CP_3 (`requirements.md:90`)
  - 估时: 0.8h
  - 依赖: T8.4, T5.2, T5.5
  - 可独立 commit: yes
  - 实施细节: 上报 selected trace item、run_id、edge context summary；大内容按 threshold + fingerprint 截断。在本 view route 内接入 `useCopilotContext`, debounce 800ms 同步当前 view 到 backend。

- **T5.8 Run/Trace workflow smoke**
  - 路径: `apps/studio/frontend/tests/e2e/run-trace.spec.ts` (新建)
  - AC: AC_FN_3, AC_FN_4, AC_API_3
  - 估时: 2.5h
  - 依赖: T5.1-T5.7
  - 可独立 commit: yes
  - 实施细节: 模拟 1000 trace items，验证滚动、选择、context viewer、micro-topology、dark mode、断流 UI。

## Stage 6: 工作流 05 Debug & Resume - UI 占位降级 (4.0h)
- **T6.1 实现 paused/error 节点黄色锁定 UI**
  - 路径: `src/routes/skill/debug.tsx`, `src/components/studio/skill-node.tsx` (新建/更新)
  - AC: AC_FN_5 (`requirements.md:84`) — V2 UI 占位降级
  - 估时: 1.0h
  - 依赖: T5.6
  - 可独立 commit: yes
  - 实施细节: 节点 yellow ring、局部 `[Resume]`、顶部 HitL/Error banner；真实 resume 不承诺，降级见 `design.md:155`。

- **T6.2 Resume Toast 占位 + 禁止网络请求**
  - 路径: `src/routes/skill/debug.tsx` (更新)
  - AC: AC_FN_5 (`requirements.md:84`) — V2 UI 占位降级
  - 估时: 0.7h
  - 依赖: T6.1
  - 可独立 commit: yes
  - 实施细节: 点击 Toast `"HitL Resume 待 backend 实现 (V3 范围)"`；不得调用 `/resume`，后端缺失见 `design.md:335`。

- **T6.3 Edge Monaco 编辑暂存 LocalStorage + 脏状态作废**
  - 路径: `src/components/studio/edge-context-viewer.tsx`, `src/hooks/useDraftPersist.ts`, `src/routes/skill/debug.tsx` (更新)
  - AC: AC_FN_5 (`requirements.md:84`)
  - 估时: 1.5h
  - 依赖: T5.5, T3.8
  - 可独立 commit: yes
  - 实施细节: Edge JSON 保存只写 localStorage；Pause 期间改相关 draft 后禁用 Resume placeholder，强制重新 Compile (`requirements.md:46`, `design.md:160`)。

- **T6.4 Debug Copilot context + 降级验收记录**
  - 路径: `src/routes/skill/debug.tsx`, `src/hooks/useCopilotContext.ts` (更新)
  - AC: AC_CP_3 (`requirements.md:90`), AC_FN_5 (`requirements.md:84`)
  - 估时: 0.8h
  - 依赖: T8.4, T6.1
  - 可独立 commit: yes
  - 实施细节: 上报 paused node、error summary、override fingerprint；PR/验收明确 AC_FN_5 是 UI 完整、backend OOS (`design.md:348`)。在本 view route 内接入 `useCopilotContext`, debounce 800ms 同步当前 view 到 backend。

## Stage 7: 工作流 06 Eval & Publish (7.0h)
- **T7.1 实现 Eval route 全屏 Diff Shell**
  - 路径: `src/routes/skill/eval.tsx` (新建)
  - AC: AC_FN_6 (`requirements.md:85`), AC_API_5 (`requirements.md:101`)
  - 估时: 1.2h
  - 依赖: T4.5, T5.2
  - 可独立 commit: yes
  - 实施细节: 隐藏画布，全屏 split-view，左 Artifact 当前产物、右 Golden Baseline；设计见 `design.md:162`。

- **T7.2 复用 useGoldenDiff 接 compare API**
  - 路径: `src/hooks/useGoldenDiff.ts`, `src/components/diff/**` (改造)
  - AC: AC_API_5 (`requirements.md:101`), AC_FN_6 (`requirements.md:85`)
  - 估时: 1.3h
  - 依赖: T7.1
  - 可独立 commit: yes
  - 实施细节: 调 `GET /api/skills/{id}/runs/{run_id}/compare`；端点见 `design.md:325`。

- **T7.3 升级结构化 JSON/Text Diff 呈现**
  - 路径: `src/components/diff/**` (改造)
  - AC: AC_FN_6 (`requirements.md:85`)
  - 估时: 1.0h
  - 依赖: T7.2
  - 可独立 commit: yes
  - 实施细节: 左右对齐代码与 JSON 数据级 diff，长文本折叠，遵守 modal/z-index 纪律。

- **T7.4 Copilot Judge + Eval context**
  - 路径: `src/routes/skill/eval.tsx`, `src/components/copilot/copilot-panel.tsx`, `src/hooks/useCopilotContext.ts` (更新)
  - AC: AC_FN_6 (`requirements.md:85`), AC_CP_3 (`requirements.md:90`), AC_CP_6 (`requirements.md:93`)
  - 估时: 1.0h
  - 依赖: T8.5, T7.2
  - 可独立 commit: yes
  - 实施细节: 将 diff summary 作为 context 或消息交给 Copilot judge，不新增后端 judge endpoint (`requirements.md:51`)。在本 view route 内接入 `useCopilotContext`, debounce 800ms 同步当前 view 到 backend。

- **T7.5 Publish Modal + confetti**
  - 路径: `src/components/studio/publish-modal.tsx`, `src/lib/confetti.ts`, `src/api/client.ts` (新建/更新)
  - AC: AC_FN_6 (`requirements.md:85`)
  - 估时: 1.2h
  - 依赖: T7.1
  - 可独立 commit: yes
  - 实施细节: Commit message 可选；成功后 `canvas-confetti` 撒花；若后端缺 publish API，不改 backend，页面降级标缺口 (`research.md:116`)。

- **T7.6 Eval/Publish smoke**
  - 路径: `apps/studio/frontend/tests/e2e/eval.spec.ts` (新建)
  - AC: AC_FN_6, AC_API_5
  - 估时: 1.3h
  - 依赖: T7.1-T7.5
  - 可独立 commit: yes
  - 实施细节: 覆盖 compare load、diff scroll、AI judge dispatch、publish success/failure、confetti dark mode。

## Stage 8: Copilot V1 集成层 (16.5h)
- **T8.1 定义 Copilot TS types 与 UnknownEvent**
  - 路径: `src/types/copilot.ts` (新建)
  - AC: AC_CP_4 (`requirements.md:91`)
  - 估时: 1.0h
  - 依赖: T1.2
  - 可独立 commit: yes
  - 实施细节: 定义 text_delta/tool_use_start/tool_use_result/done/error/unknown；避免后端 union 漂移白屏 (`research.md:165`)。

- **T8.2 实现 useCopilot WebSocket + message lifecycle**
  - 路径: `src/hooks/useCopilot.ts`, `src/store/copilotStore.ts` (新建)
  - AC: AC_CP_1 (`requirements.md:88`), AC_CP_4 (`requirements.md:91`), AC_CP_7 (`requirements.md:94`)
  - 估时: 2.6h
  - 依赖: T8.1
  - 可独立 commit: yes
  - 实施细节: 连接 `/api/skills/{id}/copilot/ws`；聊天仅 in-memory，skill/model 切换 reset；端点见 `design.md:329`。

- **T8.3 text_delta 聚合与 WS 重连**
  - 路径: `src/hooks/useCopilot.ts` (更新)
  - AC: AC_CP_1 (`requirements.md:88`), AC_CP_4 (`requirements.md:91`)
  - 估时: 1.2h
  - 依赖: T8.2
  - 可独立 commit: yes
  - 实施细节: text_delta 50-100ms 聚合；断流指数退避；性能与重连策略见 `design.md:243`, `design.md:250`。

- **T8.4 实现 useCopilotContext 防抖 + threshold + fingerprint**
  - 路径: `src/hooks/useCopilotContext.ts` (新建)
  - AC: AC_CP_3 (`requirements.md:90`)
  - 估时: 2.0h
  - 依赖: T8.2
  - 可独立 commit: yes
  - 实施细节: 监听 route/selected node/trace；800ms debounce，<=2048 全量，>2048 summary + fingerprint (`design.md:182`)。

- **T8.5 实现 CopilotPanel always-on UI**
  - 路径: `src/components/copilot/copilot-panel.tsx` (新建)
  - AC: AC_CP_1 (`requirements.md:88`), AC_CP_6 (`requirements.md:93`)
  - 估时: 2.0h
  - 依赖: T8.2, T1.3
  - 可独立 commit: yes
  - 实施细节: Right rail 永远渲染，不提供 close；标准 markdown 渲染 text_delta，通用问题不屏蔽。必须对消息历史列表子项 (`<ChatMessageItem />`) 施加 `React.memo`, 防止输入框 typing 时全列表 re-render。

- **T8.6 实现 ToolCallBubble + DiffBubble**
  - 路径: `src/components/copilot/tool-call-bubble.tsx`, `src/components/copilot/diff-bubble.tsx` (新建)
  - AC: AC_CP_4 (`requirements.md:91`)
  - 估时: 2.2h
  - 依赖: T8.1, T8.5
  - 可独立 commit: yes
  - 实施细节: tool_use_start 渲染“正在 Read/Write/Edit/Bash”；tool_use_result 渲染摘要和 diff，边界见 `design.md:191`。ToolCallBubble + DiffBubble 必须用 `React.memo` 包裹, props 比较包含 `event.id` + `event.status`。

- **T8.7 实现 credentials API + ModelPicker + Settings**
  - 路径: `src/api/copilot.ts`, `src/components/copilot/model-picker.tsx`, `src/components/copilot/copilot-settings.tsx` (新建)
  - AC: AC_CP_1 (`requirements.md:88`), AC_CP_2 (`requirements.md:89`), AC_CP_5 (`requirements.md:92`), AC_TR_2 (`requirements.md:107`)
  - 估时: 3.0h
  - 依赖: T1.7, T8.2
  - 可独立 commit: yes
  - 实施细节: GET/PUT credentials；未配 key 灰显 tooltip；Gemini/OpenAI disabled + V1.5 badge；切模型清 messages 并 Toast (`design.md:197`)。

- **T8.8 实现 error/unknown event 兜底呈现**
  - 路径: `src/components/copilot/copilot-panel.tsx` (更新)
  - AC: AC_CP_4 (`requirements.md:91`), AC_CP_6 (`requirements.md:93`)
  - 估时: 0.8h
  - 依赖: T8.5
  - 可独立 commit: yes
  - 实施细节: backend error event 以可恢复卡片展示；UnknownEvent 以 JSON fallback 呈现，不崩溃。

- **T8.9 Copilot integration smoke**
  - 路径: `apps/studio/frontend/tests/e2e/copilot.spec.ts` (新建)
  - AC: AC_CP_1, AC_CP_2, AC_CP_3, AC_CP_4, AC_CP_5, AC_CP_6, AC_CP_7
  - 估时: 1.7h
  - 依赖: T8.1-T8.8
  - 可独立 commit: yes
  - 实施细节: 覆盖 model switch reset、disabled key、context debounce、tool bubble、diff bubble、unknown event、dark mode。

## Stage 9: Tauri 集成 + 边角 (5.0h)
- **T9.1 封装 Tauri shell API**
  - 路径: `src/lib/tauri.ts` (新建)
  - AC: AC_TR_1 (`requirements.md:106`)
  - 估时: 1.0h
  - 依赖: T0.1
  - 可独立 commit: yes
  - 实施细节: 封装 `openInCursor`, `openInTerminal`, `openInCodex`；Web 环境 no-op + Toast；示例见 `design.md:206`。

- **T9.2 接入 IDE buttons 与 production refresh smoke**
  - 路径: `src/components/studio/header.tsx`, `src/components/studio/toolbar.tsx`, `tests/e2e/tauri.spec.ts` (更新/新建)
  - AC: AC_TR_1 (`requirements.md:106`), AC_TR_4 (`requirements.md:109`)
  - 估时: 1.2h
  - 依赖: T9.1, T1.4
  - 可独立 commit: yes
  - 实施细节: 三个 IDE button 使用当前 skill path；`/#/skill/:id/edit` 刷新不白屏，见 `design.md:228`。

- **T9.3 前端禁止 Tauri FS 写凭据扫描**
  - 路径: `apps/studio/frontend/src/**` (扫描/修正)
  - AC: AC_TR_2 (`requirements.md:107`)
  - 估时: 0.7h
  - 依赖: T8.7
  - 可独立 commit: yes
  - 实施细节: `rg "@tauri-apps/api/fs|writeTextFile|BaseDirectory"` 不得命中 credentials 写入；凭据只走 HTTP (`research.md:178`)。

- **T9.4 RTL/logical properties 与 A11y 扫描**
  - 路径: `src/components/**`, `src/routes/**` (更新)
  - AC: AC_TR_3 (`requirements.md:108`), AC_UI_6 (`requirements.md:77`)
  - 估时: 1.2h
  - 依赖: T1.3
  - 可独立 commit: yes
  - 实施细节: 审查方向性样式与 icon-only buttons；基础点击面积 >=32px，ARIA labels 完整 (`requirements.md:124`)。

- **T9.5 OS dark mode / 多窗口同步 smoke**
  - 路径: `src/store/themeStore.ts`, `tests/e2e/theme.spec.ts` (更新/新建)
  - AC: AC_UI_1 (`requirements.md:72`)
  - 估时: 0.9h
  - 依赖: T1.5
  - 可独立 commit: yes
  - 实施细节: media query + storage/BroadcastChannel；多 WebView 撕裂风险见 `research.md:169`。

## Stage 10: 清理旧 src 文件 + Bundle size check + E2E smoke (6.0h)
- **T10.1 删除旧 App、组件和 UI/DOM hooks**
  - 路径: `src/App.tsx`, `HeaderBar.tsx`, `SkillSidebar.tsx`, `RightPanel.tsx`, `ToastStack.tsx`, `hooks/useFocusTrap.ts`, `useVirtualScroll.ts`, `useTheme.ts` (删除/替换)
  - AC: AC_FN_1 (`requirements.md:80`), AC_UI_5 (`requirements.md:76`), AC_API_7 (`requirements.md:103`)
  - 估时: 1.2h
  - 依赖: Stage 1-8 完成
  - 可独立 commit: yes
  - 实施细节: 删除清单对齐 `design.md:268`；数据 hooks 保留，UI/DOM hooks 淘汰 (`design.md:98`)。

- **T10.2 清理 Audit Stub / OOS 入口 / frontend FS 写路径**
  - 路径: `apps/studio/frontend/src/**` (扫描/删除)
  - AC: AC_FN_1 (`requirements.md:80`), AC_TR_2 (`requirements.md:107`)
  - 估时: 0.8h
  - 依赖: T10.1, T9.3
  - 可独立 commit: yes
  - 实施细节: 不显示 Audit Log、审计查询、前端凭据写入；历史硬约束见 `research.md:178`。

- **T10.3 Bundle size analyze 与 route lazy 收敛**
  - 路径: `vite.config.*`, `src/routes/**` (更新)
  - AC: AC_UI_3 (`requirements.md:74`)
  - 估时: 1.0h
  - 依赖: Stage 1-9 完成
  - 可独立 commit: yes
  - 实施细节: 目标主 chunk gzipped <=2.5MB；Monaco/React Flow/Diff/Copilot 分包，Q6 见 `design.md:349`。

- **T10.4 全量 typecheck/lint/unit + Playwright E2E**
  - 路径: `apps/studio/frontend/**` (验证)
  - AC: 全部
  - 估时: 1.5h
  - 依赖: T10.1-T10.3
  - 可独立 commit: no
  - 实施细节: 跑 typecheck/lint/unit；E2E 覆盖 Home、Edit、Predict、Run、Debug placeholder、Eval、Copilot、dark mode。

- **T10.5 Tauri 桌面冷启动 smoke + AC 归档**
  - 路径: `tests/e2e/tauri.spec.ts`, `test-results/**` (验证/生成)
  - AC: 全部
  - 估时: 1.5h
  - 依赖: T10.4
  - 可独立 commit: no
  - 实施细节: 验证冷启动、Hash refresh、drag region、IDE buttons、Settings HTTP-only；AC_FN_5 标注 UI 占位降级。

## §4 跨 stage 依赖矩阵
| Stage | 必须依赖 | 可并行说明 |
|---|---|---|
| S0 | 无 | 环境、CSS、目录骨架最先做 |
| S1 | S0 | Router/Shell/Theme 是后续所有工作流前提 |
| S2 | S1 部分完成 | Home 可与 S3 canvas foundation 并行 |
| S3 | S1 | Edit/Compile 是 Predict/Run 的执行门禁 |
| S4 | T3.7 | Predict 依赖 compile success；可与 S5 并行 |
| S5 | T3.7 | Run/Trace 依赖 compile success；可与 S4 并行 |
| S6 | T5.5/T5.6 | Debug UI 依赖 Run 状态与 Edge viewer |
| S7 | T4.5/T5.2 | Eval 依赖 Golden 与 RunHistory，可与 S6 后段并行 |
| S8 | S1 | Copilot core 可与 S2-S7 并行，route context 后接 |
| S9 | S1 | Tauri 边角可与 S2-S8 并行，credential scan 依赖 T8.7 |
| S10 | S1-S9 | 清理、bundle、E2E 必须最后 |

## §5 实施 DAG (按依赖并行)
```text
S0:
  T0.1 -> (T0.2, T0.3) -> T0.4

Shell:
  T0.3 -> T1.1 -> T1.2 -> T1.3 -> T1.4
  T0.2 -> (T1.5, T1.6)
  T1.2 -> T1.7
  T1.1 -> T1.8

Workflow:
  T0.3 -> T2.1 -> (T2.2, T2.4, T2.5)
  T1.3 -> T3.1 -> (T3.2, T3.3, T3.5, T3.6)
  T3.3 -> T3.4
  (T3.3, T3.5, T3.6) -> T3.7 -> (T4.1, T5.1)
  T3.7 -> T3.8 -> T3.9

Predict/Run/Debug/Eval:
  T4.1 -> T4.2 -> T4.3 -> T4.4 -> T4.5 -> T4.7
  T4.4 -> T4.6
  T5.1 -> T5.2 -> (T5.3a, T5.4, T5.5) -> T5.3b
  T5.3a -> T5.6 -> T5.8
  T5.2 -> T5.7
  (T5.5, T5.6) -> T6.1 -> (T6.2, T6.3, T6.4)
  (T4.5, T5.2) -> T7.1 -> (T7.2, T7.5) -> T7.6
  T7.2 -> (T7.3, T7.4)

Copilot:
  T1.2 -> T8.1 -> T8.2 -> (T8.3, T8.4, T8.5)
  T8.5 -> T8.6 -> T8.8
  T1.7 + T8.2 -> T8.7
  T8.1..T8.8 -> T8.9

Tauri/Cleanup:
  T0.1 -> T9.1 -> T9.2
  T8.7 -> T9.3
  T1.3 -> (T9.4, T9.5)
  S1-S9 -> T10.1 -> T10.2 -> T10.3 -> T10.4 -> T10.5
```

并行机会摘要:
- T1.5/T1.6/T1.7 可并行推进。
- T2 页面编写可与 T1.1 Router 挂载并行打桩。
- T2 Home 与 T3 Canvas foundation 可并行。
- T3.2/T3.3/T3.5/T3.6 可在 T3.1 后分工并行。
- Stage 4 Predict 与 Stage 5 Run 可在 T3.7 后并行。
- Stage 8 Copilot core 可从 S1 后并行，route context 沉淀在各 workflow task 内。
- Stage 9 Tauri 边角可与 S2-S8 并行。
- T7 Eval 可与 S6 Debug 后段并行。

## §6 AC ↔ Task 映射追踪表
| AC ID | requirements line | 覆盖 Task |
|---|---:|---|
| AC_UI_1 | `requirements.md:72` | T0.2, T1.5, T3.2, T9.5 |
| AC_UI_2 | `requirements.md:73` | T0.2 |
| AC_UI_3 | `requirements.md:74` | T0.2, T1.8, T3.2, T3.6, T5.6, T10.3 |
| AC_UI_4 | `requirements.md:75` | T0.4, T1.2, T1.6 |
| AC_UI_5 | `requirements.md:76` | T0.1, T1.3, T1.4, T10.1 |
| AC_UI_6 | `requirements.md:77` | T0.2, T1.4, T9.4 |
| AC_FN_1 | `requirements.md:80` | T0.3, T1.1, T1.2, T1.3, T1.4, T2.1, T2.3, T2.5, T9.2, T10.1, T10.2 |
| AC_FN_2 | `requirements.md:81` | T3.1, T3.3, T3.4, T3.5, T3.6, T3.7, T4.1, T4.3 |
| AC_FN_3 | `requirements.md:82` | T5.1, T5.2, T5.3a, T5.3b, T5.5, T5.6, T5.8 |
| AC_FN_4 | `requirements.md:83` | T3.1, T3.5, T5.4, T5.8 |
| AC_FN_5 | `requirements.md:84` | T5.5, T6.1, T6.2, T6.3, T6.4 (UI 占位/OOS 降级) |
| AC_FN_6 | `requirements.md:85` | T4.4, T7.1, T7.2, T7.3, T7.5, T7.6 |
| AC_CP_1 | `requirements.md:88` | T1.3, T8.2, T8.3, T8.5, T8.7, T8.9 |
| AC_CP_2 | `requirements.md:89` | T1.7, T8.7, T8.9 |
| AC_CP_3 | `requirements.md:90` | T3.8, T4.6, T5.7, T6.4, T7.4, T8.4 |
| AC_CP_4 | `requirements.md:91` | T8.1, T8.2, T8.3, T8.6, T8.8, T8.9 |
| AC_CP_5 | `requirements.md:92` | T8.7, T8.9 |
| AC_CP_6 | `requirements.md:93` | T2.4, T4.6, T7.4, T8.5, T8.8, T8.9 |
| AC_CP_7 | `requirements.md:94` | T8.2, T8.7, T8.9 |
| AC_API_1 | `requirements.md:97` | T2.1, T2.2 |
| AC_API_2 | `requirements.md:98` | T2.4 |
| AC_API_3 | `requirements.md:99` | T5.1, T5.2 |
| AC_API_4 | `requirements.md:100` | T4.1, T4.2, T4.7 |
| AC_API_5 | `requirements.md:101` | T4.4, T4.5, T7.1, T7.2 |
| AC_API_6 | `requirements.md:102` | T3.3, T3.7, T3.8 |
| AC_API_7 | `requirements.md:103` | T1.6, T10.1 |
| AC_TR_1 | `requirements.md:106` | T2.3, T9.1, T9.2 |
| AC_TR_2 | `requirements.md:107` | T1.7, T8.7, T9.3, T10.2 |
| AC_TR_3 | `requirements.md:108` | T9.4 |
| AC_TR_4 | `requirements.md:109` | T0.4, T1.4, T9.2 |

覆盖结论: 30/30 AC 均有 task 映射；AC_FN_5 按 design 降级为 UI 占位，不接 backend resume。

## §7 风险点提示
- §5.5 Debug & Resume 降级为 UI 占位；V3 接通 backend checkpoint/resume 后，T6 需要整体重做。
- Bundle size <=2.5MB gzipped 可能压迫 Monaco、React Flow、Diff、Copilot 分包策略；T10.3 必须实测。
- Q3 Predict cancel 没后端中断路径；Stage 4 只能做 loading/timeout/Toast，不应假装已取消真实 LLM 执行。
- Q4 Schema infer 建议 Stage 3 开工前小 spike；复杂 union 推导在 V2 应降级为 warning。
- Trace WebSocket 高频事件若超过预期，T5.3a 的 100ms 合批和 T5.3b 虚拟化是硬门槛。
- 严禁重回 Audit Stub、旧全局 skill list、前端 FS 写 credentials、紫蓝主题。
