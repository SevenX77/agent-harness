---
ws_id: WS-E1-create-agent-core
modules: [01-agent-loop, 03-assemble, 02-middleware, 04-run-outer/01-graph-exec, 02-iterate]
depends_on: []          # gateway WS-1(GatewayChatModel 稳)= soft;WS-E6(run_skill 扫描码)= LOGIC 子步骤 soft 依赖(§8 ordering 二选一)
blocks: [WS-E2, WS-E5, WS-E8]
owns_files:
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py   # 热点:create_agent构造(state_schema/system_prompt/thread_id-ns/max_iter)/6槽接线/subagent重接线(_invoke_subagent_tool_t21,:1057+)/LOGIC节点/iterate/子图io放宽接线
  - packages/graph-agent/src/graph_agent/middleware/factory.py     # 6 槽 build_middleware_chain 接进 AGENT
  - packages/graph-agent/src/graph_agent/middleware/__init__.py    # 顺序契约(若需调整)
  - packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py  # finish_task schema 对齐(_handle_finish_task 读 args 与工具 schema 一致)
  - packages/graph-agent/src/graph_agent/cognitive/finish_task.py  # finish_task 工具 schema 对齐(markdown 单参 vs business_data_md/reasoning/diagnostics_md)
  - packages/graph-agent/src/graph_agent/core/manifest.py          # BatchSpec → 统一 IterateSpec(iterate)
  - packages/graph-agent/src/graph_agent/core/loader.py            # 仅 :528 子图 io inputs 1:1 删(11-io 仅此项);其余 loader 勿动
spec_ssot:
  - ../02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md §2/§4/§5（create_agent 迁移 + AL1/AL2）
  - ../02-mechanism/03-assemble/mvp1-alignment.md §2/§3（_build_skill_node 收口 create_agent 构造）
  - ../02-mechanism/05-run-inner/02-middleware/mvp1-alignment.md §2（6 槽链 + 顺序）
  - ../02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md §2/§5（LE1-3 LOGIC 干净契约 + iterate + 11-io E1-E3）
  - ../02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md §2（执行模型）+ ../01-contract/02-skill-syntax/mvp1-alignment.md §2.9/§2.10（iterate/io 声明)
status: drafted
---

# WS-E1 create_agent 核心(graph_assembler.py 串行链)— 任务书

## 1. 目标(intent + why)
把 `graph_assembler.py` 的**手写 ReAct loop 换成原生 `create_agent`**(含 state_schema/finish_task/thread_id-ns/max_iterations 等运行边界),并在同一热点文件内串行收口 **6 槽中间件接线 / subagent 重接 / LOGIC runtime 契约 / iterate 执行 / 子图 io 放宽**。**为什么**:① keystone——中间件后 3 槽(E2)、内层 checkpoint(E5)、退出闸(E8)都挂 create_agent;② 手写 loop = 重复造轮子,还得自己处理 tool-call 消息配对、return-direct、middleware 顺序、checkpoint 交互(现 `:483-576` 逐手调 `model.invoke`/`tool.invoke`、无 tool_calls 时裸退)。目标机制以 `spec_ssot` 为准,不在此复制。

## 2. SSOT 指针(grounding,IR2/IR5)
- **目标**:见 frontmatter `spec_ssot`。
- **现状(起点)**:`../02-mechanism/05-run-inner/01-agent-loop/baseline.md`、`../03-assemble/baseline.md`、`../02-middleware/baseline.md`(6 槽 3 真 3 空)、`../04-run-outer/01-graph-exec/baseline.md`、`../02-iterate/baseline.md`(仅节点级 batch)。
- **实现前必读源码(先回读关键符号 + 现状再动手)**:
  - `core/graph_assembler.py:437-576`(`_build_skill_node` + 手写 loop,待替换;`:510` max_iterations、`:514` LLMCallEvent、`:535-544` subagent 拦截、`:563` finish_task 桥接)、`:240-300`(节点级 batch)、`:325`(`_build_logic_node`)
  - LangChain create_agent 运行边界源码:`langchain/agents/factory.py`(state_schema union `_resolve_schema`、`:1597` recursion_limit、`:1601` checkpointer compile)
  - finish_task 两套形态:`cognitive/finish_task.py:40`(工具 `_finish_task(markdown)`)vs `middleware/cognitive_flow.py:479`(读 business_data_md/reasoning/diagnostics_md)
  - `middleware/factory.py:29`(`build_middleware_chain` 6 槽)/`:68`(单槽 live)、`middleware/__init__.py:58`(顺序契约)
  - `core/manifest.py:121`(`BatchSpec`)、`core/loader.py:528`(子图 io 1:1 强校)、`core/runner.py:689`(外层 thread_id config)
  - (11-io 文件导入 `:287`/read_file/state/storage/runner = WS-E1-io,不在本 WS)

## 3. 文件归属(并发锁,IR1)
- **本 WS owns(可改/建)**:见 frontmatter `owns_files`。
- **禁止触碰**:`middleware/tracing.py`/`tool_error.py`/`loop_detection.py`→**WS-E2**;`core/checkpointer.py`/`state.py`→**WS-E5**;`core/exceptions.py`/`error_registry.py`/`result.py`→**WS-E3**;`callbacks/events.py`/`emit.py`→**WS-E4**;`core/purity.py`→**WS-E6**;`middleware/nudge_injector.py`/exit middleware→**WS-E8**。
- **本 WS owns 补充**:`middleware/cognitive_flow.py` + `cognitive/finish_task.py`(finish_task schema 对齐,两者不属其它 WS)纳入本 WS owns。
- **共享协调**:`graph_assembler.py` 内 create_agent/subagent/LOGIC/iterate/子图io 多处改 → **内部串行(§7)**,不并发编辑。`loader.py` **仅** `:528` 子图 io 那段归本 WS,其余 loader 勿动。**E6 的 run_skill 扫描码与本 WS LOGIC 子步骤有 ordering 约束**(§8)。

## 4. 现状锚点(baseline)
手写 ReAct loop live(`:483-576`);AGENT 只接单槽 middleware(`factory.py:68`);LOGIC action 用可变 Context facade;仅节点级 batch、无 loop/图级;子图 io 1:1 强校(`loader.py:528`)。详见各 baseline。

## 5. 目标行为(可测的契约)
- **create_agent 构造(含运行边界,P0 全集)**(agent-loop §2):AGENT phase → `create_agent(model=GatewayChatModel, tools=业务+framework+finish_task+subagent, middleware=6槽, checkpointer, state_schema=WorkflowState, system_prompt=...)` → `invoke(config={"configurable":{"thread_id","checkpoint_ns"}})` → finish_task;**不再**手拼 ToolMessage / 无 tool_calls 裸退。下列运行边界**必须显式接好**(核实自 LangChain `create_agent` 源码,均会"假绿"):
  - **`state_schema=WorkflowState`(P0)**:create_agent 默认 `base_state = state_schema or AgentState`(`langchain/agents/factory.py` `_resolve_schema`),不显式传则基底是 `AgentState`(只有 messages),`WorkflowState.data`(业务黑板)/`flow`(框架态)会**被裁掉** → subagent / CognitiveFlow / ProtocolValidation 全拿不到真 state。必须传 `state_schema=WorkflowState`(或确保某中间件声明该 schema 被 union 进来)。
  - **`max_iterations` 保活(P1)**:手写 loop 尊重 `phase_ast.max_iterations`(`graph_assembler.py:510` 每阶段迭代上限);create_agent 默认 `recursion_limit=10000`(`factory.py:1597`)≈ 无界。必须把 phase 上限接成 create_agent 可执行的迭代约束。
  - **`model`** 吃 `GatewayChatModel`(AL2 核心:provider 差异归 gateway,引擎不分支)。
- **finish_task schema 对齐(P0,迁移最易假绿)**:现状两套形态——工具 builder `build_finish_task_tool`(`cognitive/finish_task.py:40`)签名 `_finish_task(markdown: str)` 单参;而 `CognitiveFlowMiddleware._handle_finish_task`(`middleware/cognitive_flow.py:479-482`)读 `args.get("reasoning"/"diagnostics_md"/"business_data_md")` 三参。现状手写 loop 用工具**结果**桥接(`graph_assembler.py:563` `handle_finish_task_tool_result`);迁 create_agent 后中间件直接读 tool-call `args`,**绑定的工具 schema 必须与中间件期望一致**,否则模型 tool-call 形态错、finish 被拒。本 WS 须把二者对齐(改 `finish_task.py` 工具 schema 或 `cognitive_flow.py` 读取,二者均纳入 owns)并测。
- **subagent 在 create_agent 下存活**(P0,迁移断裂点):现状手写 loop 按工具名拦截 subagent(`graph_assembler.py:535-544`:`if name in subagent_by_tool_name → _invoke_subagent_tool_t21(... runtime=subagent_runtime_by_tool_name[name])`),**绕过** loader 给 subagent 工具挂的 placeholder func(`loader.py:709` `_pending_call_subagent_tool` 直接 `raise NotImplementedError`)。删掉手写 loop、把 `all_tools` 裸交 create_agent 后,create_agent 原生 tool 节点会去调那个 placeholder → 炸 `NotImplementedError`,**核心路径断裂**。本 WS 须在交给 create_agent 前把 subagent 工具的 func **重接** 到引擎派发闭包(复用 `_invoke_subagent_tool_t21` + `_subagent_runtime_map`,均在 `graph_assembler.py` 内、已 owns,**不动** `loader.py:709`)。重接闭包要拿到真 `WorkflowState`(依赖上面 `state_schema=WorkflowState`;LangGraph `ToolNode` 的 `ToolCallRequest` 携带 `state`,wrapper 可短路工具执行)。验收:create_agent 工具循环里调 subagent → 走引擎真派发,**不命中** placeholder。
- **6 槽接线**(middleware §2):`build_middleware_chain` 6 槽按 `__init__.py:58` 顺序接进 AGENT。**与 create_agent 同一垂直切片**(create_agent 构造本身要消费这 6 槽,二者不可分步,见 §7 步骤 1)。
- **checkpointer 接线 = 可运行验收,不只编译期接受**(E1/E5 边界):create_agent compile 时收 `checkpointer`(`factory.py:1601`),但运行时**还须**在 `invoke` config 给 `thread_id` + 内层 `checkpoint_ns`,否则 checkpointer 报缺 key。现 `runner.py:689` 只给**外层图**传 `thread_id`,内层 create_agent 的 ns 未接。本 WS 验收 = **小 N 能真跑** + thread_id/checkpoint_ns 正确 + **不污染外层 state**(checkpoint alignment §line63 列为头号 D-test)。checkpoint 内层 **delta/compaction/state 模型优化 = WS-E5**,不在本 WS 验收(§9)。
- **LLM usage/事件归属不丢(P1)**:现手写 loop 手动发 `LLMCallEvent`(带 token usage,`graph_assembler.py:514-518`);迁 create_agent 后该发射点消失,usage 只剩 message metadata。本 WS 须明确接替者:要么 E1 接一个 bridge 把 usage 发进引擎事件流,要么**显式 defer 到 E4(tracing/events)并测"usage 至少进 message metadata、defer 项记 §11/deferred-items"**——二选一写清,不留隐性丢失。
- **LOGIC 运行时契约(scope 收敛,不声称"完整 LOGIC 干净")**(graph-exec LE1-3):`_build_logic_node` action = `def <name>(inputs)->dict` 纯返回、只读 inputs;砍 Context `set/update/delete`;**FS 写 + import 越界禁令现成可测**(`purity.py` 扫 os/shutil/tempfile/写模式 → `loader.py:367/770` 已发 `[F-v3-logic-action-purity-violation]` FATAL)。**`run_skill` 硬禁(graph-exec §2 第18行)= WS-E6 交付**(`purity.py` 现**不扫** `run_skill`)。**ordering 铁律**:E1 的 LOGIC 子步骤**只声明"纯返回 runtime + FS/Context purity"**,**不声明"完整 LOGIC 干净契约完成"**;完整 run_skill 禁令由 E6 落地(E6 → E1-LOGIC 退出 二选一:E6 先于本子步,或本子步显式降级 scope,见 §8)。
- **iterate**(02-iterate §2):节点级 loop(`accumulate{var,init,from,merge}`)/ 图级 batch(`Send`)/ 图级 loop=B(引擎包 loop-body,一 thread + `ns=iter{k}`);统一 `iterate` 配置(兼容现 `batch`)。
- **11-io 收敛 = 仅子图 io 放宽**(graph-exec E1):删 `loader.py:528` 对 **inputs** 的 1:1 强校(子图用自己 io.inputs 经 StateMapper 切片),**outputs 保留**相等校验。**owns 内可完成**(loader.py:528 已 owns)。
  - ⚠️ **文件导入→黑板 lazy(11-io E2)+ artifact business_data_md(11-io E3)拆出本 WS**:核实 graph-exec alignment §2 第29-30行,这两项要调 `tools/builtin/read_file.py` + `StateManager.update_business`(**state.py = E5 owns**)+ 发 `InputFileInjectedEvent`(**events = E4 owns**)+ `save_artifact`(storage.py)+ 改 `runner.py:598`(现只筛 `target=="file"`)。跨 E4/E5/read_file/storage/runner → **owns 必相交,违 IR1**,不能塞进 E1。**已拆出为 WS-E1-io(依赖 E4/E5),记于 `IMPL_PLAN.md` §二/§三**。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4;抽 alignment §6)
- ★ **create_agent 端到端**(D-test-3):`create_agent(model=GatewayChatModel)` 跑通,gateway usage / thinking blocks / tool-call metadata **不丢**;多轮 tool loop **不裸退**。
- ★ **`state_schema=WorkflowState` 保真**(P0):create_agent 跑完,`WorkflowState.data`(业务黑板)/`flow`(框架态)**不被裁掉**(对照不传 state_schema 时 data/flow 丢失的反例)。
- ★ **finish_task schema 一致**(P0,易假绿):绑定给 create_agent 的 finish_task 工具 schema 与 `CognitiveFlowMiddleware._handle_finish_task` 期望的 `business_data_md/reasoning/diagnostics_md` 对齐;模型按该 schema 发 tool-call → 中间件正确收 finish、结构化输出落 state。
- ★ **6 槽接线**:live `assemble_graph` 的 AGENT phase 传 **6 槽** middleware(非单槽)。
- ★ **subagent 在 create_agent 下不命中 placeholder**(P0 回归,迁移断裂点专测):create_agent 工具循环里调一个 subagent 工具 → 走引擎真派发(`_invoke_subagent_tool_t21`)且拿到真 `WorkflowState`,**绝不**触发 `loader.py:709` placeholder 的 `NotImplementedError`。
- ★ **checkpointer 可运行**(P0):create_agent + checkpointer,`invoke` 给 `thread_id`+`checkpoint_ns` → 小 N **真能跑**、checkpoint 写成、**不污染外层图 state**。
- **max_iterations 保活**(P1):phase 声明的 `max_iterations` 真生效(超限即停),**不被** create_agent 默认 `recursion_limit=10000` 吞掉。
- **LLM usage 进事件流 / 或显式 defer**(P1):usage 要么经 bridge 进引擎 `LLMCallEvent` 流,要么显式 defer E4 但测"usage 进 message metadata"+ defer 记录;不允许静默丢失。
- **LOGIC 纯返回 + FS purity**(scope 收敛):action 同输入同输出(无 LLM、确定性);Context mutation / **FS 写 / import 越界**命中编译期 `[F-v3-logic-action-purity-violation]` FATAL(**现成可测**)。**`run_skill` 禁令测试归 WS-E6**(E1 不以它为退出条件,见 §8 ordering)。
- **iterate 图级 loop=B**:引擎包 loop-body(一 thread + `ns=iter{k}`),**非 N 次独立 invoke**;loop 产出累积 checkpoint(体积随 N 增长属预期;**delta/compaction 不在本 WS 测**,归 E5)。
- **11-io 收敛**:仅测子图 inputs 放宽(父子 io 非 1:1 仍跑通,outputs 仍严校)。**文件 lazy 注入 / artifact 测试随 E2/E3 拆出的 WS**(§5/§9)。
- **无回归**(写成具体契约,非一行带过):
  - **predict 分支**:`predict_context` 经 `_build_skill_node(... predict_context=...)`(`:435`)透传到 `_resolve_phase_chat_model`,resolver 在 predict 下返回 `PredictGatewayChatModel`;迁 create_agent 后 `PredictGatewayChatModel.bind_tools()` **仍拦截**(干跑/mock 不真调模型),predict usage 归零不被 create_agent 改坏。
  - **usage 归属 / thinking 不拍平**:gateway 模型路径(`GatewayChatModel`/resolver 返回的 gateway 模型,**非仅** fake model)下,token usage 归属正确、thinking blocks 不被 create_agent 拍平。
- **真实 e2e**(非 CI 闸,必须真跑):一条真 skill 经 create_agent 跑通工具循环 + finish_task(结构化输出落 state)。

## 7. 内部子步骤顺序(严格串行,IR1 共享 graph_assembler.py;每步 RED→GREEN→契约门 gate 后才进下一步)
> **为何不拆成 E1a-E1e 独立 WS**(回应 codex round-1 建议):五个关注点**全改 `graph_assembler.py` 同一文件**,拆成多 WS **零并发收益**(同文件不能并行锁),只增协调开销;与 IMPL_PLAN §一「graph_assembler.py = 串行热点,只能一条串行链」+ gateway WS1 范例一致。采纳 codex **粒度顾虑的实质**:把内部步骤升级为**逐步 gated TDD 检查点**,并把最高风险的跨边界项(subagent 存活)拎成独立 gated 步,而非碎成多 WS。详见 §12。

1. **create_agent 构造 + 运行边界 + 6 槽接线**(K1/K2 + A1,**同一垂直切片**):`_build_skill_node`(`:437`)手写 loop(`:483-576`)→ create_agent 一次构造 + invoke;**本步必须一并接好全部运行边界**(缺一即假绿):① `state_schema=WorkflowState`(否则 data/flow 丢);② `system_prompt=` 系统提示;③ `invoke` config 给 `thread_id`+`checkpoint_ns`(checkpointer 可运行);④ `max_iterations` 接成 create_agent 迭代约束(不被 recursion_limit=10000 吞);⑤ `build_middleware_chain` 6 槽(现单槽 `:300`/`factory.py:68`)随构造接进;⑥ **finish_task 工具 schema 与 `CognitiveFlowMiddleware` 期望对齐**(改 `finish_task.py` 或 `cognitive_flow.py`)。
2. **subagent 在 create_agent 下重接线**(P0 gated 步,迁移断裂点):把 subagent 工具的 func 重接到引擎派发闭包(`_invoke_subagent_tool_t21`/`_subagent_runtime_map`,均在 graph_assembler 内),使 create_agent 原生 tool 节点调 subagent 时走真派发、拿到真 `WorkflowState`、**不命中** `loader.py:709` placeholder。本步 ★ 回归测试(§6)绿才进步骤 3。
3. **LOGIC 运行时契约**(I1/LE1-3,scope 收敛):`_build_logic_node`(`:325`)纯返回 + 砍 Context mutation;**FS 写/import 越界 FATAL 现成可测**;**`run_skill` 禁令 = WS-E6 交付**——本步**不声明"完整 LOGIC 干净"**,run_skill 退出条件二选一(E6 先于本步 / 本步显式降级 scope,见 §8)。
4. **iterate 执行**(I3):`:240-300` 扩 loop/图级;`manifest.py` BatchSpec→IterateSpec。
5. **11-io 子图 io 放宽**(I5,收敛):仅 `loader.py:528` 删 inputs 1:1 强校(outputs 保留)。**文件导入 lazy(E2)/ artifact(E3)已拆出本 WS**(跨 E4/E5/read_file/storage/runner,见 §5/§9)。

## 8. 验收标准(硬退出,IR4)
- [ ] §6 全部测试绿(含 ★ create_agent / state_schema / finish_task / 6 槽 / subagent / checkpointer 先 RED 后 GREEN)。
- [ ] AGENT phase 走 create_agent 且传 6 槽;手写 loop 已退役(无残留 `for _ in range(max_turns)`)。
- [ ] **`state_schema=WorkflowState`**:create_agent 后 `data/flow` 不被裁掉(★ 反例对照绿)。
- [ ] **finish_task schema 对齐**:绑定工具 schema = `CognitiveFlowMiddleware` 期望的 `business_data_md/reasoning/diagnostics_md`;finish 正确收、结构化输出落 state(★ 绿)。
- [ ] **subagent 走引擎真派发**(`_invoke_subagent_tool_t21`)且拿真 `WorkflowState`,**不命中** `loader.py:709` placeholder(★ 绿)。
- [ ] **checkpointer 可运行**:`invoke` 给 `thread_id`+`checkpoint_ns` → 小 N 真跑、checkpoint 写成、不污染外层 state(★ 绿)。**delta/compaction 不在本 WS 验收**(= WS-E5)。
- [ ] **max_iterations 保活**:phase 上限生效,不被 `recursion_limit=10000` 吞。
- [ ] **LLM usage 不丢**:进引擎事件流 **或** 显式 defer E4(+ message metadata 可见 + defer 记录)——二选一且测到。
- [ ] LOGIC action 纯返回;Context mutation / **FS 写 / import 越界**命中 purity FATAL(现成可测)。
- [ ] **`run_skill` 禁令 ordering(铁律,不再 xfail 稀释)**:二选一并在本节勾选 —— ☐ **(A)** WS-E6 的 run_skill 扫描码**先于**本 WS 的 LOGIC 子步骤完成,本 WS LOGIC 验收含 run_skill FATAL 绿;**或** ☐ **(B)** 本 WS LOGIC **显式降级**为"纯返回 runtime + FS/Context purity",**不声明完整 LOGIC 干净契约**,run_skill 禁令明确划归 E6(§1/§5 措辞同步降级)。**禁止** "声明 LOGIC 干净但 run_skill 仍能溜进去"的中间态。
- [ ] iterate 图级 loop=B(一 thread + ns)+ 节点级 loop accumulate;**子图 io 放宽(仅 inputs,outputs 严校)**。
- [ ] **无回归**:predict(`predict_context` 透传 + `PredictGatewayChatModel.bind_tools()` 仍拦截)/ usage 归属 / thinking blocks / tool-call metadata —— 各有专测且绿(gateway 模型路径,非仅 fake)。
- [ ] 至少一条**真实 e2e**(create_agent 工具循环 + finish_task 结构化输出落 state)人工跑通并记录。
- [ ] `uv run pytest packages/graph-agent/tests -q` 全绿;`uv run mypy`(改动文件)0 error。
- [ ] **11-io E2/E3 已拆出**:本 WS 仅含子图 io 放宽;文件导入 lazy / artifact 不在本 WS(= WS-E1-io,记 §9 + `IMPL_PLAN.md`)。

## 9. 不做(范围锁定,IR7)
- 不实现中间件**后 3 槽逻辑**(Tracing/ToolError/LoopDetection)= **WS-E2**(本 WS 只接线 6 槽外壳)。
- 不做 checkpoint 内层 delta/compaction(E5)、错误 V2(E3)、V4 trace 事件(E4)、purity 扫描器 **run_skill 扫描码**(E6,本 WS LOGIC 仅触发现成 FS/import FATAL)、退出闸(E8)、resume/golden(E7)。
- **不做 11-io 文件导入 lazy(E2)+ artifact business_data_md(E3)**:跨 `tools/builtin/read_file.py` + `state.py`(E5)+ `callbacks/events.py`(E4)+ `storage.py` + `runner.py:598`,owns 必相交违 IR1 → **另立 WS-E1-io(依赖 E4/E5),已记 `IMPL_PLAN.md` §二/§三**。本 WS 11-io **仅**子图 io 放宽(`loader.py:528`)。
- 不动 gateway 内部(只用 `GatewayChatModel` 接口)。
- 范围外问题 → 记 `docs/deferred-items.md`。

## 10. baseline 回写指令(IR6,实现后)
照真实代码改:`01-agent-loop/baseline.md`(手写 loop 退役、create_agent live)、`03-assemble/baseline.md`(_build_skill_node 收口)、`02-middleware/baseline.md`(6 槽接 live)、`graph-exec/baseline.md`(LOGIC 纯返回 runtime、iterate loop/图级 live、11-io **仅**子图 io 放宽)、`02-iterate/baseline.md`(loop/图级 live)。**finish_task schema 对齐后**回写 `01-agent-loop/baseline.md` 的 finish_task 形态。回写后 baseline = 真实代码(此时"目标当现状"物理上不可能)。

## 11. 评审检查点
- **契约门(Claude 审测试,放 Gemini 前)**:★ 全集(create_agent metadata 不丢、`state_schema=WorkflowState` 保 data/flow、finish_task schema 一致、6 槽接线、subagent 真派发、checkpointer 可运行)是否**忠实编码** alignment 目标;LOGIC 纯返回测试覆盖 Context mutation/FS 写/import 越界(**run_skill 归 E6,见 §8 ordering**);max_iterations 保活 + LLM usage 不丢各有专测。
- **Codex 审查退出** = §8 全满足(非主观满意)。
- **Claude 终审**:① create_agent 编排外壳/provider 中立是否守住 **AL2 核心决策**(不被 provider 格式统一推翻);② baseline 回写诚实(对真实代码);③ e2e 非 mock 到绿。

## 12. 决策记录(codex round-1 复核处置)
> codex round-1 复核(7 findings,核心建议「打回、拆成 E1a-E1e」)。逐条**核源**后处置如下(已采信 = 改了任务书;已推翻 = 附证据)。

| codex finding | 核源结论 | 处置 |
|---|---|---|
| **P0 subagent 断裂**(create_agent 裸交 tools → 命中 placeholder) | **证实**:`graph_assembler.py:535-544` 按名拦截真派发,`loader.py:709` placeholder `raise NotImplementedError`;删 loop 后 create_agent 原生 tool 节点会调 placeholder | **采纳**:§5 新增 subagent 存活契约 + §7 步骤 2 独立 gated 步 + §6/§8 ★ 回归测试。修复在 graph_assembler(已 owns,无新增文件) |
| **P0 checkpoint E1/E5 边界含糊** | **部分证实**:§5/§6 旧文把 checkpoint 体积当优化目标,与「E5 owns checkpoint 内层」混 | **采纳**:§5/§6/§8 划清——E1 仅**接线** checkpointer + ns;delta/compaction = E5 |
| **P0 owns 漏 purity** | **推翻(措辞)**:`core/purity.py` §3 已明划 WS-E6,非漏;FS purity FATAL(`loader.py:367/770`)**现成**。但 `run_skill` 扫描**确不存在** | **部分采纳**:§5/§8 拆 FS-FATAL(E1 可测)vs run_skill-FATAL(E6 gated) |
| **P1 §6 缺 predict/thinking/usage** | **推翻**:旧 §6 行 55 已列,codex 漏看;有效点 = 写太浅 | **采纳实质**:§6 把 predict_context 透传 / `bind_tools()` 拦截 / gateway 模型路径写成具体可测契约 |
| **P1 11-io 越界 io/manager/storage/read_file** | **未证实(推测)**:graph_assembler 仅 import io helper、不编辑 io 模块;落点 `loader.py:528`(已 owns)+ `:287` | **不预认领**:§5 注明 owns 内可完成;若 impl 期确需改 io 模块再追加 owns |
| **P1 §7 顺序(create_agent / 6 槽 倒置)** | **证实**:create_agent 构造要消费 6 槽,应同切片 | **采纳**:§7 步骤 1 合并 create_agent + 6 槽为一垂直切片 |
| **P1 WS-E1 过大,拆 E1a-E1e** | **不采纳(架构裁定)**:五关注点全改 `graph_assembler.py` 同一文件 → 拆多 WS **零并发收益**(同文件不能并行锁,codex 自己也承认子 WS 仍串行),只增协调开销;违 IMPL_PLAN §一「串行热点 = 一条链」+ gateway WS1 范例 | **采纳实质、不碎 WS**:§7 升级为逐步 gated TDD 检查点 + subagent 独立 gated 步,保单一文件锁 |

**架构裁定要点**:codex 的「拆」本质是想要**更细的 TDD/审查粒度**(它承认子 WS 仍串行)。粒度诉求用「§7 逐步 gated 检查点 + 高风险项独立成步」满足即可,无需把同文件锁碎成 5 个 WS。WS partition 的依据是**文件归属并发**(IR1),同文件无并发可分,拆了反而要在 graph_assembler 上做跨 WS 锁协调。

### round-2 复核处置(FAIL 5.6 → 返工;codex 这轮基本全对,含纠我 round-2 一处反驳错)
> codex round-2(逐条带 LangChain/LangGraph 真源码 file:line + 本地验证)。**全部核源后**处置:

| round-2 finding | 核源结论 | 处置 |
|---|---|---|
| **P0 新:create_agent 默认 `AgentState` 裁掉 `data/flow`** | **证实**:`factory.py` `base_state = state_schema or AgentState` → 不传则 data/flow 不在 agent state | **采纳**:§5/§7 步骤1 必传 `state_schema=WorkflowState` + §6/§8 ★ 反例对照测试 |
| **P0 新:finish_task schema 冲突** | **证实**:工具 `_finish_task(markdown)`(finish_task.py:40) vs 中间件读 `business_data_md/reasoning/diagnostics_md`(cognitive_flow.py:479) | **采纳**:§5/§7 步骤1 加对齐契约 + owns 纳入 finish_task.py/cognitive_flow.py + §6/§8 ★ 测试 |
| **P0 返工:checkpointer 只编译期接受不够** | **证实**:`runner.py:689` 只给外层图 thread_id,内层 ns 未接;checkpoint alignment 列头号 D-test | **采纳**:§5/§8 改为"可运行验收"(invoke 给 thread_id+checkpoint_ns、小N真跑、不污染外层) |
| **P1 新:max_iterations 被 recursion_limit=10000 吞** | **证实**:`factory.py:1597` 默认近无界 vs 手写 loop 尊重 `phase_ast.max_iterations`(:510) | **采纳**:§5/§6/§8 加 max_iterations 保活测试 |
| **P1 新:LLMCallEvent 无接替者** | **证实**:手写 loop 手动发 `LLMCallEvent`(:514),迁后消失 | **采纳**:§5/§8 要求 bridge 或显式 defer E4 + 测,不静默丢 |
| **P1 返工:11-io owns 违 IR1(我 round-2 反驳错)** | **证实 codex、推翻我自己**:`task-spec-standard` IR1 = owns 必须全集不预留;graph-exec alignment §2 第29-30行 11-io E2/E3 跨 read_file/state.py(E5)/events(E4)/storage/runner | **纠错采纳**:11-io 收敛为仅子图 io 放宽;E2/E3 拆出另立 WS(§5/§9)。**我 round-2 "owns 内可完成"判断错——把 slice helper 是 import 误当全部 11-io 在 graph_assembler 内** |
| **P1 返工:run_skill xfail 稀释退出** | **证实**:graph-exec §2 第18行 run_skill = LOGIC 硬禁;E1 声明"LOGIC 干净"却 xfail = 留洞 | **采纳**:§8 改为 ordering 二选一(E6 先于本步 / 本步显式降级 scope),禁中间态 |
| 不拆 E1a-E1e | codex 此轮不再坚持(认可同文件无并发收益) | 维持单 WS + gated 步 |

**自检教训(记忆点)**:round-2 我对 11-io 的反驳,错在"拿一次浅 grep(graph_assembler 只 import `phase_inputs_from_state`)就下结论 owns 内可完成",没去读 graph-exec alignment §2 对 11-io E2/E3 列的真实改动面(read_file/StateManager/events/storage/runner)。**核源要核到 alignment 的目标改动面,不只看 live import 关系。**
