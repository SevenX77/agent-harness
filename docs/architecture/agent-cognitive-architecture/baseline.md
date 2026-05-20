# agent-cognitive-architecture (architecture) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: baseline: 旧 GraphAgentHarness 单文件线性控制流; MVP0: V2.1 LangGraph DAG + LOGIC/SUBGRAPH/SKILL 三态心智模型
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

这份架构 baseline 描述的是当前“认知模型”如何反映到 Studio UI，而不是 UI 本身。现在系统同时存在两套心智模型：旧 `GraphAgentHarness` 的多 phase 线性/路由控制流，以及 V2.1 的 `GRAPH.md` + LangGraph DAG。旧 Harness 仍然是一个完整类，定义在 `packages/graph-agent/src/graph_agent/core/harness.py:331` 到 `packages/graph-agent/src/graph_agent/core/harness.py:354`；V2.1 运行入口则在 `_run_v21_skill_dict()`，见 `packages/graph-agent/src/graph_agent/core/runner.py:451` 到 `packages/graph-agent/src/graph_agent/core/runner.py:486`。

Studio 画布当前展示的是“节点 + 边”的 DAG 心智模型。GraphCanvas 用 React Flow 渲染 nodes/edges，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`。节点来自 manifest phase，V2.1 manifest phases 被转换为前端 phase 节点，见 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:20` 到 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:29`；边来自 `depends_on`，见 `apps/studio/frontend/src/components/nodes/buildEdges.ts:23` 到 `apps/studio/frontend/src/components/nodes/buildEdges.ts:49`。

术语说明：DAG 是 Directed Acyclic Graph，有向无环图。UI 上看就是每个 phase 是一个节点，`depends_on` 是一条从上游到下游的线。旧 Harness 的 mental model 更像“一个带重试和回调的执行器”，V2.1 mental model 更像“声明式图结构交给 LangGraph 调度”。Studio UI 当前主要采用后者，但底层 engine 里前者仍然存在。

phase 状态在 UI 上表现为节点状态、Trace 列表、Compile 面板和运行历史；这些状态不由 architecture 文档直接生成，而是来自 backend API 和 websocket。运行事件 WebSocket 是 `/ws/runs/{run_id}`，后端路由见 `apps/studio/backend/app/routers/websockets.py:27` 到 `apps/studio/backend/app/routers/websockets.py:39`。这说明认知架构对 UI 的影响是“数据结构约束”，不是组件约束。

当前 UI 没有把旧 Harness 的 retry router、heartbeat、checkpoint、IO mapping 分别呈现成独立一等对象。旧 Harness 这些概念集中在 `GraphAgentHarness.__init__()` 和 run setup 中，见 `packages/graph-agent/src/graph_agent/core/harness.py:356` 到 `packages/graph-agent/src/graph_agent/core/harness.py:390`、`packages/graph-agent/src/graph_agent/core/harness.py:568` 到 `packages/graph-agent/src/graph_agent/core/harness.py:629`。因此 UI 上看到的“节点失败/事件流”只是 orchestration 的投影，不是完整 Harness state。

当前 UI 也没有把 V2.1 的三态节点精确外显为三种视觉节点。前端 manifest phase 映射用 `mode: 'logic'`，见 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:20` 到 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:29`；engine 真实分支在 `_build_phase_node()`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:99` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:113`。所以当前 UI 能表达拓扑，但不能完整表达 LOGIC/SUBGRAPH/SKILL 的执行语义差异。

Canvas 交互的边界也很清楚。ReactFlow 提供点击、双击、MiniMap、Controls、Background 等画布体验，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`。这些交互帮助用户浏览 graph，但没有改变 engine 的 graph assembly 或 blackboard reducer。

从用户视角看，compile 面板和 run 面板是同一认知链路的两个窗口：compile 解释 skill 能否形成 graph，run 解释 graph 是否能执行。前端 compile 调用在 `apps/studio/frontend/src/api/client.ts:81` 到 `apps/studio/frontend/src/api/client.ts:90`，run 调用在 `apps/studio/frontend/src/api/client.ts:140` 到 `apps/studio/frontend/src/api/client.ts:144`。两者都通过 Studio backend 间接触达 graph-agent。

当前 UI 不直接暴露 `BlackboardState`。用户看到的是 RunDetail、events、artifacts，而不是 `data/flow/messages/run_id` 的原始 TypedDict。`BlackboardState` 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`；Studio run detail 读取逻辑在 `apps/studio/backend/app/services/run_manager.py:408` 到 `apps/studio/backend/app/services/run_manager.py:422`。

这个 baseline 因此把 UI/UX 结论限定为现状：Studio 已经采用 DAG 浏览心智模型，但 engine 内部还保留旧 Harness 心智模型；UI 没有证明架构已经完全切换，只证明 V2.1 拓扑已经成为主要展示对象。

## 前端逻辑

前端消费的是 Studio backend 的 skill detail、compile result、run events 和 Copilot context，不直接运行 graph-agent。API client 默认指向 `VITE_STUDIO_API_BASE_URL` 或 `http://localhost:8787/api`，见 `apps/studio/frontend/src/api/client.ts:20` 到 `apps/studio/frontend/src/api/client.ts:27`；compile 调用 `POST /skills/{skillId}/compile`，见 `apps/studio/frontend/src/api/client.ts:81` 到 `apps/studio/frontend/src/api/client.ts:90`；run 调用 `POST /skills/{skillId}/runs`，见 `apps/studio/frontend/src/api/client.ts:140` 到 `apps/studio/frontend/src/api/client.ts:144`。

GraphCanvas 的前端心智模型有一个当前偏差：V2.1 phase 在 `phasesFromManifest()` 里被映射成 `mode: 'logic'` 的前端 phase def，见 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:20` 到 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:29`。这只是前端展示/兼容层，不等于 engine 里 V2.1 只有 LOGIC。engine 真实三态是 `LogicNodeAST`、`SubgraphNodeAST`、`SkillNodeAST`，定义在 `packages/graph-agent/src/graph_agent/core/manifest.py:69` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:90`。

Copilot context 也属于前端消费认知模型的一部分。Workspace 会把当前选中节点等 view context 送给 Copilot context hook，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:65` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:75`；hook POST 的 payload 是 `view/context/timestamp`，见 `apps/studio/frontend/src/hooks/useCopilotContext.ts:39` 到 `apps/studio/frontend/src/hooks/useCopilotContext.ts:63`。这不是旧架构文档里写的 `build_copilot_session(skill_id, error_log)` 伪代码，也不是 spec 里期待的 `mentions` 数组。

High-002 当前必须暴露：前端 Copilot WebSocket 发送消息时只构造 `{ user_message, model_override? }`，见 `apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`。没有 `mentions: [{type:'file', id:'...'}]`，也没有 trace event mention 或 node mention payload。后端 `CopilotWsRequestPayload` 同样只有 `user_message` 和 `model_override`，见 `apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:27`。

前端还有一个分层事实：Canvas、Copilot、Run 面板并不共享一个显式的“cognitive session model”。Canvas 通过 GraphCanvas props 消费 nodes/edges，Copilot 通过 context hook 发送 view context，Run 通过 API/WS 读取 events。API client 的 base URL、token header、WebSocket URL 处理分别在 `apps/studio/frontend/src/api/client.ts:20` 到 `apps/studio/frontend/src/api/client.ts:27`、`apps/studio/frontend/src/api/client.ts:46` 到 `apps/studio/frontend/src/api/client.ts:54`、`apps/studio/frontend/src/api/client.ts:101` 到 `apps/studio/frontend/src/api/client.ts:108`。

这意味着前端认知层当前是“多个 feature 通过 backend contract 间接对齐”，不是一个统一 store 驱动所有 feature。selected node context 通过 Workspace 进入 Copilot，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:65` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:75`；但 Copilot WebSocket payload 没有携带 node id 或 file mention，见 `apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`。

前端 DAG 的边来源是 structural dependency，不是运行时数据依赖。`buildEdges()` 读取 `dependsOn/root/output` 构边，见 `apps/studio/frontend/src/components/nodes/buildEdges.ts:23` 到 `apps/studio/frontend/src/components/nodes/buildEdges.ts:49`。engine 的 `ContextBridge` 只在 manifest model 中定义，见 `packages/graph-agent/src/graph_agent/core/manifest.py:26` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:32`；当前 Canvas 不把它作为完整 IO contract 展示。

对前端来说，V2.1 的三态差异目前主要通过 compile/runtime 后端信息体现，而不是前端类型系统体现。`LogicNodeAST`、`SubgraphNodeAST`、`SkillNodeAST` 的差异定义在 Python manifest model 中，见 `packages/graph-agent/src/graph_agent/core/manifest.py:69` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:90`。这也是 architecture baseline 需要引用后端和 engine 的原因。

Copilot 的 context update 是 REST，chat 是 WebSocket。context update model 是 `ContextUpdateRequest`，见 `apps/studio/backend/app/models/copilot.py:73` 到 `apps/studio/backend/app/models/copilot.py:80`；chat model 是 `CopilotWsRequestPayload`，见 `apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:27`。两者分开使得“当前视图”可以进入 prompt，但“用户这句话明确提到哪些文件/节点/trace”仍没有结构化状态。

所以 High-002 的前端结论不是“Copilot 没上下文”，而是“Copilot 有 view context，但没有 mentions payload contract”。旧审计指出的 file mention 形态没有在 `useCopilot.ts` 或 `CopilotWsRequestPayload` 中落地，见 `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:29` 到 `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:36`。

## 后端功能

当前后端职责分成两层。Studio backend 是 FastAPI 外壳，注册 skills、runs、copilot、llm、websockets 等路由，见 `apps/studio/backend/app/main.py:112` 到 `apps/studio/backend/app/main.py:140`。graph-agent engine 是 Python package，提供 compile/run/graph assembly 和 legacy Harness。

旧 `GraphAgentHarness` 是完整的多 phase orchestration engine。它在初始化时接收 `phases`、callbacks、IO config、context mapping、skill_dir、checkpointer，并构建 `GraphBuilder`，见 `packages/graph-agent/src/graph_agent/core/harness.py:356` 到 `packages/graph-agent/src/graph_agent/core/harness.py:390`。它的 run 过程会创建 RunContext、Heartbeat、PhaseExecutor，并把 executor 通过 LangGraph config 传入，见 `packages/graph-agent/src/graph_agent/core/harness.py:568` 到 `packages/graph-agent/src/graph_agent/core/harness.py:629`。这套路径还包含 IOManager 和 ContextResolver，见 `packages/graph-agent/src/graph_agent/core/harness.py:831` 到 `packages/graph-agent/src/graph_agent/core/harness.py:856`。

V2.1 路径更短：`run_skill()` 先调用 `_run_skill_dict()`，当入口是目录时进入 `_run_v21_skill_dict()`，见 `packages/graph-agent/src/graph_agent/core/runner.py:161` 到 `packages/graph-agent/src/graph_agent/core/runner.py:224`、`packages/graph-agent/src/graph_agent/core/runner.py:270` 到 `packages/graph-agent/src/graph_agent/core/runner.py:277`。V2.1 分支删除 callbacks，编译 skill，装配 graph，再 `graph.invoke()`，见 `packages/graph-agent/src/graph_agent/core/runner.py:451` 到 `packages/graph-agent/src/graph_agent/core/runner.py:486`。

V2.1 DAG 装配由 `assemble_graph()` 负责。它创建 `StateGraph(BlackboardState)`，按 manifest phases 添加 node，按 `depends_on` 添加 edge，再连接 terminal phase 到 END，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:96`。三态分发在 `_build_phase_node()`：LOGIC、SUBGRAPH、SKILL 分别走不同 builder，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:99` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:113`。

这两套并存状态是 transition state，不是完全统一的新架构。旧 runner 路径仍会默认创建 `LoggingCallback()` 和 `TracingCallback()`，并加载 cached Harness，见 `packages/graph-agent/src/graph_agent/core/runner.py:284` 到 `packages/graph-agent/src/graph_agent/core/runner.py:307`。V2.1 分支则 `del callbacks`，见 `packages/graph-agent/src/graph_agent/core/runner.py:462`。engine baseline 已记录 P0-1：V2.1 无真实 LLM 路径，`chat_model` 只有 mock 能填，SKILL node 无模型会抛 RuntimeError，见 `docs/engine/execution-runtime/baseline.md:145`。

Studio backend 对 engine 的使用也分开。compile 走 `compile_skill(skill_dir, cache=False)` 并转成 Studio compile contract，见 `apps/studio/backend/app/services/skills.py:294` 到 `apps/studio/backend/app/services/skills.py:311`。run 走 subprocess entrypoint，构造 `StudioQueueCallback` 和 `TracingCallback` 后调用 `run_skill()`，见 `apps/studio/backend/app/services/run_manager.py:220` 到 `apps/studio/backend/app/services/run_manager.py:235`。这意味着 Studio 希望用 callback/trace，但 V2.1 engine 主线当前不完整接入，见 `docs/engine/tracing-and-observability/baseline.md:23` 到 `docs/engine/tracing-and-observability/baseline.md:27`。

Copilot 后端不是 graph runtime。它使用 Claude Agent SDK session，解析 `copilot_chat` role 或 model override，再将 view context 注入 system prompt，见 `apps/studio/backend/app/services/copilot.py:183` 到 `apps/studio/backend/app/services/copilot.py:223`。view context 缓存在 `_view_contexts`，更新逻辑见 `apps/studio/backend/app/services/copilot.py:117` 到 `apps/studio/backend/app/services/copilot.py:140`；system prompt 拼接见 `apps/studio/backend/app/services/copilot.py:165` 到 `apps/studio/backend/app/services/copilot.py:180`。

旧 Harness 的后端功能还包括 checkpointer 解析。`_resolve_checkpointer()` 支持直接传入、禁用、env override 和 SQLite URI，见 `packages/graph-agent/src/graph_agent/core/harness.py:391` 到 `packages/graph-agent/src/graph_agent/core/harness.py:430`。这属于旧 orchestration 侧的持久化能力；V2.1 `_run_v21_skill_dict()` 当前没有把等价 checkpointer 注入到 `assemble_graph()` 调用中，见 `packages/graph-agent/src/graph_agent/core/runner.py:451` 到 `packages/graph-agent/src/graph_agent/core/runner.py:486`。

旧 Harness 的 IO 功能也仍在代码里。`_build_context_from_io()` 通过 IOManager 和 ContextResolver 解析输入上下文，见 `packages/graph-agent/src/graph_agent/core/harness.py:831` 到 `packages/graph-agent/src/graph_agent/core/harness.py:856`；`_save_outputs_via_io()` 保存 declared outputs，见 `packages/graph-agent/src/graph_agent/core/harness.py:858` 到 `packages/graph-agent/src/graph_agent/core/harness.py:890`。V2.1 baseline 中 A1/A2/A3/A6 缺口说明新路径还没有同等完整 input funnel 和 phase IO contract，见 `docs/engine/state-and-io-contract/baseline.md:99` 到 `docs/engine/state-and-io-contract/baseline.md:127`。

V2.1 LOGIC node 当前是确定性 action 包装。builder 创建 Context，执行 `action(ctx)`，再把 delta 写回 `data`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:116` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:138`。这说明 LOGIC 的认知角色是“纯函数式状态变换近似”，不是 LLM agent。

V2.1 SUBGRAPH node 当前会 compile child graph，把 parent `data/flow` 传入 child，再把 child result 与 parent state 做 diff 回写，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:141` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:174`。这说明 SUBGRAPH 的认知角色是“固定子图委派”，但其隔离性和 IO 边界仍由当前 shallow state/diff 机制限制。

V2.1 SKILL node 当前是最接近 agent phase 的部分。它准备 tools/subagents/finish_task，注入 messages 和 exit_contract，处理 tool calls，并把 finish_task 写入 state，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:177` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:298`。但在没有 chat_model 时会抛 RuntimeError，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:229` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

`CompiledStateGraph` 只是 graph、manifest、root_dir 的轻 wrapper，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:41` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:47`。它不包含 Studio callback schema、run artifact schema 或 Copilot context。架构上这说明 V2.1 graph assembly 与 Studio runtime presentation 仍是两层。

`Harness = GraphAgentHarness` alias 仍存在，见 `packages/graph-agent/src/graph_agent/core/harness.py:1150`。这不是功能 bug，但它说明 public surface 仍承认旧 Harness 作为 engine 概念。architecture baseline 不能把旧 Harness 当成已删除实现。

Studio run worker 用 subprocess 隔离运行。worker 创建 callbacks 后调用 `run_skill()`，见 `apps/studio/backend/app/services/run_manager.py:220` 到 `apps/studio/backend/app/services/run_manager.py:235`。这使 Studio 能把 engine 执行转成队列事件，但并不改变 V2.1 `_run_v21_skill_dict()` 对 callbacks 的处理。

`StudioQueueCallback` 把 graph-agent callback event 转成 Studio event queue，见 `apps/studio/backend/app/services/run_manager.py:87` 到 `apps/studio/backend/app/services/run_manager.py:130`。这个 adapter 是 Studio trace/runner 认知层的一部分；它依赖 engine 发出 callback，而不是从 LangGraph state 自动推断所有事件。

综上，后端现状不是“单一 graph runtime”。它是旧 Harness runtime、V2.1 graph assembler、Studio run manager、Copilot service 四条后端路径并存，并通过 API、callbacks、文件 artifacts 和 view context 松散连接。

## API

核心 engine API 有两类。旧 public API 是 `run_skill(skill_path, ..., **inputs) -> WorkflowResult`，签名在 `packages/graph-agent/src/graph_agent/core/runner.py:161` 到 `packages/graph-agent/src/graph_agent/core/runner.py:173`。V2.1 compile API 是 `compile_skill()`，Studio 调用点见 `apps/studio/backend/app/services/skills.py:303`。V2.1 graph assembly API 是 `assemble_graph(compiled, chat_model=...) -> CompiledStateGraph`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:41` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:60`。

Studio API 以 HTTP 和 WebSocket 暴露。`GET /api/skills/{skill_id}` 返回 SkillDetail，见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:105`；`POST /api/skills/{skill_id}/compile` 返回 compile result 或 422 compile failure，见 `apps/studio/backend/app/routers/skills.py:108` 到 `apps/studio/backend/app/routers/skills.py:118`；`POST /api/skills/{skill_id}/runs` 启动 run，见 `apps/studio/backend/app/routers/runs.py:27` 到 `apps/studio/backend/app/routers/runs.py:29`；`GET /api/skills/{skill_id}/runs/{run_id}` 返回 run detail，见 `apps/studio/backend/app/routers/runs.py:53` 到 `apps/studio/backend/app/routers/runs.py:55`。

Copilot API 当前有三条：dispatch REST endpoint 存在但 not implemented，见 `apps/studio/backend/app/routers/copilot.py:23` 到 `apps/studio/backend/app/routers/copilot.py:31`；WebSocket `/api/skills/{skill_id}/copilot/ws` 接收 `CopilotWsRequestPayload`，见 `apps/studio/backend/app/routers/copilot.py:34` 到 `apps/studio/backend/app/routers/copilot.py:54`；context POST `/api/skills/{skill_id}/copilot/context` 接收 view context，见 `apps/studio/backend/app/models/copilot.py:73` 到 `apps/studio/backend/app/models/copilot.py:80`。

API 层的一个重要边界是：Studio HTTP API 返回的是 Studio DTO，不是 engine native object。`GET /api/skills/{skill_id}` 由 skills router 调 service 返回 SkillDetail，见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:105`；compile endpoint 捕获 CompileError 后转成 HTTP 422，见 `apps/studio/backend/app/routers/skills.py:108` 到 `apps/studio/backend/app/routers/skills.py:118`。这说明 UI 看到的是后端整理后的 contract。

run API 也不直接返回 `BlackboardState`。`POST /api/skills/{skill_id}/runs` 返回 run 创建结果，见 `apps/studio/backend/app/routers/runs.py:27` 到 `apps/studio/backend/app/routers/runs.py:29`；后续 detail endpoint 再读取 run directory，见 `apps/studio/backend/app/routers/runs.py:53` 到 `apps/studio/backend/app/routers/runs.py:55`、`apps/studio/backend/app/services/run_manager.py:408` 到 `apps/studio/backend/app/services/run_manager.py:422`。

WebSocket API 分两类：run events 和 Copilot chat。run events route 是 `/ws/runs/{run_id}`，见 `apps/studio/backend/app/routers/websockets.py:27` 到 `apps/studio/backend/app/routers/websockets.py:39`；Copilot chat route 在 copilot router，见 `apps/studio/backend/app/routers/copilot.py:34` 到 `apps/studio/backend/app/routers/copilot.py:54`。两者没有共享一个 event envelope model。

engine API 的 `run_skill()` 是兼容入口。它能处理 legacy path 和 V2.1 path，分支点在 `_run_skill_dict()`，见 `packages/graph-agent/src/graph_agent/core/runner.py:270` 到 `packages/graph-agent/src/graph_agent/core/runner.py:277`。这使 Studio 可以调用同一个 Python API，但也让 architecture baseline 必须同时记录两套 runtime 行为。

V2.1 graph API `assemble_graph()` 接收 `CompiledSkill` 和可选 `chat_model`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:60`。runner 当前在非 mock 情况下传入 `chat_model = None`，见 `packages/graph-agent/src/graph_agent/core/runner.py:467` 到 `packages/graph-agent/src/graph_agent/core/runner.py:474`。这就是 P0-1 与 architecture 的 API 层映射。

API 层没有 file mention contract。前端 payload、后端 request model、copilot route 都没有 `mentions` 字段，见 `apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`、`apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:27`、`apps/studio/backend/app/routers/copilot.py:34` 到 `apps/studio/backend/app/routers/copilot.py:54`。这就是 High-002 在 API 维度的 exposed bug。

## Data Model / State

V2.1 graph 的数据模型从 `GraphManifest` 开始。`GraphPhaseRef` 包含 `id/src/depends_on`，见 `packages/graph-agent/src/graph_agent/core/manifest.py:16` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:23`；`GraphManifest` 包含 schema version、name、IO refs、phases、metadata，见 `packages/graph-agent/src/graph_agent/core/manifest.py:45` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:56`。

三态 node AST 是 `LogicNodeAST`、`SubgraphNodeAST`、`SkillNodeAST`。LOGIC 是确定性 Python action，`python_callable` 在 `packages/graph-agent/src/graph_agent/core/manifest.py:69` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:73`；SUBGRAPH 是固定子图委派，`sub_skill_ref` 在 `packages/graph-agent/src/graph_agent/core/manifest.py:76` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:80`；SKILL 是 LLM ReAct phase，含 `system_prompt`、`exit_contract`、tools、subagents，见 `packages/graph-agent/src/graph_agent/core/manifest.py:83` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:90`。

运行 state 是 `BlackboardState`：`data`、`flow`、`messages`、`run_id`，见 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`。`data` 使用 `shallow_dict_merge`，该 reducer 遇到同名 key 会抛 `[F-v21-state-conflict]`，见 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:32`。这解释了当前认知模型不是“每个 phase 独立 IO”，而是共享黑板；相关缺口详见 [state-and-io-contract baseline](../../engine/state-and-io-contract/baseline.md)。

Studio run detail 把 engine 结果重新包装为 `RunDetail`：metadata、input_data、events、final_context、artifacts，读取逻辑见 `apps/studio/backend/app/services/run_manager.py:408` 到 `apps/studio/backend/app/services/run_manager.py:422`。前端看到的是这个外壳状态，不是直接看到 `BlackboardState`。

Copilot state 当前是两层：一个是 WebSocket 消息 payload，只含 user message 和 model override；另一个是 view context cache，只含 view/context/timestamp。没有 mentions 数组，没有“文件/节点/trace event 引用”的显式状态模型。这是 High-002 在当前 baseline 中的结论。

`GraphPhaseRef.depends_on` 是拓扑依赖，不是数据 schema。它定义在 `packages/graph-agent/src/graph_agent/core/manifest.py:16` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:23`；`assemble_graph()` 只用它连接 edge，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:80` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:88`。数据依赖仍由 shared blackboard 和 node action 自己处理。

`ContextBridge` 在 manifest model 中提供 parent/child data mapping 的结构位，见 `packages/graph-agent/src/graph_agent/core/manifest.py:26` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:32`。但当前 architecture baseline 不能把它描述成完整可视化/验证的 IO contract，因为 engine state baseline 已记录 phase-level IO contract 缺口，见 `docs/engine/state-and-io-contract/baseline.md:99` 到 `docs/engine/state-and-io-contract/baseline.md:127`。

`shallow_dict_merge` 的冲突语义很关键。它只做顶层浅合并，同名 key 冲突直接抛异常，见 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:32`。这意味着认知模型里的“多 phase 协作”现在依赖 phase 避免写同一顶层 key，而不是依赖 typed output slots 自动隔离。

`messages` 在 V2.1 `BlackboardState` 中存在，见 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`，但 LOGIC/SUBGRAPH 并不天然都用它。SKILL node 会把 prompt 和 user message 注入 messages，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:236` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:246`。所以当前 message state 主要服务 LLM skill node，不是全局 trace。

旧 Harness 有自己的 runtime storage 和 working memory 概念，类 docstring 已声明 working memory、callbacks、validation retries、cognitive templates 等职责，见 `packages/graph-agent/src/graph_agent/core/harness.py:331` 到 `packages/graph-agent/src/graph_agent/core/harness.py:354`。V2.1 的 state 则集中在 `BlackboardState` 和 LangGraph graph 中，见 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:55` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:96`。

Studio 的 state model 是二次包装。Run manager 从 filesystem 读取 trace、final state、artifacts 并拼成 detail，见 `apps/studio/backend/app/services/run_manager.py:408` 到 `apps/studio/backend/app/services/run_manager.py:422`。这让 Studio 能保留运行历史，但也说明 Studio state 不等于 engine state。

Copilot 的 view context 使用普通 dict 缓存，更新入口是 `set_view_context()`，见 `apps/studio/backend/app/services/copilot.py:117` 到 `apps/studio/backend/app/services/copilot.py:140`。system prompt 注入发生在 query 前，见 `apps/studio/backend/app/services/copilot.py:165` 到 `apps/studio/backend/app/services/copilot.py:180`。这是一种 prompt-time context，不是 graph state。

数据模型层最终暴露三个核心事实：engine V2.1 共享黑板，Studio 运行记录是 artifacts/detail，Copilot 上下文是 view context cache。三者没有统一 schema，这正是 architecture 层需要跨 feature 标注的当前状态。

## Cross-feature interaction

与 engine baselines：本 architecture 是总览，具体 bug 和边界已经落在 engine 四份 baseline。V2.1 真实 LLM 路径不可用、callbacks 未接、A4/A5 subagent/call_subgraph 缺口见 [execution-runtime baseline](../../engine/execution-runtime/baseline.md)。共享黑板、缺 input funnel、缺 phase-level IO contract 见 [state-and-io-contract baseline](../../engine/state-and-io-contract/baseline.md)。

与 Studio Canvas：Canvas 使用 DAG 视图显示 phase/edge，但当前 edge 主要来自 `depends_on`，不是完整数据流 contract。Canvas baseline 见 [canvas-topology baseline](../../studio/feature-folders/canvas-topology/baseline.md)。

与 Trace：Studio 后端希望通过 `StudioQueueCallback` 和 `TracingCallback` 获取事件，见 `apps/studio/backend/app/services/run_manager.py:87` 到 `apps/studio/backend/app/services/run_manager.py:130`，但 V2.1 engine 分支删除 callbacks。Trace 当前状态见 [tracing-and-observability baseline](../../engine/tracing-and-observability/baseline.md) 和 [Studio trace-visualization baseline](../../studio/feature-folders/trace-visualization/baseline.md)。

与 Copilot：旧 architecture doc 的伪代码说后端 `build_copilot_session(skill_id, error_log)` 直接拼上下文；当前真实实现是前端异步 POST view context，WebSocket 只发 user_message/model_override，后端 system prompt 从 cached view context 注入。这和 High-002 指出的 mentions payload 缺失一致，具体 feature 现状见 [copilot-assistance baseline](../../studio/feature-folders/copilot-assistance/baseline.md)。

与 prod/dev separation：本文件描述认知模型并存；进程边界、Tauri sidecar、dev tunnel、Python runtime bundle 在 [prod-dev-separation baseline](../prod-dev-separation/baseline.md)。两者交叉点是 Studio backend 调用 graph-agent Python API，而不是通过独立 engine service。

与 compile contract：Studio compile endpoint 调用 graph-agent compile 并转成 Studio contract，见 `apps/studio/backend/app/services/skills.py:294` 到 `apps/studio/backend/app/services/skills.py:311`。这让 Canvas 能显示 DAG，但 compile contract 不能证明 run-time LLM path、callbacks、IO contract 都完整。

与 execution runtime：P0-1、P1-2、P1-3、P1-4、A4、A5 的具体 runtime 缺口已经写在 [execution-runtime baseline](../../engine/execution-runtime/baseline.md)。本文件只在 architecture 层说明这些缺口如何影响“agent cognitive architecture”这个总心智模型。

与 state/io contract：A1/A2/A3/A6 说明共享 blackboard、input funnel、phase IO、subgraph IO 仍没有形成完整 production contract，见 [state-and-io-contract baseline](../../engine/state-and-io-contract/baseline.md)。因此 architecture baseline 不能把 DAG 画布解释成强类型数据流编辑器。

与 tracing：V2.1 callbacks 未接导致 Studio trace 不能完整覆盖新 DAG runtime，见 [tracing-and-observability baseline](../../engine/tracing-and-observability/baseline.md)。这影响用户对 agent cognition 的观察能力：看到事件不等于看到完整 LangGraph state transition。

与 Copilot High-002 audit：audit 要求暴露 file mentions payload 缺失，见 `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:29` 到 `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:36`。本文件在 UI、前端、API、Data Model 四个维度都明确写出：当前只有 view context 和 user message/model override，没有 mentions。

与 legacy Harness：旧 Harness 不是历史文档残影，而是当前 public code surface。`Harness = GraphAgentHarness` 在 `packages/graph-agent/src/graph_agent/core/harness.py:1150`，runner legacy path 仍加载 cached Harness，见 `packages/graph-agent/src/graph_agent/core/runner.py:288` 到 `packages/graph-agent/src/graph_agent/core/runner.py:307`。所以所有 architecture 结论都必须保留“并存”而不是“已迁移完成”的表述。

最终边界：本 baseline 不写改造方案，不承诺 MVP0 已完成，不替 engine baseline 详细列 bug，不替 Studio feature baseline 描述 UI 细节。它只记录当前代码里“用户看到的 DAG 认知模型、后端仍存在的 Harness/V2.1 双轨、Copilot 上下文缺 mentions、state/trace/API 未完全统一”这些跨层事实。

Audit 映射补充：P0-1 对应 SKILL node 无真实 LLM model 的 runtime 断点。runner 在非 mock 情况下传 `chat_model = None`，见 `packages/graph-agent/src/graph_agent/core/runner.py:467` 到 `packages/graph-agent/src/graph_agent/core/runner.py:474`；SKILL node 无 chat_model 会 RuntimeError，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:229` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

Audit 映射补充：P1-4 对应 callbacks/tracing 未接入 V2.1。legacy runner 会创建 Logging/Tracing callbacks，见 `packages/graph-agent/src/graph_agent/core/runner.py:284` 到 `packages/graph-agent/src/graph_agent/core/runner.py:286`；V2.1 runner 删除 callbacks，见 `packages/graph-agent/src/graph_agent/core/runner.py:462`。Studio run manager 仍期待 callbacks，见 `apps/studio/backend/app/services/run_manager.py:228` 到 `apps/studio/backend/app/services/run_manager.py:235`。

Audit 映射补充：A1/A2/A3/A6 属于 state/io 层，不可在 architecture 文档里伪装成已解决。当前 V2.1 `BlackboardState` 只有 `data/flow/messages/run_id`，见 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`；相关边界见 `docs/engine/state-and-io-contract/baseline.md:99` 到 `docs/engine/state-and-io-contract/baseline.md:127`。

Audit 映射补充：A4/A5 影响 SUBGRAPH/SKILL 的 agent 心智模型。SUBGRAPH 当前通过 child graph invoke 和 diff 回写工作，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:141` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:174`；SKILL 的 tools/subagents/finish_task 路径见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:177` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:298`。具体缺口仍以 [execution-runtime baseline](../../engine/execution-runtime/baseline.md) 为准。

Studio 映射补充：Canvas 只消费 graph topology，不消费 Harness retry/checkpoint semantics。Canvas nodes/edges 渲染见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`；Harness retry/router/checkpointer 初始化见 `packages/graph-agent/src/graph_agent/core/harness.py:356` 到 `packages/graph-agent/src/graph_agent/core/harness.py:430`。

Studio 映射补充：Compile success 只是 graph 可构建，不等于 run 可完整执行。compile endpoint 见 `apps/studio/backend/app/routers/skills.py:108` 到 `apps/studio/backend/app/routers/skills.py:118`；V2.1 run invoke 见 `packages/graph-agent/src/graph_agent/core/runner.py:476` 到 `packages/graph-agent/src/graph_agent/core/runner.py:486`。P0-1 就发生在 run-time SKILL node，而不是 compile-time manifest parsing。

Studio 映射补充：Run event visibility 依赖 event pipeline。WebSocket route 见 `apps/studio/backend/app/routers/websockets.py:27` 到 `apps/studio/backend/app/routers/websockets.py:39`；StudioQueueCallback 见 `apps/studio/backend/app/services/run_manager.py:87` 到 `apps/studio/backend/app/services/run_manager.py:130`。如果 engine 分支不发 callback，UI event stream 就不能完整反映认知执行过程。

Copilot 映射补充：view context 是当前代码的真实上下文入口。frontend POST context 见 `apps/studio/frontend/src/hooks/useCopilotContext.ts:39` 到 `apps/studio/frontend/src/hooks/useCopilotContext.ts:63`；backend set_view_context 见 `apps/studio/backend/app/services/copilot.py:117` 到 `apps/studio/backend/app/services/copilot.py:140`。这条路径不能替代 mentions payload。

Copilot 映射补充：backend prompt 注入是 system prompt 拼接，不是结构化 reference resolver。`build_system_prompt()` 见 `apps/studio/backend/app/services/copilot.py:165` 到 `apps/studio/backend/app/services/copilot.py:180`；stream query 调用 Claude Agent SDK client，见 `apps/studio/backend/app/services/copilot.py:183` 到 `apps/studio/backend/app/services/copilot.py:223`。

API 映射补充：Copilot dispatch REST endpoint 当前 not implemented，见 `apps/studio/backend/app/routers/copilot.py:23` 到 `apps/studio/backend/app/routers/copilot.py:31`。因此 architecture baseline 不应把 Copilot 写成“REST dispatch + session builder”的旧伪代码形态。

Data 映射补充：`GraphManifest` 的 `phases` 和 metadata 形成 graph 编译输入，见 `packages/graph-agent/src/graph_agent/core/manifest.py:45` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:56`。但运行时状态仍由 LangGraph state 管理，不是 manifest 自身保存。

Data 映射补充：`CompiledStateGraph` 保存 graph、manifest、root_dir，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:41` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:47`。它没有保存 Studio run_id、artifact paths、Copilot session 或 UI selection。

Boundary 补充：本文件引用 engine baseline 和 Studio feature baseline 只是 cross-link，不修改这些文件。architecture 这里记录的是跨层事实，而不是替代每个 feature 的详细 baseline。

Boundary 补充：本文没有把旧 Harness 删除、迁移或降级为 dead code。只要 `GraphAgentHarness` 和 `Harness = GraphAgentHarness` 仍在，见 `packages/graph-agent/src/graph_agent/core/harness.py:331` 到 `packages/graph-agent/src/graph_agent/core/harness.py:354`、`packages/graph-agent/src/graph_agent/core/harness.py:1150`，baseline 就必须写成双轨并存。

Boundary 补充：本文没有把 V2.1 说成不可用；它能 compile/assemble/invoke graph，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:96`、`packages/graph-agent/src/graph_agent/core/runner.py:476` 到 `packages/graph-agent/src/graph_agent/core/runner.py:486`。结论只是当前若干 production contract 不完整。

Boundary 补充：本文没有把 Studio UI 说成 engine。前端 API client、Canvas、Copilot hook 都只通过 backend contract 工作，见 `apps/studio/frontend/src/api/client.ts:20` 到 `apps/studio/frontend/src/api/client.ts:54`、`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`、`apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`。

Boundary 补充：本文没有提出新 schema。所有 schema 名称都来自当前代码：`GraphManifest`、`LogicNodeAST`、`SubgraphNodeAST`、`SkillNodeAST`、`BlackboardState`、`CopilotWsRequestPayload`、`ContextUpdateRequest`，分别见 `packages/graph-agent/src/graph_agent/core/manifest.py:45` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:90`、`packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`、`apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:80`。

最后的 architecture 结论：当前系统的 agent cognition 是由 V2.1 DAG 展示、旧 Harness runtime surface、Studio callbacks/artifacts、Copilot view context 四者共同形成的现状。它已经有清晰的 DAG 方向，但还不是单一、闭合、可观测、可 mention 的生产 agent 架构。

Lineage 补充：旧 Harness 文档化的能力还包括 validation retries 和 dual-control execution，见 `packages/graph-agent/src/graph_agent/core/harness.py:331` 到 `packages/graph-agent/src/graph_agent/core/harness.py:354`。这些能力在 UI 上没有独立 contract。

Lineage 补充：V2.1 graph 的 terminal edge 由 `assemble_graph()` 根据 phase 依赖计算，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:80` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:96`。这是真实 DAG 结构来源。

Lineage 补充：Studio skill detail、compile、run 仍通过 backend routers 提供，见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:118`、`apps/studio/backend/app/routers/runs.py:27` 到 `apps/studio/backend/app/routers/runs.py:55`。前端没有绕过 backend 直连 engine。
