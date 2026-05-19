# Studio Frontend V2 Requirements

## 1. 项目背景
本阶段为 `studio-frontend-v2`，旨在将第一阶段基于 shadcn radix-mira 构建的 UIKit 组件（`apps/studio/uikit/`）正式迁入并替换生产环境的前端应用（`apps/studio/frontend/`）。在此过程中，我们将全面接入在 `studio-copilot-v1` 中锁定的后端服务（含基于 WebSocket 的 Claude/DeepSeek Copilot 接入），并严格按照 `ux_workflow` 确定的 6 大工作流节点（从发现到发布）和 `UI_SPEC.md` 的视觉与布局契约，构建出一个高度沉浸、高信息密度、基于 Tauri 运行的图形化 Agent 编排与调试 IDE。V2 版本将根除原本单块（Monolithic）且难以维护的 `App.tsx`，建立基于 React Router 的多页隔离架构。

## 2. User Stories

### 2.1 全局框架 & Copilot 横切 (Global & Cross-cutting)
- **US-G1 (强隔离的导航心智)**: 作为 PM，我打开 Studio 时首先看到的是一个极简的 Dashboard (Home)，仅提供“新建 Skill”或“打开 Skill”的入口。进入某个 Skill 后，界面完全卸载 Dashboard，变更为仅展示该 Skill 的“沉浸式工作区”，防止被其他项目干扰。
- **US-G2 (左上角返回机制)**: 作为 PM，在我沉浸于某个工作区时，需要有非常明显的 `[← Back to Home]` 按钮，允许我随时退出工作流。
- **US-G3 (外部 IDE 联动)**: 作为 PM，在工作区内我需要能通过一组快捷入口一键使用外部工具处理复杂逻辑：`[Open in Cursor]`, `[Open in Terminal]`, `[Open in Codex]`。
- **US-G4 (常驻全能助手)**: 作为 PM，工作区右侧必须永远有一个不可被关闭的 Copilot 面板（always-on）。它能自动获取我当前视图的上下文，并支持使用工具读取和编辑工作区文件。
- **US-G5 (多模无缝切换)**: 作为 PM，我能在 Copilot 顶部的下拉菜单中随时切换后端模型（如 Claude API 和 DeepSeek API），切流体验应如同 Cursor IDE 般顺滑，切换时明确重起会话。
- **US-G6 (一站式配置)**: 作为 PM，我可以通过全局的 Settings Modal 统一配置我个人的不同模型 API Key。

### 2.2 工作流 01: 发现与初始化 (Discovery & Init)
- **US-1.1**: 作为 PM，我能在 Home Dashboard 上看到我最近打开过的 Skill 列表（Recent Skills），点击直接进入其沉浸式工作区。
- **US-1.2**: 作为 PM，当我决定新建一个空 Skill 时，我不需要填写复杂的表单，只需选定或创建一个本地空目录，系统即刻跳转进入工作区。
- **US-1.3**: 作为 PM，进入空的全新 Workspace 后，我可以直接在右侧 Copilot 面板中通过自然语言对话（`create-skill` prompt），让 Copilot 帮我生成基础的 `SKILL.md` 骨架。

### 2.3 工作流 02: 编辑与编译 (Edit & Compile)
- **US-2.1 (宏观定义)**: 作为 PM，我可以在工作区顶部清晰地配置 Skill 的全局基础信息（如 name, description, type），并清晰地定义起点的 Input Schema 和终点的 Output Schema。
- **US-2.2 (自动推导)**: 作为 PM，当我向 Input Node 拖拽一个现成的 JSON 测试数据文件时，系统能自动推导出输入数据的 Schema 结构。
- **US-2.3 (中观拓扑)**: 作为 PM，我在主视觉区（画布）可以通过声明 `depends_on` 或连线直观地建立节点间的串行/并行流转关系。
- **US-2.4 (子图展开)**: 作为 PM，对于包含子图的复杂节点，我期望能在主画布上直接以“树状平铺展开 (Inline Expand)”或以新标签页跳转（下钻）查看其脉络，配合面包屑导航防止迷失。
- **US-2.5 (微观编辑)**: 作为 PM，双击 Agent-Loop 类型的节点后，我能在滑出的 Monaco 编辑器中沉浸式编写 `<system_prompt>` 和 `<user_prompt_builder>`。
- **US-2.6 (节点属性)**: 作为 PM，我能在编辑节点时自由配置静态知识文件，挂载动态工具，并调节执行参数（如 validator, retry_target, max_retries, max_nudges）。
- **US-2.7 (实时编译护栏)**: 作为 PM，我在画布上的每一次修改，都会触发后端的 Compile (Lint)。如果数据流断层或循环，图上会出现红叉阻断执行；只有 Compile 绿灯亮起，才能解锁 Predict 按钮。

### 2.4 工作流 03: 预测与基线 (Predict & Baseline)
- **US-3.1 (测试驱动)**: 作为 PM，我能够通过文件选择器挑选输入用例，并在其上触发即时的 Schema 校验。
- **US-3.2 (异构执行)**: 作为 PM，触发 Predict 时，所有节点 (Code-only / Agent-Loop / Subgraph) 都运行真实逻辑 — Code-only 节点执行真实 Python, Agent-Loop 节点调用真实 LLM API (复用 copilot-v1 后端已接通的 Anthropic 兼容入口: OpenRouter / DeepSeek)。Predict 跟 Run 在 LLM 真实性维度上无差别，差别仅在 UX 维度: Predict = 单次同步打磨入口 (用于建 Golden Baseline), Run = 正式 Tracing 完整执行 (落 Trace Timeline)。
- **US-3.3 (双屏打磨)**: 作为 PM，执行 Predict 后，我期望看到分屏视图：左侧显示本次 Predict 的拟真输出流转，右侧展示我正在构建/对比的 Golden Baseline 草稿。
- **US-3.4 (Copilot 协助)**: 作为 PM，在打磨结果时，我可以随时召唤右侧的 Copilot 帮我分析 Predict 与预期的出入并给出调整代码。

### 2.5 工作流 04: 运行与追踪 (Run & Trace)
- **US-4.1 (执行场控)**: 作为 PM，我可以执行全局真实的 Run 操作，直观地看到流程在 Running / Paused / Failed / Success 之间的状态变化。
- **US-4.2 (Trace 竖版构图)**: 作为 PM，在 Timeline 面板中，我能通过 WebSocket 接收实时流，以垂直的时间线形式查看按 Phase 分隔的详细执行日志，包含工具调用、大模型思考耗时及 Token 消耗。
- **US-4.3 (微观拓扑展开)**: 作为 PM，我在 Trace 过程中可以通过单击 LLM 节点，展开其微观拓扑结构（如 update_working_memory -> tool_calls -> MD2JSON -> validator）。
- **US-4.4 (黑板透视)**: 作为 PM，我可以通过点击画布节点间的 Edge（连线圆点），唤起一个 JSON Viewer，在右侧查看此时传递的全局 Context。
- **US-4.5 (Prompt Inspector)**: 作为 PM，我能深入查看任意节点的 Prompt，并在 3 个独立的标签页（Template / Variables / Rendered）间切换。

### 2.6 工作流 05: 调试与恢复 (Debug & Resume)
- **US-5.1 (断点求助)**: 作为 PM，当流程触发 HitL 或 Error 时，顶部必须出现弹窗问询，同时对应的出错节点上会出现局部 `[Resume]` 按钮，允许我局部干预并注入重试参数。
- **US-5.2 (脏状态阻断)**: 作为 PM，如果我在流程暂停期间修改了对应节点的 `SKILL.md`，系统必须立刻失效（Dirty State Invalidation）从而阻止我直接 Resume，强制我重新 Compile 以策安全。
- **US-5.3 (大黑板篡改)**: 作为 PM，当发现上游数据存在瑕疵时，我能在 Edge 点击唤出的 Monaco JSON Editor 中直接篡改黑板的变量值，保存后点击 Resume，让下游带着假数据继续运行测试。

### 2.7 工作流 06: 评估与发布 (Eval & Publish)
- **US-6.1 (基线对比)**: 作为 PM，在 Run 结束之后，我可以进入 Split-view Diff 面板，直观查阅当前的产物结构和文本对比 Golden Baseline 发生的偏移。
- **US-6.1b (确立基准)**: 作为 PM，在 Eval 面板比对真实 Run 的产物无误后，我可以点击 `[Save as Golden]` 将此次 Run 升格为测试基线。Backend 契约: `POST /api/skills/{id}/golden` with `{run_id, lock}`; 拒绝 `metadata.is_predict=True` 的 trace (409 PREDICT_TRACE_CANNOT_BE_GOLDEN)。
- **US-6.2 (Copilot 判卷)**: 作为 PM，我可以在比对时点击请求，强制调取后端 Copilot 作为 Judge 角色，针对当前偏离打出分数并提供分析报告。
- **US-6.3 (一键上云)**: 作为 PM，当我确信所有环节正常，点击 `[Publish]`。系统提供我选填 Commit Message 的输入框（同时支持一键生成兜底说明），随后后端静默执行 `git add SKILL.md && git commit && git push`。发布成功后在屏幕中央洒下全屏撒花特效 (Confetti)。

## 3. 关键 Framing 决策 (立场声明)

1. **02_EDIT_AND_COMPILE 布局流派**: **选定 Canvas-first（画布优先）并支持切换**。
   - *立场*：图形拓扑是本产品的核心壁垒和操作心智。我们将主内容区 80% 赋予 React Flow 画布，微观节点编辑可通过局部侧边栏或覆层展示。考虑到长篇逻辑的连贯性，VS-Code 模式（上下大分屏同步滚动）作为备选布局供硬核开发者切换，但非默认流派。
2. **App.tsx 单文件重构方向**: **彻底重写 (Rewrite)**。
   - *立场*：现有的 907 行 `App.tsx` 存在严重的逻辑和视图揉叠。必须采用 React Router 将应用解耦成两大强隔离页面结构：Dashboard 负责展示和引导，Skill Workspace 负责具体应用的编排，消除原本极度脆弱的大杂烩状态管理。
3. **现有 18 个 Hooks 复用率**: **核心数据流复用，约 60% UI/业务协同 Hook 重写**。
   - *立场*：基于后端的 axios `client.ts` 相关纯数据获取 Hook 完全原样复用（如 `useRuns`, `useSkills`）。而所有涉及视图焦点联动、面板控制和本地 UI Context 分发的 Hook，因为我们拆分了独立的子组件与 React Flow Context，必须统统用颗粒度更小的状态重写。
4. **Copilot v1 前端集成形态**: **按四层逻辑下发**。
   - *立场*：① Streaming 与数据层统一下沉至 `useCopilot.ts`；② 视图上下文防抖感知交由 `useCopilotContext.ts` 发送 POST；③ Chat Bubble 界面聚焦流式 markdown 与特化 `tool_use` (Read/Write/Edit/Bash) 图文反馈渲染；④ ModelPicker 和 Settings 分别负责接口层的读写与缓存。
5. **Home / Workspace 路由**: **采用 React Router 多页跳转**。
   - *立场*：单页状态切换在维护大量强隔离状态时极易发生内存泄露和状态污染。强制实施多页路由（`/` 与 `/skill/:id`），切换项目相当于进行了一次干干净净的 DOM 与 Context 卸载回收。
6. **Theme 管理**: **采用 `useSyncExternalStore` (UIKit 模式)**。
   - *立场*：仅靠 Tailwind `dark:` 处理不够应对复杂的基于 oklch 动态色板的需求，且前端在 Tauri 内可能需要持久化。采用订阅机制确保各类图表、SVG 和 Canvas 颜色在明暗切换时不发生撕裂脱节。

## 4. Acceptance Criteria (AC)

### 4.1 UI/视觉 AC (严格履行 UI_SPEC.md)
- **AC_UI_1**: 全局配色必须 100% 应用基于 oklch 的 `radix-mira` 主题。暗色模式的 `border` 必须采用 `oklch(1 0 0 / 0.1)` 半透白。状态指示强制按规范：idle/running/success/error/paused/breakpoint（例如错误态使用红橙色 `destructive` 标记）。
- **AC_UI_2**: 字体必须加载 `Inter Variable` (正文) 和 `JetBrains Mono Variable` (代码/副ID)。字号依循以 1.5 比例的字阶，字重控制在 400-700。
- **AC_UI_3**: Canvas Node 在 running 状态必须呈现 1.4s 週期的 `pulse-primary` 动画。面板、模态窗弹出必须带有 `animate-in fade-in` 或 `slide-in-from-right` (200ms ease-out) 以传达平滑交互体验。
- **AC_UI_4**: 严格执行 z-index 分层控制栈：`z-0` Canvas -> `z-10` 侧边栏/Toolbar -> `z-20` Resizable Handle -> `z-40` Copilot/浮球 -> `z-50` 弹窗 -> `z-60` Toast。
- **AC_UI_5**: 界面布局外壳必须为 44px (h-11) 顶部 Header，48px (w-12) 左侧 Toolbar。主内容区必须基于 3 个 `ResizablePanelGroup` 构建以确保动态比例安全响应拖拽。
- **AC_UI_6**: Button 组件默认尺寸、Input 圆角以及 Badge 组件形态需全面替换 uikit-redesign-spec 设定的 `tokens.md` 中相应的尺寸和高度 (如 Toolbar 按 32px 的点击热区对齐)。

### 4.2 功能流转 AC (Ux Workflow 契约)
- **AC_FN_1**: 启动时强制路由至 Home Dashboard，在列表或建立向导中交互完成后跳转至 `/skill/:id` 的隔离 Workspace，隐藏其他项目的无关元素。
- **AC_FN_2**: 编辑工作区（Monaco或表单）任何修改，防抖保存后必须立刻触发 `POST /skills/{id}/lint` 进行后置检测；返回任何编译层级报错必须渲染在 Compilation Widget，并锁定后续执行。
- **AC_FN_3**: Trace Panel 与 Run 接口接通。触发执行后，必须动态渲染 Timeline (竖版)，并在连线点 Edge 圆圈高亮处点击展开 Context JSON 查看器。
- **AC_FN_4**: 支持 Micro-Topology 展开：单击 LLM 节点即可在副窗体查看它工作内存、工具调用、及其返回文本和验证。支持 Prompt Inspector 的 Template/Variables/Rendered 切换。
- **AC_FN_5**: 调试拦截：当后端在 `breakpoint` 打出异常处于 `paused` 状态时，画布须变黄锁定，支持在侧边或局部修改并注入修复后触发 `[Resume]` 的调用。
- **AC_FN_6**: Compare 面板完整实现左右对齐代码与 JSON 数据级 Diff，成功触发 `git push` API 后必须展示全屏撒花效果。

### 4.3 Copilot V1 集成 AC
- **AC_CP_1**: Copilot 的聊天记录仅存于会话生命周期内，切后端模型必须引发会话清空并渲染提示语“已切换模型，会话重起”。
- **AC_CP_2**: 如果当前后端 `credentials` 状态未设定对应模型的 API Key，模型 Picker 下拉项中此模型置灰，悬浮提示要求 "请先在 Settings 配置 API Key"。
- **AC_CP_3**: View Context (视图黑板) 更新请求必须对 Copilot 的会话历史完全隔离，且通过 debounce (防抖) 控制在 `POST /api/skills/{id}/copilot/context` 上。
- **AC_CP_4**: 解析引擎需捕捉 `tool_use_start` 并映射为 "🔧 正在 Read/Write" 的友好提示框；捕捉 `text_delta` 解析为标准 Markdown；且明确支持渲染执行完的 `tool_use_result` 摘要及 diff。
- **AC_CP_5**: ModelPicker 内对于暂不开放的 Gemini/OpenAI，标定 disabled state 并悬浮徽章展现 "V1.5 上线"。
- **AC_CP_6**: System prompt 渲染的后端需保证专家定位但在遇到无关编程问题时也能做通识应对，前端必须予以渲染而非错误屏蔽。
- **AC_CP_7**: 当 ModelPicker 选择 Claude 时，流量应直接通过封装向 Anthropic 发送；选择 DeepSeek 时，流量指向其官方的 Anthropic 兼容端点 (后端实现)。

### 4.4 现有 Frontend API 接入 AC (Phase B)
- **AC_API_1**: 接入已有的 `useSkills` 与 `useRecentSkills` 钩子服务于主页入口及项目发现。
- **AC_API_2**: `useTemplates` 在由 Copilot 引导创建前作为可选项的脚手架工具。
- **AC_API_3**: `useRunHistory` 必须配合 Timeline 实现数据的呈现，支持选中某个历史快照进行回溯查看及 `DELETE` 清理。
- **AC_API_4**: `useInputPlayground` 组件逻辑需直接嵌入到 Predict 触发模块。
- **AC_API_5**: `useGoldenDiff` 负责支撑最终 Eval 工作流的对比分析。
- **AC_API_6**: 必须支持通过 `useBatchRun` 和 `useDraftPersist` 处理本地自动存储，同时通过 `usePhaseForm/Sync` 同步 Markdown 与节点的输入。
- **AC_API_7**: 必须引入 `useGlobalShortcuts`：按下 `/` 键弹出全局命令中心，按下 `?` 弹出速查表。

### 4.5 Tauri 桌面端集成 AC
- **AC_TR_1**: 工作区导航处必须具有分别触发 `[Open in Cursor]`, `[Open in Terminal]`, `[Open in Codex]` 的独立按键，调用 Tauri Shell 执行相应的子系统拉起操作。
- **AC_TR_2**: 关于配置文件读写的动作必须彻底杜绝前端的 Tauri FS 访问，所有的 `API Keys` 变更指令通过 HTTP 方式送交给 Python Backend 执行以规避环境权限差异。
- **AC_TR_3**: Webview 内部必须全面禁止 RTL 语言强制倒装带来的混乱，使用 Tailwind logical properties 保留对组件拓展层级的包容性即可。
- **AC_TR_4**: 提供适应操作系统的顶部可拖拽抓手区域 (Drag Region)，以便 Tauri Webview 能顺利响应系统级的窗口移动和 Resize。

## 5. Out of Scope (V2 明确不做，留至 V3+)
- **Sub-graph Drilled Down (子图深层下钻交互)**: V2 仅支持在主画布上以“平层树状展开 (Inline Expand)”查看子图结构，或者以“新标签页/新 Workspace”方式跳转。复杂的基于嵌套 z-index 和状态堆栈的原地深层下钻暂留后续。
- **大规模 Audit Stub**: MVP3 中定义的详细的追踪鉴权和所有涉及企业审计上报的组件，V2 中全部暂缓。
- **Tauri Keyring 级原生加密**: 涉及 MacOS/Windows Keychain 原生级别的凭据加密推迟，当前只执行文件的基础防护。
- **Copilot 历史会话本地落盘**: 所有对话局限于 in-memory 状态。刷新则丢失，不作持久化表结构管理。
- **LiteLLM 多模型协议中转**: 工具调用的协议转换成本太高，不强行通过 LiteLLM 翻译至 Gemini/OpenAI，因此这双路的 Tool Use 支持顺延至 V1.5。

## 6. 非功能需求 (NFR)
- **Performance**:
  - 画布渲染要求：在具有数十个节点并在视口存在 Monaco 编辑器时，拖曳缩放操作必须稳保 60fps 不卡顿。
  - 会话长列表防抖：当对话进入长回复模式 (100+ items)，强制开启列表子项的 `React.memo` 判断，确保聊天输入框的键盘输入迟滞 <50ms。
- **Resilience**:
  - 通讯网络中断防护：若是因代理配置导致 WebSocket 断联，必须配置基于指数退避算法（Exponential Backoff）的自动重连机制。
- **Accessibility (A11y)**:
  - 聚焦与导航：组件接受标准的 TAB 键盘寻址，Focus 环色彩对齐 `--ring` 变量确保不过度刺眼；基础互动的点击面积需大于 32px 保证精准触发。全局必须维护 ARIA labels 供识别。

## 7. 依赖与前置
- 强依赖已交付的 `studio-copilot-v1` 后端设施（包含 T1-T3 commits 锁定的 credentials API, Context API 及 WebSockets Endpoint）。
- 强依赖现存的 `apps/studio/backend/app/routers/` 提供的全套 Lint, Compile, Run 和 Compare HTTP 端点支持。
- 前提是 `apps/studio/uikit` 中的 UI 组件重构 (tokens 设计审核) 已然通过并可供复用拷贝。

## 8. Open Questions (设计阶段跟进)
- **Q1 (Context Auto-Injection 数据量优化)**: 针对超大尺寸的文件或代码块（如超出几千字的大 View），视图自动触发 `POST /context` 是否采取全文上报？还是采取“只有 Path 以及关键 Hash 指纹的精简 Diff”，或者是设定如 2KB 为界限的数据截断策略？这将交由 architecture design 阶段决议。

## Appendix B: studio-copilot-v1 12 AC ↔ studio-frontend-v2 AC 一字映射

| copilot-v1 AC | 内容摘要 | v2 对应 AC | 备注 |
|---|---|---|---|
| AC1 | Claude → Anthropic API | AC_CP_7 | 已由后端实现，前端路由传递 Model_ID 触发。 |
| AC2 | DeepSeek → DeepSeek 端点 (Anthropic 兼容) | AC_CP_7 | 同上。 |
| AC3 | 切 model 重起 session + 提示 | AC_CP_1 | 补充了 UI 提示 "已切换模型，会话重起"。 |
| AC4 | 未配 key 灰显 + tooltip | AC_CP_2 | 完全映射。 |
| AC5 | V1.5 卡位 Gemini/OpenAI disabled | AC_CP_5 | 完全映射。 |
| AC6 | Keys 存 ~/.studio/copilot.json chmod 600 (走 backend) | AC_TR_2 | 明确了由 Tauri 前端跨越 FS API，交由 Python 后端代理写入。 |
| AC7 | always-on 不可关 | US-G4, AC_CP_1 | 面板常驻在需求总览已明确约束。 |
| AC8 | Read/Write/Edit/Bash + acceptEdits | AC_CP_4, US-G4 | Frontend 侧需渲染 Tool 状态。 |
| AC9 | tool_use UI "正在 X" + diff | AC_CP_4 | 完全映射，需解析 `tool_use_start/result` 事件。 |
| AC10 | view 切换 POST /copilot/context | AC_CP_3 | 防抖更新 Context API。 |
| AC11 | 聚焦但不拒通用问题 | AC_CP_6 | 前端放行通用对话不拦截。 |
| AC12 | view 切换不重起 session | AC_CP_3 | 明确与 Chat History 状态管理剥离。 |
