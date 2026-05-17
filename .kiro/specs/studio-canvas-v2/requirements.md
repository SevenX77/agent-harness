# Studio Canvas V2 - Requirements (Engine Round-trip)

**Spec**: studio-canvas-v2
**Naming Note**: 旧 `studio-canvas-v1` 是 visual-only scope (4 US, 已 ship 在 `feat/copilot-v1-backend` 分支 commit `e252fe9`); 本 v2 = engine 反向序列化 + GRAPH.md 真正双向编辑, scope 互不重叠
**Status**: Requirements (Kiro Step 1)
**Date**: 2026-05-16
**Author**: a2 (Resident Architect)

## R0. 范围声明与核心立项背景 (多源同步与图形化双向视图)

在 graph_agent 框架的 V2.0 时代，旧有 spec `graph-agent-studio` 曾确立了一条明确的 P1 级别红线：“明确禁止在画布上编辑任何 DSL 内容 (所有修改走 Open CLI)，保护 Copilot 单一事实源契约”。当时的架构下，单个 SKILL 等同于单个 `SKILL.md` 文件，图的拓扑编排、业务逻辑代码以及大语言模型的提示词 (Prompt) 全部混杂在一起。如果允许图形化画布对整个文件进行反向写入，极易破坏 Copilot（如 Claude Code 等 AI 助手）对业务逻辑部分做出的精细修改，引发难以解决的代码冲突与状态不一致。

然而，随着 V2.1 Hard Cutover 阶段的顺利完成（PR #45 已合并至 main 分支，commit `a53e72c`），系统架构发生了根本性的物理分离。如今，一个 SKILL 被解构为多目录和多文件结构：
- **`GRAPH.md` (磁盘文件)**：纯粹的图拓扑 Manifest 文件，专注于阶段（phase）定义及阶段间的有向无环图依赖（`depends_on`），彻底剥离了业务逻辑，是**唯一的 Single Source of Truth (SSOT)**。
- **`phases/<phase_id>/*`**：承载具体业务节点逻辑的文件（如 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md`），专注于提示词与 Python Action 的实现。
- **`io/*.json`**：输入输出 Schema 契约独立存在。

**核心纠正：Canvas 不“拥有”拓扑，GRAPH.md 才是唯一的 Truth。** Canvas-v1 是 `GRAPH.md` 的双向 View，不是拓扑的 owner。任何渠道（无论是 Canvas 画布上的拖拽操作、多文件编辑器 T-apps-1 的直接文本修改、Copilot 的 AI 智能改写，还是外部 IDE / Vim 的手动编辑）都有权平等地修改 `GRAPH.md` 文件。因此，Canvas 的核心使命是：
1. **Read (Downstream) / Live Reflect**：必须忠实地体现 `GRAPH.md` 当前的最新内容，无论修改源头是何方，都必须实时无缝地 live reload 并精准重绘渲染。
2. **Write (Upstream)**：把用户在画布上的拓扑变更操作（增加节点、删除节点、修改依赖）以最高安全级别 persist 序列化回 `GRAPH.md`，与其他修改源平等和谐地共存。

这不仅仅是简单的红线翻转，更是彻底的理念升级：从“各司其职”转变为全面拥抱“多源同步 (Multi-source sync)”。

## R1. 功能需求 (Functional Requirements)

本章节采用标准的 Kiro Acceptance Criteria 格式 ("When X, the system shall Y") 进行需求细化，确保每一个需求点都拥有清晰的触发条件和系统级响应要求。

### R1.1 画布拓扑连线与持久化 (Topology Editing)
- **When** 用户在 React Flow 画布中通过鼠标拖拽，将一个阶段节点的源句柄 (Source Handle) 连接至另一个阶段节点的目标句柄 (Target Handle) 时，
  - **The system shall** 立即在前端状态中构建出一条视觉连线，并在内部拓扑模型中记录新的依赖关系。
- **When** 用户移除一条现有连线时，
  - **The system shall** 取消目标节点对源节点的依赖。
- **When** 触发保存机制时，
  - **The system shall** 将画布当前的完整拓扑状态发送给后端 API，最终反映在持久化文件 `GRAPH.md` 的 `depends_on` 属性变更中。

### R1.2 节点增删同步 (Node Lifecycle)
- **When** 用户通过组件面板或快捷键向画布中添加一个全新阶段（Phase）节点时，
  - **The system shall** 为新节点分配唯一的 phase_id，并在画布上渲染该节点。
- **When** 用户从画布中删除一个阶段节点时，
  - **The system shall** 同步删除与之相连的所有输入和输出连线（边），并从拓扑树中摘除该节点。
- **When** 增删节点的操作被持久化时，
  - **The system shall** 确保后端的 `GRAPH.md` 文件中精确地增加或删除对应的 `<phase ... />` 行，并保持文件的语义合法性。

### R1.3 多入多出支持 (Fan-in / Fan-out)
- **When** 一个源节点被引出多条边连接到多个不同的目标节点（扇出 / Fan-out）时，
  - **The system shall** 在视觉交互上清晰地呈现多分支发散路径，且在运行时阶段交由 Engine 侧已实现的浅合并（shallow_dict_merge）reducer 安全处理并行状态写入。
- **When** 多个源节点连接到同一个目标节点（扇入 / Fan-in）时，
  - **The system shall** 在视觉上呈现多支路聚合至同一目标句柄的形态，并在持久化时将该目标节点的 `depends_on` 属性更新为包含所有源节点 ID 的逗号分隔列表（例如 `depends_on="phase_A, phase_B"`）。

### R1.4 子图结构可视化 (Subgraph Drill-down)
- **When** 渲染的图节点类型为 `SUBGRAPH` 时，
  - **The system shall** 采用特殊的视觉样式（如特定的图标、背景色等）将其与普通 Agent/Logic 节点区分开来。
- **When** 用户对一个 `SUBGRAPH` 节点进行特定的钻入交互（如双击或点击专用按钮）时，
  - **The system shall** 切换当前画布视图，加载并展示该子图所对应的深层内部拓扑结构，并在界面上提供清晰的面包屑（Breadcrumb）导航以支持返回上层。

### R1.5 跨组件协作与文件级编辑关联 (Multi-file Editor Integration)
- **When** 用户在画布上双击一个普通的 Agent 或 Logic 节点时，
  - **The system shall** 不在画布侧边栏内联展开复杂的文本编辑界面，而是向 T-apps-1 统筹的多文件编辑器（Multi-file Editor）发送联动信号。
- **When** 该联动信号被接收时，
  - **The system shall** 自动在代码编辑区域聚焦并打开该节点对应的业务源文件（如 `phases/xxx/LOGIC.md`），实现拓扑与具体业务逻辑实现的丝滑切换。

### R1.6 多源同步 (Multi-source sync)
- **When** 任何外部源（无论是 T-apps-1 的多文件编辑器修改、Copilot 的 AI 直接文件重写、还是用户在外部文本编辑器如 vim 中的直接更改）使得磁盘上的 `GRAPH.md` 发生文件级别变动时，
  - **The system shall** 通过后端的文件监听机制捕捉到变化，并且立刻利用 WebSocket 向所有活跃的客户端广播带有对应 `skill_id` 与 `changed_files` 列表的 `skill_changed` 事件。
- **When** Canvas 收到该文件变动的广播推送（`changed_files` 包含 `GRAPH.md`），
  - **The system shall** 必须立刻执行检查并在 ≤ 2 秒的时间内 live reload 获取最新的文件内容，且通过弹窗等合理手段处理潜在冲突，最终极其忠实地重绘新获取到的拓扑网络状态。保证图形视图永远向唯一的 Truth 看齐。

## R2. 非功能需求 (Non-Functional Requirements)

### R2.1 拓扑自动排版 (Automatic Graph Layout)
放弃当前前端实现中缺乏依赖感知的硬编码位置分配或由后端不精确推断的坐标堆叠。Canvas 必须引入专业的有向无环图 (DAG) 布局算法引擎（如 Dagre），在首次加载和节点变更时自动进行流向清晰、层级分明且无交叉重叠的自动排版计算。这确保了无论图形拓扑多么复杂，用户打开就能看到清爽的流程图。

### R2.2 Minimal Diff 与序列化契约 (Serialization Contract)
前端编辑引发的任何保存操作最终落地到 `GRAPH.md` 时，必须遵守严格的 Minimal Diff 契约。序列化引擎严禁干扰未被修改的文本部分。具体而言：
1. **Frontmatter 不变**：文件头部的 YAML frontmatter 以及其中的任何开发者手工注释必须 100% 字节级保留。
2. **无关行不动**：如果仅修改了 Phase B 的 `depends_on`，那么 Phase A 与 Phase C 的声明行以及它们前后的 Markdown 文本/HTML 注释绝对不允许发生位置飘移或格式重排。保证 Git Commit Diff 干净、易审。

### R2.3 性能指标 (Performance Targets)
- **渲染流畅度**：前端 React Flow 画布在满载 100+ 个 Phase 节点及连线的超大型 SKILL 时，平移、缩放与滚动必须保持流畅，帧率 (FPS) 稳定在 60fps 以上。
- **操作延迟**：画布上拖拽节点或连线的视觉反馈延迟必须 < 16ms（避免掉帧断层感）。
- **序列化效率**：后端执行完整的 `serialize_graph` 算法将 AST 反向序列化为 Markdown 字符串的端到端耗时应 < 200ms。
- **API 响应**：标准的图拓扑增删改查 API 接口的 p95 响应时间必须 < 500ms（单机本地网络环境）。

### R2.4 浏览器 WebView 兼容性 (Tauri Compatibility)
Studio 的运行环境是基于 Tauri 桌面端构建的，其底层的 WebView 是 Wry 封装层。这就意味着在 macOS 上对应的是 WKWebView，在 Windows 上对应的是 WebView2，而在 Linux 侧对应的是 WebKitGTK。Canvas 的技术选型必须确保：
- 使用的 React Flow 11 与 Dagre 等前端图形依赖，能在上述所有的 WebView 内核上正常且一致地渲染，不依赖仅限最新版 Google Chrome 独占的 Web API。
- 对于图形密集型场景，针对渲染性能存在短板的 WebKitGTK (Linux) 保持持续监测和降级渲染可用性的保障。

### R2.5 可观测性与日志埋点 (Observability)
为了协助后续排查由于拓扑持久化引发的潜在 bug，系统必须具备良好的可观测性。
- 后端每次触发 `serialize_graph` 与写入磁盘操作，都需记录操作耗时及修改影响面的日志。
- 前端每一次的拓扑结构变动（onConnect, onDelete, onNodeAdd），都应触发可追溯的用户行为事件记录（Metrics），汇总至 Studio 后端埋点体系，以便后续进行 UX 分析。

### R2.6 容错与错误处理 (Error Handling & Resilience)
在复杂状态机或极端连线错误场景中，底层序列化或者 AST 模型可能会拒绝非法的网络。
- 当后端的 `serialize_graph` 或依赖循环检查 (Cycle Detection) 发现无法序列化的致命错误抛出 Exception 时，后端必须返回标准化的 422 状态码。
- 前端在接收到该错误后，应在 Toast 中清晰展示错误信息给用户，并且能够使得画布的 React Flow state 进行回滚 (Rollback)，自动对齐重新拉取的最后一次安全 Server Snapshot。

## R3. 范围外 (Non-goals)

- **不做** 节点内部的具体业务内容编辑。在 Canvas 画布上，绝不支持修改诸如 system_prompt 内容、Python action 源码、以及 `io/inputs.json` 的具体文本。针对这类详细文本编辑的操作，职责全部划归至 T-apps-1 的多文件编辑器模块中。Canvas 仅是一个用来总览并调整图级别的外层依赖连线的拓扑管理器。
- **不做** 跨不同 SKILL 之间的宏观工作流编排。当前版本的单块 Canvas 画布，其生命周期与上下文严格对应于且仅对应于编辑同一个特定 SKILL 下的唯一单份 `GRAPH.md` 文件。不会出现将 SKILL A 作为节点直接连线至 SKILL B 这种组合场景。
- **不做** 原生的节点操作历史撤销/重做栈 (Undo/Redo Stack)（此特性作为长远规划，留待 V2 后续迭代中实现）。
- **不做** 多人同时在线时的实时游标协作与 CRDT 同步（此特性留待云端化版本实现）。

## R4. Open Questions

1. **复杂拓扑编辑与新建文件竞争**：当 Canvas 新增阶段节点时，由于 T-apps-1 的文件系统也处于激活状态，是否需要由 backend boilerplate 自动生成空的逻辑挂载文件，还是仅仅在编译层报出“缺少 src 文件”的红牌警告让用户手工创建填补？
2. **孤儿阶段节点 (Orphan Phases) 的视觉容忍策略**：若用户移除某节点的全部边连线致其断联成为“孤儿”，在 UI 层面上是立刻通过自动清理机制抹除掉，还是暂时发出高亮红框警告容忍它作为脱机组件序列化保留以备后续重新连接？
3. **跨文件联动的巨型文本延迟阻断**：双击节点联动跳转 T-apps-1 打开极其巨大的 Markdown Prompt Tab 时，1-2秒级的渲染耗时是否需要加上全屏强制 Loading Overlay 遮罩来消除割裂体验感？