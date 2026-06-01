# agent-cognitive-architecture (architecture) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20; PR G / round-18 engine cleanup notes synced 2026-05-26
> **Scope**: baseline: 旧 GraphAgentHarness 单文件线性控制流; MVP0: V0.3.0 LangGraph DAG + LOGIC/SUBGRAPH/Agent 三态心智模型。Studio/root `skills/` corpus 的 V2.1 残留属于 PR G §10 Deferred。
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

这份架构 baseline 描述的是当前“认知模型”如何反映到 Studio UI，而不是 UI 本身。PR G 之后 engine 当前主线是 V0.3.0 `GRAPH.md` + LangGraph DAG: phase 类型由 `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 文件名推导, LOGIC 通过 `<action>` + phase-local actions 执行, Agent 使用 cognitive template。旧 `GraphAgentHarness` 类仍存在, 但 V2.1 的 `context_mapping` / `ContextResolver` / `python_callable` / codemod / dead validators 已从 engine 删除。Studio 和根 `skills/` corpus 仍有 V2.1 残留, 这是 PR G §10 Deferred, 不能再描述成 engine 当前机制。

Studio 画布当前展示的是“节点 + 边”的 DAG 心智模型。GraphCanvas 用 React Flow 渲染 nodes/edges。节点来自 backend compile/manifest phase 信息；Studio 对根 `skills/` V2.1 corpus 的展示兼容仍属 §10 Deferred。V0.3.0 engine 侧边来自 `GRAPH.md` body `<phase depends_on>...</phase>`。

术语说明：DAG 是 Directed Acyclic Graph，有向无环图。UI 上看就是每个 phase 是一个节点，`depends_on` 是一条从上游到下游的线。旧 Harness 的 mental model 更像“一个带重试和回调的执行器”，V0.3.0 mental model 更像“声明式图结构交给 LangGraph 调度”。Studio UI 当前仍会展示部分 V2.1 corpus 形态, 但 engine 当前契约以 V0.3.0 skill-spec 为准。

phase 状态在 UI 上表现为节点状态、Trace 列表、Compile 面板和运行历史；这些状态不由 architecture 文档直接生成，而是来自 backend API 和 websocket。运行事件 WebSocket 是 `/ws/runs/{run_id}`，后端路由见 `apps/studio/backend/app/routers/websockets.py:27` 到 `apps/studio/backend/app/routers/websockets.py:39`。这说明认知架构对 UI 的影响是“数据结构约束”，不是组件约束。

当前 UI 没有把旧 Harness 的 retry router、heartbeat、checkpoint、IO mapping 分别呈现成独立一等对象。旧 Harness 这些概念集中在 `GraphAgentHarness.__init__()` 和 run setup 中，见 `packages/graph-agent/src/graph_agent/core/harness.py:356` 到 `packages/graph-agent/src/graph_agent/core/harness.py:390`、`packages/graph-agent/src/graph_agent/core/harness.py:568` 到 `packages/graph-agent/src/graph_agent/core/harness.py:629`。因此 UI 上看到的“节点失败/事件流”只是 orchestration 的投影，不是完整 Harness state。

当前 UI 也没有把 V0.3.0 的三态节点精确外显为三种视觉节点。前端 manifest phase 映射仍有兼容层偏差；engine 真实分支是 LOGIC / SUBGRAPH / Agent, 由 `LogicNodeAST` / `SubgraphNodeAST` / `AgentNodeAST` 表达。所以当前 UI 能表达拓扑，但不能完整表达三类执行语义差异。

Canvas 交互的边界也很清楚。ReactFlow 提供点击、双击、MiniMap、Controls、Background 等画布体验，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`。这些交互帮助用户浏览 graph，但没有改变 engine 的 graph assembly 或 blackboard reducer。

从用户视角看，compile 面板和 run 面板是同一认知链路的两个窗口：compile 解释 skill 能否形成 graph，run 解释 graph 是否能执行。前端 compile 调用在 `apps/studio/frontend/src/api/client.ts:81` 到 `apps/studio/frontend/src/api/client.ts:90`，run 调用在 `apps/studio/frontend/src/api/client.ts:140` 到 `apps/studio/frontend/src/api/client.ts:144`。两者都通过 Studio backend 间接触达 graph-agent。

当前 UI 不直接暴露 `BlackboardState`。用户看到的是 RunDetail、events、artifacts，而不是 `data/flow/messages/run_id` 的原始 TypedDict。`BlackboardState` 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`；Studio run detail 读取逻辑在 `apps/studio/backend/app/services/run_manager.py:408` 到 `apps/studio/backend/app/services/run_manager.py:422`。

这个 baseline 因此把 UI/UX 结论限定为现状：Studio 已经采用 DAG 浏览心智模型，但 engine / Studio / corpus 的迁移边界并未完全闭合；UI 没有证明架构已经完全切换，只证明 graph 拓扑已经成为主要展示对象。

## 前端逻辑

前端消费的是 Studio backend 的 skill detail、compile result、run events 和 Copilot context，不直接运行 graph-agent。API client 默认指向 `VITE_STUDIO_API_BASE_URL` 或 `http://localhost:8787/api`，见 `apps/studio/frontend/src/api/client.ts:20` 到 `apps/studio/frontend/src/api/client.ts:27`；compile 调用 `POST /skills/{skillId}/compile`，见 `apps/studio/frontend/src/api/client.ts:81` 到 `apps/studio/frontend/src/api/client.ts:90`；run 调用 `POST /skills/{skillId}/runs`，见 `apps/studio/frontend/src/api/client.ts:140` 到 `apps/studio/frontend/src/api/client.ts:144`。

GraphCanvas 的前端心智模型有一个当前偏差：Studio 仍可能把 legacy corpus phase 通过兼容层映射为前端 phase def。这只是前端展示/兼容层，不等于 engine 里只有 LOGIC。engine V0.3.0 真实三态是 `LogicNodeAST`、`SubgraphNodeAST`、`AgentNodeAST`; `SkillNodeAST` 已由 `AgentNodeAST` 替代。

Copilot context 也属于前端消费认知模型的一部分。Workspace 会把当前选中节点等 view context 送给 Copilot context hook，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:65` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:75`；hook POST 的 payload 是 `view/context/timestamp`，见 `apps/studio/frontend/src/hooks/useCopilotContext.ts:39` 到 `apps/studio/frontend/src/hooks/useCopilotContext.ts:63`。这不是旧架构文档里写的 `build_copilot_session(skill_id, error_log)` 伪代码，也不是 spec 里期待的 `mentions` 数组。

High-002 当前必须暴露：前端 Copilot WebSocket 发送消息时只构造 `{ user_message, model_override? }`，见 `apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`。没有 `mentions: [{type:'file', id:'...'}]`，也没有 trace event mention 或 node mention payload。后端 `CopilotWsRequestPayload` 同样只有 `user_message` 和 `model_override`，见 `apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:27`。

前端还有一个分层事实：Canvas、Copilot、Run 面板并不共享一个显式的“cognitive session model”。Canvas 通过 GraphCanvas props 消费 nodes/edges，Copilot 通过 context hook 发送 view context，Run 通过 API/WS 读取 events。API client 的 base URL、token header、WebSocket URL 处理分别在 `apps/studio/frontend/src/api/client.ts:20` 到 `apps/studio/frontend/src/api/client.ts:27`、`apps/studio/frontend/src/api/client.ts:46` 到 `apps/studio/frontend/src/api/client.ts:54`、`apps/studio/frontend/src/api/client.ts:101` 到 `apps/studio/frontend/src/api/client.ts:108`。

这意味着前端认知层当前是“多个 feature 通过 backend contract 间接对齐”，不是一个统一 store 驱动所有 feature。selected node context 通过 Workspace 进入 Copilot，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:65` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:75`；但 Copilot WebSocket payload 没有携带 node id 或 file mention，见 `apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`。

前端 DAG 的边来源是 structural dependency，不是运行时数据依赖。`buildEdges()` 读取 `dependsOn/root/output` 构边，见 `apps/studio/frontend/src/components/nodes/buildEdges.ts:23` 到 `apps/studio/frontend/src/components/nodes/buildEdges.ts:49`。engine 的 `ContextBridge` 只在 manifest model 中定义，见 `packages/graph-agent/src/graph_agent/core/manifest.py:26` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:32`；当前 Canvas 不把它作为完整 IO contract 展示。

对前端来说，V0.3.0 的三态差异目前主要通过 compile/runtime 后端信息体现，而不是前端类型系统体现。`LogicNodeAST`、`SubgraphNodeAST`、`AgentNodeAST` 的差异定义在 engine manifest model 中。这也是 architecture baseline 需要引用后端和 engine 的原因。

Copilot 的 context update 是 REST，chat 是 WebSocket。context update model 是 `ContextUpdateRequest`，见 `apps/studio/backend/app/models/copilot.py:73` 到 `apps/studio/backend/app/models/copilot.py:80`；chat model 是 `CopilotWsRequestPayload`，见 `apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:27`。两者分开使得“当前视图”可以进入 prompt，但“用户这句话明确提到哪些文件/节点/trace”仍没有结构化状态。

所以 High-002 的前端结论不是“Copilot 没上下文”，而是“Copilot 有 view context，但没有 mentions payload contract”。旧审计指出的 file mention 形态没有在 `useCopilot.ts` 或 `CopilotWsRequestPayload` 中落地，见 `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:29` 到 `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:36`。

## 后端功能

当前后端职责分成两层。Studio backend 是 FastAPI 外壳，注册 skills、runs、copilot、llm、websockets 等路由，见 `apps/studio/backend/app/main.py:112` 到 `apps/studio/backend/app/main.py:140`。graph-agent engine 是 Python package，提供 compile/run/graph assembly 和 legacy Harness。

旧 `GraphAgentHarness` 是完整的多 phase orchestration engine。PR G 后它不再接收 `context_mapping`, 也不再通过 `ContextResolver` 构造 initial context; `ContextResolver` 文件已删除。旧 Harness 仍保留 callbacks、IO config、skill_dir、checkpointer、RunContext、Heartbeat、PhaseExecutor 等 orchestration 概念。

V0.3.0 graph 路径更短：`run_skill()` 先调用 `_run_skill_dict()`, 当入口是含 `GRAPH.md` 的目录时进入 V0.3 graph helper, 编译 skill, 装配 graph, 再 `graph.invoke()`。PR G 后 `_run_v21_skill_dict()` 命名已收敛为 V0.3 helper; 根 `skills/` corpus 的 V2.1 格式仍属 §10 Deferred, 不代表 engine 主线。

V0.3.0 DAG 装配由 `assemble_graph()` 负责。它创建 `StateGraph(BlackboardState)`, 按 manifest phases 添加 node, 按 `depends_on` 添加 edge, 再连接 terminal phase 到 END。三态分发是 LOGIC、SUBGRAPH、Agent 分别走不同 builder。

这仍是 transition state, 不是完全统一的新架构。V0.3.0 graph runtime 的 trace 主线已在 T3 切到 `event_subscriber` + 内部 event sink；engine execution-runtime 文档记录了 ModelResolver、trace payload、StateMapper 等仍需对齐的目标态。

Studio backend 对 engine 的使用也分开。compile 走 `compile_skill(skill_dir, cache=False)` 并转成 Studio compile contract; run 走 subprocess entrypoint, 构造 `_queue_event_subscriber` 后调用 `run_skill(event_subscriber=...)`。默认 trace 落盘由 engine sink 写 `trace.jsonl`。

Copilot 后端不是 graph runtime。它使用 Claude Agent SDK session，解析 `copilot_chat` role 或 model override，再将 view context 注入 system prompt，见 `apps/studio/backend/app/services/copilot.py:183` 到 `apps/studio/backend/app/services/copilot.py:223`。view context 缓存在 `_view_contexts`，更新逻辑见 `apps/studio/backend/app/services/copilot.py:117` 到 `apps/studio/backend/app/services/copilot.py:140`；system prompt 拼接见 `apps/studio/backend/app/services/copilot.py:165` 到 `apps/studio/backend/app/services/copilot.py:180`。

旧 Harness 的后端功能还包括 checkpointer 解析。`_resolve_checkpointer()` 支持直接传入、禁用、env override 和 SQLite URI。这属于旧 orchestration 侧的持久化能力；V0.3.0 graph runtime 的等价 checkpoint 注入仍需按 execution-runtime/state alignment 收敛。

旧 Harness 的 IO 功能仍包括 `IOManager` 输入加载和 declared outputs 保存, 但 PR G 后已删除 `ContextResolver` / `context_mapping` 表达式层。V0.3.0 的 input funnel 和 phase IO contract 以 inline IO schema / StateMapper 为目标, 见 state-and-io-contract alignment。

V0.3.0 LOGIC node 当前是确定性 action 包装。LOGIC 不再使用 `python_callable`; 它读取 `LOGIC.md` body `<action>` 顺序并执行 phase-local `actions/<name>.py`。这说明 LOGIC 的认知角色是“纯函数式状态变换近似”，不是 LLM agent。

V0.3.0 SUBGRAPH node 是固定子图委派, 通过 `target_skill` + `SkillResolverProtocol` 寻址完整 graph skill。其长期隔离性和 IO 边界由 inline IO schema / StateMapper / parent-child IO 1:1 校验收敛。

V0.3.0 Agent node 是最接近 LLM phase 的部分。它消费 `AgentNodeAST`, cognitive template、tools/subagents/finish_task 和 output schema; `exit_contract` 由模板尾置生成, 不再由 Agent body 自定义。

`CompiledStateGraph` 只是 graph、manifest、root_dir 的轻 wrapper。它不包含 Studio callback schema、run artifact schema 或 Copilot context。架构上这说明 V0.3.0 graph assembly 与 Studio runtime presentation 仍是两层。

`Harness = GraphAgentHarness` alias 仍存在，见 `packages/graph-agent/src/graph_agent/core/harness.py:1150`。这不是功能 bug，但它说明 public surface 仍承认旧 Harness 作为 engine 概念。architecture baseline 不能把旧 Harness 当成已删除实现。

Studio run worker 用 subprocess 隔离运行。worker 创建 event subscriber 后调用 `run_skill()`。这使 Studio 能把 engine 执行转成队列事件，同时 engine 自己写 run-scoped `trace.jsonl`。

`_queue_event_subscriber` 把 graph-agent typed event 转成 Studio event queue，见 `apps/studio/backend/app/services/run_manager.py:74` 到 `apps/studio/backend/app/services/run_manager.py:78`。这个 adapter 是 Studio trace/runner 认知层的一部分；它依赖 engine 发出 typed event，而不是从 LangGraph state 自动推断所有事件。

综上，后端现状不是“单一 graph runtime”。它是旧 Harness runtime、V0.3.0 graph assembler、Studio run manager、Copilot service 四条后端路径并存，并通过 API、callbacks、文件 artifacts 和 view context 松散连接。V2.1 只应作为 Studio/root corpus deferred 残留或历史迁移背景出现。

## API

核心 engine API 有两类。旧 public API 是 `run_skill(skill_path, ..., **inputs) -> RunResult`。V0.3.0 compile API 是 `compile_skill()`, graph assembly API 是 `assemble_graph(compiled, chat_model=...) -> CompiledStateGraph`。Studio 仍通过 backend 间接调用这些 API。

Studio API 以 HTTP 和 WebSocket 暴露。`GET /api/skills/{skill_id}` 返回 SkillDetail，见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:105`；`POST /api/skills/{skill_id}/compile` 返回 compile result 或 422 compile failure，见 `apps/studio/backend/app/routers/skills.py:108` 到 `apps/studio/backend/app/routers/skills.py:118`；`POST /api/skills/{skill_id}/runs` 启动 run，见 `apps/studio/backend/app/routers/runs.py:27` 到 `apps/studio/backend/app/routers/runs.py:29`；`GET /api/skills/{skill_id}/runs/{run_id}` 返回 run detail，见 `apps/studio/backend/app/routers/runs.py:53` 到 `apps/studio/backend/app/routers/runs.py:55`。

Copilot API 当前有三条：dispatch REST endpoint 存在但 not implemented，见 `apps/studio/backend/app/routers/copilot.py:23` 到 `apps/studio/backend/app/routers/copilot.py:31`；WebSocket `/api/skills/{skill_id}/copilot/ws` 接收 `CopilotWsRequestPayload`，见 `apps/studio/backend/app/routers/copilot.py:34` 到 `apps/studio/backend/app/routers/copilot.py:54`；context POST `/api/skills/{skill_id}/copilot/context` 接收 view context，见 `apps/studio/backend/app/models/copilot.py:73` 到 `apps/studio/backend/app/models/copilot.py:80`。

API 层的一个重要边界是：Studio HTTP API 返回的是 Studio DTO，不是 engine native object。`GET /api/skills/{skill_id}` 由 skills router 调 service 返回 SkillDetail，见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:105`；compile endpoint 捕获 CompileError 后转成 HTTP 422，见 `apps/studio/backend/app/routers/skills.py:108` 到 `apps/studio/backend/app/routers/skills.py:118`。这说明 UI 看到的是后端整理后的 contract。

run API 也不直接返回 `BlackboardState`。`POST /api/skills/{skill_id}/runs` 返回 run 创建结果，见 `apps/studio/backend/app/routers/runs.py:27` 到 `apps/studio/backend/app/routers/runs.py:29`；后续 detail endpoint 再读取 run directory，见 `apps/studio/backend/app/routers/runs.py:53` 到 `apps/studio/backend/app/routers/runs.py:55`、`apps/studio/backend/app/services/run_manager.py:408` 到 `apps/studio/backend/app/services/run_manager.py:422`。

WebSocket API 分两类：run events 和 Copilot chat。run events route 是 `/ws/runs/{run_id}`，见 `apps/studio/backend/app/routers/websockets.py:27` 到 `apps/studio/backend/app/routers/websockets.py:39`；Copilot chat route 在 copilot router，见 `apps/studio/backend/app/routers/copilot.py:34` 到 `apps/studio/backend/app/routers/copilot.py:54`。两者没有共享一个 event envelope model。

engine API 的 `run_skill()` 是兼容入口。它能处理 legacy harness path 和 V0.3.0 graph root path。这使 Studio 可以调用同一个 Python API, 但也让 architecture baseline 必须同时记录 engine 主线与 deferred corpus/Studio 残留。

V0.3.0 graph API `assemble_graph()` 接收 `CompiledSkill` 和可选 `chat_model`。ModelResolver 注入、phase-level LLM role 路由和 trace callbacks 是 execution-runtime alignment 的后续收敛项。

API 层没有 file mention contract。前端 payload、后端 request model、copilot route 都没有 `mentions` 字段，见 `apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`、`apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:27`、`apps/studio/backend/app/routers/copilot.py:34` 到 `apps/studio/backend/app/routers/copilot.py:54`。这就是 High-002 在 API 维度的 exposed bug。

## Data Model / State

V0.3.0 graph 的数据模型从 `GRAPH.md` frontmatter + body DAG 开始。根 IO inline 在 `GRAPH.md`, phase 类型由物理文件名推导, 不再使用 V2.1 `io_inputs_ref` / `io_outputs_ref` 或 `context_mapping`。

三态 node AST 是 `LogicNodeAST`、`SubgraphNodeAST`、`AgentNodeAST`。LOGIC 是确定性 Python action, 使用 `actions` 列表和 `<action>` body, 不再有 `python_callable`; SUBGRAPH 是固定子图委派, 通过 `target_skill` + resolver; Agent 是 LLM ReAct phase, 由 cognitive template 生成 system prompt 和尾置 exit contract。

运行 state 是 `BlackboardState`: `data`、`flow`、`messages`、`run_id`。`data` 仍是共享黑板; V0.3.0 的目标是用 inline IO schema / StateMapper 约束每个 phase 的可见输入和可写输出。相关缺口详见 [state-and-io-contract baseline](../../engine/state-and-io-contract/baseline.md)。

Studio run detail 把 engine 结果重新包装为 `RunDetail`：metadata、input_data、events、final_context、artifacts，读取逻辑见 `apps/studio/backend/app/services/run_manager.py:408` 到 `apps/studio/backend/app/services/run_manager.py:422`。前端看到的是这个外壳状态，不是直接看到 `BlackboardState`。

Copilot state 当前是两层：一个是 WebSocket 消息 payload，只含 user message 和 model override；另一个是 view context cache，只含 view/context/timestamp。没有 mentions 数组，没有“文件/节点/trace event 引用”的显式状态模型。这是 High-002 在当前 baseline 中的结论。

`GRAPH.md` body `<phase depends_on>` 是拓扑依赖, 不是完整数据 schema。`assemble_graph()` 用它连接 edge; 数据依赖应由 inline IO schema、静态 dataflow 校验和 runtime StateMapper 收敛。

`ContextBridge` 在 manifest model 中提供 parent/child data mapping 的结构位，见 `packages/graph-agent/src/graph_agent/core/manifest.py:26` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:32`。但当前 architecture baseline 不能把它描述成完整可视化/验证的 IO contract，因为 engine state baseline 已记录 phase-level IO contract 缺口，见 `docs/engine/state-and-io-contract/baseline.md:99` 到 `docs/engine/state-and-io-contract/baseline.md:127`。

`shallow_dict_merge` 的冲突语义很关键。它只做顶层浅合并，同名 key 冲突直接抛异常，见 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:32`。这意味着认知模型里的“多 phase 协作”现在依赖 phase 避免写同一顶层 key，而不是依赖 typed output slots 自动隔离。

`messages` 在 `BlackboardState` 中存在, 但 LOGIC/SUBGRAPH 并不天然都用它。Agent node 使用它承载 LLM 对话; `exit_contract` 不再作为每轮临时消息反复注入, 而由 cognitive template 尾置生成。所以当前 message state 主要服务 LLM Agent node, 不是全局 trace。

旧 Harness 有自己的 runtime storage 和 working memory 概念。V0.3.0 graph runtime 的 state 则集中在 `BlackboardState` 和 LangGraph graph 中, 并通过 compiler 产出的 AST / inline IO / cognitive template 与旧 Harness 概念分层。

Studio 的 state model 是二次包装。Run manager 从 filesystem 读取 trace、final state、artifacts 并拼成 detail，见 `apps/studio/backend/app/services/run_manager.py:408` 到 `apps/studio/backend/app/services/run_manager.py:422`。这让 Studio 能保留运行历史，但也说明 Studio state 不等于 engine state。

Copilot 的 view context 使用普通 dict 缓存，更新入口是 `set_view_context()`，见 `apps/studio/backend/app/services/copilot.py:117` 到 `apps/studio/backend/app/services/copilot.py:140`。system prompt 注入发生在 query 前，见 `apps/studio/backend/app/services/copilot.py:165` 到 `apps/studio/backend/app/services/copilot.py:180`。这是一种 prompt-time context，不是 graph state。

数据模型层最终暴露三个核心事实：engine V0.3.0 仍以共享黑板为底层 runtime state, Studio 运行记录是 artifacts/detail, Copilot 上下文是 view context cache。三者没有统一 schema，这正是 architecture 层需要跨 feature 标注的当前状态。

## Cross-feature interaction

与 engine baselines：本 architecture 是总览，具体 bug 和边界已经落在 engine 四份 baseline。V0.3.0 ModelResolver、event_subscriber/trace、subagent/subgraph runtime 缺口见 [execution-runtime baseline](../../engine/execution-runtime/baseline.md)。共享黑板、缺 input funnel、缺 phase-level IO contract 见 [state-and-io-contract baseline](../../engine/state-and-io-contract/baseline.md)。

与 Studio Canvas：Canvas 使用 DAG 视图显示 phase/edge，但当前 edge 主要来自 `depends_on`，不是完整数据流 contract。Canvas baseline 见 [canvas-topology baseline](../../studio/feature-folders/canvas-topology/baseline.md)。

与 Trace：Studio 后端通过 `event_subscriber` 获取实时事件；engine 默认 `_TraceJsonlSink` 写 `trace.jsonl`。Trace 当前状态见 [tracing-and-observability baseline](../../engine/tracing-and-observability/baseline.md) 和 [Studio trace-visualization baseline](../../studio/feature-folders/trace-visualization/baseline.md)。

与 Copilot：旧 architecture doc 的伪代码说后端 `build_copilot_session(skill_id, error_log)` 直接拼上下文；当前真实实现是前端异步 POST view context，WebSocket 只发 user_message/model_override，后端 system prompt 从 cached view context 注入。这和 High-002 指出的 mentions payload 缺失一致，具体 feature 现状见 [copilot-assistance baseline](../../studio/feature-folders/copilot-assistance/baseline.md)。

与 prod/dev separation：本文件描述认知模型并存；进程边界、Tauri sidecar、dev tunnel、Python runtime bundle 在 [prod-dev-separation baseline](../prod-dev-separation/baseline.md)。两者交叉点是 Studio backend 调用 graph-agent Python API，而不是通过独立 engine service。

与 compile contract：Studio compile endpoint 调用 graph-agent compile 并转成 Studio contract，见 `apps/studio/backend/app/services/skills.py:294` 到 `apps/studio/backend/app/services/skills.py:311`。这让 Canvas 能显示 DAG，但 compile contract 不能证明 run-time LLM path、callbacks、IO contract 都完整。

与 execution runtime：P0-1、P1-2、P1-3、P1-4、A4、A5 的具体 runtime 缺口已经写在 [execution-runtime baseline](../../engine/execution-runtime/baseline.md)。本文件只在 architecture 层说明这些缺口如何影响“agent cognitive architecture”这个总心智模型。

与 state/io contract：A1/A2/A3/A6 说明共享 blackboard、input funnel、phase IO、subgraph IO 仍没有形成完整 production contract，见 [state-and-io-contract baseline](../../engine/state-and-io-contract/baseline.md)。因此 architecture baseline 不能把 DAG 画布解释成强类型数据流编辑器。

与 tracing：V0.3.0 callbacks / trace 事件未完全接入会导致 Studio trace 不能完整覆盖 DAG runtime, 见 [tracing-and-observability baseline](../../engine/tracing-and-observability/baseline.md)。这影响用户对 agent cognition 的观察能力：看到事件不等于看到完整 LangGraph state transition。

与 Copilot High-002 audit：audit 要求暴露 file mentions payload 缺失，见 `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:29` 到 `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:36`。本文件在 UI、前端、API、Data Model 四个维度都明确写出：当前只有 view context 和 user message/model override，没有 mentions。

与 legacy Harness：旧 Harness 不是历史文档残影，而是当前 public code surface。`Harness = GraphAgentHarness` 在 `packages/graph-agent/src/graph_agent/core/harness.py:1150`，runner legacy path 仍加载 cached Harness，见 `packages/graph-agent/src/graph_agent/core/runner.py:288` 到 `packages/graph-agent/src/graph_agent/core/runner.py:307`。所以所有 architecture 结论都必须保留“并存”而不是“已迁移完成”的表述。

最终边界：本 baseline 不写改造方案，不承诺 MVP0 已完成，不替 engine baseline 详细列 bug，不替 Studio feature baseline 描述 UI 细节。它只记录当前代码里“用户看到的 DAG 认知模型、后端仍存在的 Harness/V0.3 graph 双轨、Studio/root corpus V2.1 deferred 残留、Copilot 上下文缺 mentions、state/trace/API 未完全统一”这些跨层事实。

Audit 映射补充：P0-1 对应 SKILL node 无真实 LLM model 的 runtime 断点。runner 在非 mock 情况下传 `chat_model = None`，见 `packages/graph-agent/src/graph_agent/core/runner.py:467` 到 `packages/graph-agent/src/graph_agent/core/runner.py:474`；SKILL node 无 chat_model 会 RuntimeError，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:229` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

Audit 映射补充：P1-4 对应 callbacks/tracing 未完整接入 V0.3.0 graph runtime。legacy runner 会创建 Logging/Tracing callbacks；Studio run manager 仍期待 callbacks。后续应以 tracing alignment 的 V0.3 event contract 为准。

Audit 映射补充：A1/A2/A3/A6 属于 state/io 层，不可在 architecture 文档里伪装成已解决。当前 `BlackboardState` 仍以 `data/flow/messages/run_id` 为核心; 相关边界见 state-and-io-contract 文档。

Audit 映射补充：A4/A5 影响 SUBGRAPH/SKILL 的 agent 心智模型。SUBGRAPH 当前通过 child graph invoke 和 diff 回写工作，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:141` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:174`；SKILL 的 tools/subagents/finish_task 路径见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:177` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:298`。具体缺口仍以 [execution-runtime baseline](../../engine/execution-runtime/baseline.md) 为准。

Studio 映射补充：Canvas 只消费 graph topology，不消费 Harness retry/checkpoint semantics。Canvas nodes/edges 渲染见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`；Harness retry/router/checkpointer 初始化见 `packages/graph-agent/src/graph_agent/core/harness.py:356` 到 `packages/graph-agent/src/graph_agent/core/harness.py:430`。

Studio 映射补充：Compile success 只是 graph 可构建，不等于 run 可完整执行。compile endpoint 和 V0.3.0 run invoke 之间仍需要 ModelResolver、StateMapper、trace callback 等 runtime contract 闭合。P0-1 发生在 run-time Agent node, 不是 compile-time manifest parsing。

Studio 映射补充：Run event visibility 依赖 event pipeline。WebSocket route 见 `apps/studio/backend/app/routers/websockets.py:27` 到 `apps/studio/backend/app/routers/websockets.py:39`；`_queue_event_subscriber` 见 `apps/studio/backend/app/services/run_manager.py:74` 到 `apps/studio/backend/app/services/run_manager.py:78`。如果 engine 分支不发 typed event，UI event stream 就不能完整反映认知执行过程。

Copilot 映射补充：view context 是当前代码的真实上下文入口。frontend POST context 见 `apps/studio/frontend/src/hooks/useCopilotContext.ts:39` 到 `apps/studio/frontend/src/hooks/useCopilotContext.ts:63`；backend set_view_context 见 `apps/studio/backend/app/services/copilot.py:117` 到 `apps/studio/backend/app/services/copilot.py:140`。这条路径不能替代 mentions payload。

Copilot 映射补充：backend prompt 注入是 system prompt 拼接，不是结构化 reference resolver。`build_system_prompt()` 见 `apps/studio/backend/app/services/copilot.py:165` 到 `apps/studio/backend/app/services/copilot.py:180`；stream query 调用 Claude Agent SDK client，见 `apps/studio/backend/app/services/copilot.py:183` 到 `apps/studio/backend/app/services/copilot.py:223`。

API 映射补充：Copilot dispatch REST endpoint 当前 not implemented，见 `apps/studio/backend/app/routers/copilot.py:23` 到 `apps/studio/backend/app/routers/copilot.py:31`。因此 architecture baseline 不应把 Copilot 写成“REST dispatch + session builder”的旧伪代码形态。

Data 映射补充：V0.3.0 `GRAPH.md` 的 metadata、inline IO 和 body DAG 形成 graph 编译输入。但运行时状态仍由 LangGraph state 管理，不是 manifest 自身保存。

Data 映射补充：`CompiledStateGraph` 保存 graph、manifest、root_dir，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:41` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:47`。它没有保存 Studio run_id、artifact paths、Copilot session 或 UI selection。

Boundary 补充：本文件引用 engine baseline 和 Studio feature baseline 只是 cross-link，不修改这些文件。architecture 这里记录的是跨层事实，而不是替代每个 feature 的详细 baseline。

Boundary 补充：本文没有把旧 Harness 删除、迁移或降级为 dead code。只要 `GraphAgentHarness` 和 `Harness = GraphAgentHarness` 仍在，见 `packages/graph-agent/src/graph_agent/core/harness.py:331` 到 `packages/graph-agent/src/graph_agent/core/harness.py:354`、`packages/graph-agent/src/graph_agent/core/harness.py:1150`，baseline 就必须写成双轨并存。

Boundary 补充：本文没有把 Studio/root corpus 的 V2.1 残留说成已完成迁移；它属于 PR G §10 Deferred。engine 主线文档描述 V0.3.0 graph runtime, 结论只是当前若干 production contract 仍需闭合。

Boundary 补充：本文没有把 Studio UI 说成 engine。前端 API client、Canvas、Copilot hook 都只通过 backend contract 工作，见 `apps/studio/frontend/src/api/client.ts:20` 到 `apps/studio/frontend/src/api/client.ts:54`、`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`、`apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`。

Boundary 补充：本文没有提出新 schema。engine 侧名称以当前 V0.3.0 AST 为准: `LogicNodeAST`、`SubgraphNodeAST`、`AgentNodeAST`、`BlackboardState`; Studio/Copilot 侧仍有 `CopilotWsRequestPayload`、`ContextUpdateRequest` 等外壳模型。

最后的 architecture 结论：当前系统的 agent cognition 是由 V0.3.0 DAG engine 主线、旧 Harness runtime surface、Studio callbacks/artifacts、Copilot view context、以及 §10 Deferred 的 V2.1 corpus 残留共同形成的现状。它已经有清晰的 DAG 方向，但还不是单一、闭合、可观测、可 mention 的生产 agent 架构。

Lineage 补充：旧 Harness 文档化的能力还包括 validation retries 和 dual-control execution，见 `packages/graph-agent/src/graph_agent/core/harness.py:331` 到 `packages/graph-agent/src/graph_agent/core/harness.py:354`。这些能力在 UI 上没有独立 contract。

Lineage 补充：V0.3.0 graph 的 terminal edge 由 `assemble_graph()` 根据 phase 依赖计算。这是真实 DAG 结构来源。

Lineage 补充：Studio skill detail、compile、run 仍通过 backend routers 提供，见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:118`、`apps/studio/backend/app/routers/runs.py:27` 到 `apps/studio/backend/app/routers/runs.py:55`。前端没有绕过 backend 直连 engine。
