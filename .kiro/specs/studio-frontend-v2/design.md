# Studio Frontend V2 Architecture Design

> 本文档为 `studio-frontend-v2` 实施阶段的直接依据。所有的 UX/视觉要求已收敛于 `requirements.md`，现状摸底收敛于 `research.md`。本文档重点规定数据流、模块边界、前端路由、状态管理以及关键技术集成策略。

## §1 整体架构 (Architecture Overview)

### 1.1 三层数据流与组件交互图

```text
+-----------------------------------------------------------------------------------+
|                            Tauri WebView (Desktop Shell)                          |
|  (File System / Process spawning via @tauri-apps/api/shell, Theme OS events)      |
+-----------------------------------------------------------------------------------+
                                         | IPC
                                         v
+-----------------------------------------------------------------------------------+
|                              React App (Frontend V2)                              |
|                                                                                   |
|  [React Router (HashRouter + Data API)]                                           |
|       |- / (Home Dashboard)                                                       |
|       |- /skill/:skillId/* (Workspace)                                            |
|                                                                                   |
|  [State Management]                                                               |
|       |- Zustand (Theme/Global UI Sync via useSyncExternalStore)                  |
|       |- React Flow Provider (Canvas State)                                       |
|       |- Local Component State (React.useState / React.useReducer)                |
|                                                                                   |
|  [UI Shell (Shadcn + react-resizable-panels)]                                     |
|       |- <Header /> (h-11)                                                        |
|       |- <Toolbar /> (w-12, Left rail)                                            |
|       |- <Canvas /> (Center, React Flow)                                          |
|       |- <Panels /> (Left drawer: Assets, Timeline, Properties, Editor)           |
|       |- <CopilotPanel /> (Right rail, Always-on)                                 |
+-----------------------------------------------------------------------------------+
            | REST (axios client)                  | WebSocket (useCopilot.ts)
            v                                      v
+-----------------------------------------------------------------------------------+
|                              FastAPI Backend (Python)                             |
|                                                                                   |
|  [Routers]                                                                        |
|   |- /skills, /runs, /lint, /compare, /debug                                      |
|   |- /copilot (GET/PUT credentials, POST context, WS /ws)                         |
|                                                                                   |
|  [Services]                                                                       |
|   |- golden_diff.py (Compare to Golden)                                           |
|   |- copilot.py (Anthropic/DeepSeek LLM Client, Session mgmt)                     |
+-----------------------------------------------------------------------------------+
```

### 1.2 核心模块边界划分

1. **Routing**: `src/routes/` 目录接管。摒弃 `App.tsx` 内的条件渲染，强制页面卸载以规避内存泄露。
2. **Data Layer**: `src/api/client.ts` 维持不变。数据预取下放至 Router 的 `loader`，异步操作走 `action` 或 `useMutation` 风格钩子。
3. **State Management**: 全局配置走 `zustand` (取代手搓的 Context)。
   - **Theme 同步细节**: 彻底废弃旧的 Tailwind classes，利用 `zustand` 的 `useSyncExternalStore` 模式 (直接参考 uikit 现有 `useTheme` 钩子)，确保在 Tauri 多窗体 IPC 广播中同步更新 DOM root 的深色变量属性。
   - **Toast Global Mount**: `<ToastStack />` (Sonner) 必须挂载于 React Router 的 Root Shell 之外（即在 RouterProvider 旁边或 Root Layout 顶层），绝对不能嵌在某个具体的 Workspace Layout 内，以防切页时 Toast 突然被卸载吞毁。工作区内数据仍局部隔离于 `/skill/:id`。
4. **UI Shell**: 完全拥抱 `uikit` 产物。剥离所有的手写 margin/padding 布局，替换为 Shadcn 的 `ResizablePanelGroup`。
5. **Copilot Integration**: 从视图层剥离，形成独立的 Data Hook (`useCopilot`) 与 View Hook (`useCopilotContext`)。
6. **Tauri Shell**: 将所有 IPC 调用封装在 `src/lib/tauri.ts` 中，与 Web 环境解耦。

---

## §2 路由与 Workspace 强隔离

### 2.1 路由选型: HashRouter + Data API
根据 `research.md §2.1` 的实证：
- **为什么不用 BrowserRouter**：Tauri 在桌面端以 `file://` 协议或内嵌静态 Server 运行，直接刷新 (Cmd+R/F5) 任意子路径会导致服务端返回 404 (无 H5 History API 的重定向机制)。
- **决策**：使用 `createHashRouter` (或配置了 baseroute 的 memory 模拟)。URL 呈现为 `/#/skill/123/edit`，确保原生窗口刷新安全，同时享有 React Router v6.4+ 的 `loader` 预取能力。

### 2.2 Route Table 映射
```text
/ (Home / Dashboard)           -> 呈现 <WelcomeScreen /> (包含 Recent Skills 列表)
/skill/:skillId                -> 抽象壳组件 <WorkspaceLayout /> (拦截鉴权、载入全局 Context)
  |- /edit                     -> <EditCompileView /> (主画布 + 属性面板)
  |- /predict                  -> <PredictView /> (主画布 + 预演沙盒 面板)
  |- /run/:runId?              -> <RunTraceView /> (主画布 + Timeline 面板)
  |- /debug                    -> <DebugView /> (主画布断点状态 + Edge Inspector 面板)
  |- /eval                     -> <EvalPublishView /> (无画布，全屏 Diff Split Editor)
/settings                      -> <SettingsModal /> (通常作为 Overlay 路由呈现)
```

### 2.3 Workspace 强隔离的实现机制
- **状态不穿透**：当路由从 `/skill/A` 跳转至 `/skill/B`，`<WorkspaceLayout>` 组件会被强制卸载并重新挂载。所有的 React Flow 实例、Monaco 实例及对应的本地 `useState` 自动清空，达到完美清理内存的效果。
- **UI 持久化隔离**：侧边栏拖拽宽度的保存必须与 Skill 绑定。使用 `react-resizable-panels` 时：
  ```tsx
  <ResizablePanelGroup autoSaveId={`workspace-layout-${skillId}-${pageId}`} ... />
  ```
- **Home → Workspace 切换拦截**：在 Router 的 `loader` 或组件 Mount 时，必须调用一次 `useCopilotStore.getState().reset()`，彻底清空遗留的 Copilot 历史状态。

---

## §3 全局状态管理重构

### 3.1 废弃庞大 App State
现有的 `App.tsx` 包含了大量类似 `const [activeNode, setActiveNode] = useState(null)` 的状态，导致侧边栏开闭会触发整个画板重绘。
**动作**: 这些状态全部降级。`activeNode` 应当存放在 `<EditCompileView>` 的局部 Provider 或直接利用 React Flow 提供的 `useOnSelectionChange` 内部机制管理。

### 3.2 Hooks 的复用与淘汰法则
基于 `research.md §1.2`：
- **保留类 (Data fetching)**: `useSkills`, `useTemplates`, `useRunHistory`, `useGoldenDiff`, `useBatchRun`。这些仅仅是对 axios 的封装，只需把旧的 state setter 去掉，改为返回 Promise 供 `react-query` 或 Router loader 使用。
- **重写类 (UI & DOM)**: `useTraceSelection`, `usePhaseForm`, `useFocusTrap` 彻底作废。由 Shadcn 的 Dialog 内部管理 Focus，由 React Router 的 URL 参数管理 Trace 选中态（例如 `/run/123?trace_id=456`），而不是存内存。

---

## §4 UIKit UI Shell 的移入契约

### 4.1 布局映射 (对应 UIKit 目录)
- `<Header />` (h-11, 44px)：固定在顶部。内部挂载全局状态 (编译状态灯，Predict/Run 按钮)。
- `<Toolbar />` (w-12, 48px)：取代旧的 `SkillSidebar`。控制中下层路由的跳转 (`/edit`, `/run` 等)。
- `<ResizablePanelGroup>`：
  - **Left Panel**: 渲染 `Assets`, `Timeline`, `Properties`, `Editor` 之一。
  - **Center Panel**: 渲染 `<GraphCanvas />` (依赖 @xyflow/react)。
  - **Right Panel**: 渲染 `<CopilotPanel />`。

### 4.2 Z-index 栈空间约定
必须在全局 CSS 或 Tailwind config 强制约束：
- `z-0`: `<Canvas />` 底层画布
- `z-10`: 左侧 `<Toolbar />` 与底部辅助栏
- `z-20`: `<ResizableHandle />`
- `z-40`: `<CopilotPanel />` 与悬浮 `<CopilotButton />` (FAB)
- `z-50`: `<SettingsModal />` 等各类弹窗 Dialog
- `z-60`: `<ToastStack />` (如 Sonner)

---

## §5 六个工作流页面的视图展开

### 5.1 工作流 01: Discovery & Init (主页)
- **页面**: `src/routes/home.tsx` (原 WelcomeScreen 升级版)。
- **Hooks**: 复用 `useRecentSkills`。
- **交互**: 单击列表直接 `navigate("/skill/{id}/edit")`。
- **API**: GET `/skills`。

### 5.2 工作流 02: Edit & Compile (编辑与编译)
- **页面**: `src/routes/skill/edit.tsx`。
- **布局流派**: **Canvas-first**。主视口是 React Flow 图，双击 Agent 节点时，在左侧的 ResizablePanel 挂载 `LazyMonacoPanel` 以编辑 `system_prompt`。
- **交互与防抖护栏**:
  - `onChange` 更新本地状态；停顿 800ms 或 Monaco 失去焦点后，发起 `POST /skills/{id}/lint`。
  - 成功则在 Header 的 StatusBadge 标绿，解锁 Predict。失败标红，锁定。
- **API**: POST `/skills/{id}/lint`。

### 5.3 工作流 03: Predict & Baseline (预测试飞)
- **页面**: `src/routes/skill/predict.tsx`。
- **交互**: 点击 Predict 按钮，弹出 `useInputPlayground` 的简化版弹窗让用户选取输入 JSON，验证 Schema 后发起请求。
- **异构执行决议 (Mock 移除)**: User 决议取消 Mock LLM。前端一视同仁发送真实 `POST /api/skills/{id}/predict`，后端复用 Copilot-V1 端点进行真 LLM 调用。
- **双屏打磨**: Predict 成功后，视图通过 `uikit/split-editor.tsx` 进入分屏，左 Predict 结果，右侧可呼出 Golden 基线供查阅比对 (read-only)。**Predict 不允许直接 Save as Golden** — backend 显式 409 拦截 `metadata.is_predict=True` trace (见 `services/diagnostic_export.py assert_trace_can_be_promoted_to_golden`); 真正的 Golden 升格需经完整 Run 流程后在 Eval 视图触发, 见 §5.6 工作流 06。
- **API**: POST `/api/skills/{id}/predict`。

### 5.4 工作流 04: Run & Trace (真实执行与时间线)
- **页面**: `src/routes/skill/run.tsx`。
- **布局**: 左侧 ResizablePanel 渲染竖向 Timeline (替代旧版 TracePanel 横幅)。
- **交互 (Micro-Topology)**: 单击 Timeline 或画布中的某节点，弹出一个侧栏 (或覆层) 展现 Prompt Inspector 的三个 Tab (Template / Vars / Rendered)。单机 Edge 连线圆点，弹出 JSON Viewer (使用 readonly Monaco) 查看 Context 大黑板。
- **API**: GET `/skills/{id}/runs`。

### 5.5 工作流 05: Debug & Resume (调试与恢复 - UI 占位降级)
- **决议声明 (降级为 UI 占位)**：由于实证表明 backend 没有 `/resume` 端点且缺乏 checkpoint 状态机存储，V2 版本在真实数据流上将 Debug 环节降级为 OOS（待 V3 后端支持）。但为了验收 UI 交互，保留前端占位逻辑。
- **UI 呈现**: 节点在接收到 error/breakpoint 时仍按照 Round 1 设计变黄，渲染出 `[Resume]` 按钮和 Monaco Context 黑板。
- **交互阻断**:
  - 点击 `[Resume]` 按钮**不触发任何网络请求**，仅弹出 Toast：`"HitL Resume 待 backend 实现 (V3 范围)"`。
  - Edge Monaco Editor 修改大黑板后，点击保存，修改仅**暂存到本地 LocalStorage**，不向下游分发。

### 5.6 工作流 06: Eval & Publish (评估发布)
- **页面**: `src/routes/skill/eval.tsx`。画布被隐藏，占据全屏的 `split-editor.tsx` 变体。
- **交互**: 左列 Artifact，右列 Golden Baseline。
- **数据联通与复用**: 继续复用现存前端 `useGoldenDiff` hook。API 实证：前端请求 `GET /api/skills/{id}/runs/{run_id}/compare` (对接 `compare.py:23`) 取得双树结构的变更数据。
- **Copilot Judge**: 提供 "AI Judge" 按钮，将 Diff 数据打包发送给右侧 Copilot 让其评分。
- **Publish 撒花**: 点击 Publish，弹出填写 Commit Msg 框，发送后使用 `canvas-confetti` 在窗口中央播撒特效。
- **Save as Golden**: 在 Eval Diff 面板顶部提供 `[Save as Golden]` 按钮, 接 `POST /api/skills/{skill_id}/golden` with `{run_id, lock}`; run_id 取自当前 Eval 比对的 Run。仅 Run 流程的 final_state.json 可升格 (Predict trace 被 backend 拒绝)。

---

## §6 Copilot V1 集成层 (4 层架构)

### 6.1 `useCopilot` (WebSocket 数据钩子)
- **职责**: 维护 Socket 实例与 Messages 数组。
- **选型**: 依赖 `react-use-websocket`。开启 `shouldReconnect: () => true`。
- **Event 处理**:
  - `text_delta`: 追加并拼接至最后一条 Assistant Message。
  - `tool_use_start`: 压入特定结构，渲染 UI "正在 Read X.py"。
  - `tool_use_result`: 更新该条目的状态，渲染 "✅ 已 Edit X.py (+5 -2 lines)" 以及 Diff 气泡。
  - 拦截 AcceptEdits 要求，展示提醒。

### 6.2 `useCopilotContext` (防抖 View Context 同步)
- **职责**: 让 Agent 知道我们在看什么。
- **触发源**: `useLocation().pathname` 变化，或 `useOnSelectionChange` (React Flow 节点选中) 变化。
- **大视图截断防崩策略 (Threshold + Fingerprint)**:
  - 读取目标内容字符串长度。
  - `<= 2048` 字符：全量发给 `POST /api/skills/{id}/copilot/context`。
  - `> 2048` 字符：截断前 500 字符作为 `summary`，并在末尾附加人工指令 `[Context truncated due to length. Please use the Read tool to fetch the full content from file path or run_id if necessary.]`。
  - 结合 800ms 防抖执行。

### 6.3 `<CopilotPanel />` (Chat UI 视图层)
- **挂载点**: Always-on 处于 `workspace.tsx` 的最右侧。
- **Tool UI Component Boundaries (组件边界)**: 
  - `<ToolCallBubble />`: 专门拦截 `tool_use_start` 事件。渲染类似 Notion 的 "正在拉取 X.py..." 的 Loading 折叠区，不混入标准 Markdown 解析流。
  - `<DiffBubble />`: 专门拦截 `tool_use_result` 中的代码类更新结果，调用 `react-diff-viewer` (或现有 GoldenDiff UI) 渲染高亮的 `+5 -2 lines` 直观差异，附带确认按钮（如果适用）。避免纯粹 Markdown 渲染造成的长代码换行炸版。

### 6.4 `<ModelPicker />` + `<CopilotSettings />`
- **逻辑**: 前端不直接触碰 `~/.studio/copilot.json`。
- **加载**: 组件 Mount 时发起 `GET /api/copilot/credentials`。如果当前 Model 没有 Key，下拉项的 `disabled` 属性激活，提供 tooltip 引导。对于 Gemini/OpenAI 选项，硬编码禁用并显示徽章。
- **切换**: ModelPicker 发出变化 -> 清空前端 `useCopilot` 中的 messages 数组 -> 发送 `PUT /api/copilot/credentials` 包含 `{ set_active: true }` -> 渲染 "已切换模型" Toast。

---

## §7 Tauri 桌面端集成

### 7.1 外部 IDE Buttons 的命令封装
在 `src/lib/tauri.ts` 中封装：
```ts
import { Command } from "@tauri-apps/api/shell";
export const openInCursor = async (path: string) => {
   // Tauri tauri.conf.json 需配置 scope 允许执行 cursor 命令
   const cmd = new Command("cursor", [path]);
   await cmd.spawn();
};
```
在 Toolbar 和 Copilot Welcome 区域绑定调用。

### 7.2 文件权限与跨平台策略
- **Windows 的 chmod 600 对应物**: 在 Unix 系，后端用 `os.chmod(path, 0o600)`。在 Windows (NTFS) 环境中 `0o600` 不等价（Windows 无严格 chmod 语义，需配置 DACL 剥夺非 Owner 权限）。**(Q2: 设计阶段已知难题，已移入 Appendix B 供评审)**。
- 前端只管通过 HTTP 发送请求，把环境底层操作抛给 Python 后端。

### 7.3 系统级 Dark Mode 检测
- 利用 Tauri 窗口事件订阅或简单的媒体查询。为保障安全同步，将结果推给 `useSyncExternalStore` (即 uikit 的 `useTheme` 实现)。
  ```ts
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", ...);
  ```

### 7.4 F5 / Cmd-R 刷新屏蔽与 WebView 行为
- 在生产模式下，桌面端应用被刷新将重载 `index.html`。由于启用了 HashRouter (见 §2.1)，这不会导致白屏。
- Copilot 状态因为是在内存中，刷新会丢失，符合 "Out of Scope" 预期。
- `<header>` 加入 `data-tauri-drag-region` 属性以便拖拽窗体。

---

## §8 性能策略

1. **Trace 高频事件渲染屏障**: 
   - Trace Timeline 可能面临 >30 events/s 的推送。
   - **合批 (Batching)**: 接收 WebSocket 后，立刻放入一个非 React 状态的数组队列中，利用 `setInterval` 或是 `requestAnimationFrame` 每 100ms 抽取队列更新到 React State，极大降低 Diff 负担。
   - **虚拟化 (Virtualization)**: 引入 `react-virtuoso` 替换废弃的 `useVirtualScroll`，保障 1000+ 日志时的滚动顺滑。
2. **Monaco Editor Lazy Load**: 
   - `<Suspense>` 配合 `React.lazy` 实现切片加载，骨架屏 `animate-pulse` 防止闪屏。
3. **Copilot Message Buffering**:
   - `text_delta` 同样采取 50-100ms 的节流聚合 (throttled setState) 更新，避免打字框出现输入迟滞。
4. **Bundle Size Budget**: 
   - 设硬上限 2.5MB (Gzipped)。通过 React Router 的 `lazy` 属性进行基于路由的 Code-splitting。

---

## §9 错误处理 + 网络重连

1. **WebSocket 断流重连**:
   - 触发: Proxy 刷新或休眠唤醒。
   - 机制: Exponential Backoff (1s -> 2s -> 4s -> 8s -> 16s，最大尝试 30s)。
   - 展现: 若超过最大次数，顶部 Toast "WebSocket 实时连接失败，请检查网络或刷新"。
2. **HTTP 状态码阻断**:
   - `401/403`: 检测到时，弹窗或重定向触发打开 `<SettingsModal />` 要求配置 API Key。
   - `500`: 抛出局部 Error Boundary 提示，并在后台静默重试 1 次 (GET 请求)。
3. **网络探测**:
   - 利用 `navigator.onLine`，断网期间 Disable 主行动按钮并悬浮红条警告。

---

## §10 文件改动清单 (供 Tasks 实施参考)

### 10.1 原文件处置简表 (严格对齐 Research 决议)

| 文件 / 目录 (`apps/studio/frontend/src/`) | 实施动作 |
|---|---|
| `App.tsx` | Delete (被 Routes 取代) |
| `WelcomeScreen.tsx` | Rewrite 为 `routes/home.tsx` |
| `GraphCanvas.tsx` | Rewrite 合并入 `routes/skill/edit.tsx` 配合 uikit 组件 |
| `HeaderBar.tsx` | Delete (替换为 uikit 产物) |
| `SkillSidebar.tsx` | Delete (替换为 uikit 产物) |
| `MonacoPanel.tsx` | Rewrite (懒加载化并包裹进 uikit code-editor) |
| `TracePanel.tsx` | Rewrite (对齐 Timeline 竖版需求) |
| `SettingsPanel.tsx` | Rewrite 为 `<SettingsModal />` |
| `RightPanel.tsx` / `ToastStack.tsx` | Delete |
| `hooks/useTheme.ts` | Delete |
| `hooks/useFocusTrap.ts` / `useVirtualScroll.ts` | Delete |

### 10.2 新建文件结构预估

```
apps/studio/frontend/src/
 |- routes/
 |   |- router.tsx                 # createHashRouter 定义配置
 |   |- root.tsx                   # 根 Layout
 |   |- home.tsx                   # Dashboard
 |   |- skill/
 |       |- layout.tsx             # WorkspaceLayout (包含 Copilot)
 |       |- edit.tsx               # Edit & Compile 视图
 |       |- predict.tsx            # Predict 视图
 |       |- run.tsx                # Run & Trace 视图
 |       |- debug.tsx              # 断点恢复视图
 |       |- eval.tsx               # 全屏 Diff 视图
 |- lib/
 |   |- tauri.ts                   # Tauri IPC 封装
 |   |- websocket.ts               # Backoff socket 逻辑封装
 |- store/
     |- copilotStore.ts            # Zustand 或局部 Context 状态
```

---

## Appendix A: Backend 现状摸底接口表

作为实施依据，已调研 `apps/studio/backend/app/routers/` 目录 (共 37 个端点，按组摘要核心端点)：

| Router 分组 | 端点实证 (file:line) | 用途 & Schema | 状态 |
|---|---|---|---|
| **Skills** | `skills.py:34 GET /skills` | 列出本地所有 skill 项目 | ✅ 复用 |
| | `skills.py:53 GET /skills/{id}` | 获取某个技能详情 | ✅ 复用 |
| | `skills.py:43 POST /skills` | 创建技能 | ✅ 复用 |
| | `skills.py:74 POST /skills/{id}/fork` | Fork 技能 | ✅ 复用 |
| | `skills.py:85 POST /skills/{id}/validate_input` | 输入验证 | ✅ 复用 |
| **Lint** | `lint.py:13 POST /skills/{id}/lint` | 实时编译，抛出错误树 | ✅ 复用 |
| **Runs** | `runs.py:27 POST /skills/{id}/runs` | 触发 Run | ✅ 复用 |
| | `runs.py:32 POST /skills/{id}/runs/predict` | 走 PredictorService dispatch，调真 LLM | ✅复用 (User 拍板不再走 Mock) |
| | `runs.py:43 GET /skills/{id}/runs` | 获取历史 Timeline 列表 | ✅ 复用 |
| | `runs.py:48 POST /skills/{id}/runs/batch-run` | 批量运行 | ✅ 复用 |
| | `runs.py:53 GET /skills/{id}/runs/{run_id}` | 获单次 Run 详情 | ✅ 复用 |
| **Golden/Compare**| `golden.py:15 GET /skills/{id}/golden/...` | 获取 Golden 基准 | ✅ 复用 |
| | `golden.py:24 POST /skills/{id}/golden/...` | 保存为 Golden 基准 | ✅ 复用 |
| | `compare.py:23 GET /skills/{id}/runs/{run_id}/compare` | 获取当前 Run 对 Golden 的 diff | ✅ 复用 |
| **Copilot**| `copilot.py:109 GET /api/copilot/credentials` | 探查配键状态 | ✅ V1 引入 |
| | `copilot.py:119 PUT /api/copilot/credentials` | 更新 Keys 落盘 | ✅ V1 引入 |
| | `copilot.py:34 POST /api/skills/{id}/copilot/context`| 更新视图黑板 | ✅ V1 引入 |
| | `copilot.py:45 WS /api/skills/{id}/copilot/ws` | 流式事件推送 | ✅ V1 引入 |
| **WebSockets**| `websockets.py:17 WS /ws/runs/{run_id}` | Trace 事件下发 | ✅ 复用 |
| **Templates** | `templates.py:13 GET /templates` | 模版获取 | ✅ 复用 |
| **TestInputs**| `test_inputs.py:18 GET /test_inputs` | 输入用例读取 | ✅ 复用 |
| **System** | `system.py:18 GET /system/health` | 健康检查 | ✅ 复用 |
| | `terminal.py:13 POST /terminal` | Terminal 拉起 | ✅ 复用 |
| **Debug** | `debug.py:10 GET /api/_debug/value-error` | 5xx Exception Smoke 验证，**与 HitL Resume 无关。HitL backend 不存在**。 | 🚫 不存在 (V2 OOS) |
| **Audit** | `audit.py:14 GET /audit/...` | 已有 GET stub，但不在 V2 前端实施范围展示 | 🚫 V2 页面 OOS |

---

## Appendix B: Open Questions (挂起供决议)

| Q ID | 问题摘要与本质 | 为什么需要评审 / 拍板 | 影响哪些 AC |
|---|---|---|---|
| **Q1** | **Trace WebSocket >30 events/s 的精确节流策略** | 是选择在 Hook 内以 `50ms` `setInterval` 强制抽样合批抛出，还是交给类似 `useDeferredValue` 由 React fiber 单帧决定丢弃率？高频渲染可能引发死锁。 | 性能 NFR (60fps), AC_FN_3 |
| **Q2** | **Windows 平台下 `chmod 600` 的等价物实现** | 后端 Python 代理了凭据落盘，但 `os.chmod(path, 0o600)` 仅限 POSIX。在 Windows NTFS 文件系统中是否需要动用 DACL API (或 `icacls`) 剥夺非拥有者权限？如果未实现，凭据实际上是明文裸奔。 | AC_TR_2 |
| **Q3** | **Predict 单次执行的中途 Cancel 路径** | Predict 若调起复杂 LLM Agent，可能需耗时数十秒。如果在过程中发现错误，前端如何立刻中断调用？是否需要后端暴露 `DELETE` 或中断信号 WebSocket 端点？ | US-3.2, AC_FN_2 |
| **Q4** | **Input Schema 的自动推导执行者** | US-2.2 要求拖拽 JSON 推导 Schema。是在前端用 `genson-js` 计算完成直接贴进代码，还是向后台专门开启一个新的 `/schema/infer` 接口利用 pydantic 做严格推断？ | US-2.2 |
| **Q5 (已 resolved 为 OOS/Defer)** | **HitL Pause & Resume backend 实现缺失** | - 实证: grep backend 0 命中 `/resume` / `paused` / `checkpoint`，debug.py 仅为 5xx 测试。<br>- 决议: V2 §5.5 降级为 UI 占位 + frontend-only mock；真 backend 待 V3 立项。<br>- 影响 AC: US-5.1 (节点级 Resume) 在 V2 表示 "UI 完整, 后端待补"；AC_FN_5 移 OOS。 | US-5.1 (降级) |
| **Q6** | **Bundle Size Budget 硬上限** | Tauri Desktop 对大体积前端的容忍度高于 Web，是否要定死 `2.5MB` gzipped 主 chunk 限额？这影响 Monaco 和 React Flow 是否必须懒加载切割打包。 | 性能 NFR |

---

## Appendix C: 历史 Spec 决策遗产 (Cross-reference)
参考 `.kiro/specs/studio-frontend-v2/research.md` §4，硬约束包含：禁止 Audit Stub、禁用跨端网络凭据缓存（强制走 Backend）、确立 Mono 黑白颜色体系与标尺（抛弃大紫主题）、严格的 Home/Workspace 孤岛隔离。
