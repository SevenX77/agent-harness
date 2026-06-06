---
ws_id: WS-E1-create-agent-core
modules: [01-agent-loop, 03-assemble, 02-middleware, 04-run-outer/01-graph-exec, 02-iterate]
depends_on: []          # gateway WS-1(GatewayChatModel 稳)是 soft 依赖,不阻塞:可先用现有 GatewayChatModel
blocks: [WS-E2, WS-E5, WS-E8]
owns_files:
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py   # 热点:create_agent/6槽接线/LOGIC节点/iterate/11-io 接线
  - packages/graph-agent/src/graph_agent/middleware/factory.py     # 6 槽 build_middleware_chain 接进 AGENT
  - packages/graph-agent/src/graph_agent/middleware/__init__.py    # 顺序契约(若需调整)
  - packages/graph-agent/src/graph_agent/core/manifest.py          # BatchSpec → 统一 IterateSpec(iterate)
  - packages/graph-agent/src/graph_agent/core/loader.py            # 仅 :528 子图 io 1:1 删(11-io E1);其余 loader 勿动
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
把 `graph_assembler.py` 的**手写 ReAct loop 换成原生 `create_agent`**,并在同一热点文件内串行收口 **6 槽中间件接线 / LOGIC 干净契约 / iterate 执行 / 11-io 接线**。**为什么**:① keystone——中间件后 3 槽(E2)、内层 checkpoint(E5)、退出闸(E8)都挂 create_agent;② 手写 loop = 重复造轮子,还得自己处理 tool-call 消息配对、return-direct、middleware 顺序、checkpoint 交互(现 `:483-576` 逐手调 `model.invoke`/`tool.invoke`、无 tool_calls 时裸退)。目标机制以 `spec_ssot` 为准,不在此复制。

## 2. SSOT 指针(grounding,IR2/IR5)
- **目标**:见 frontmatter `spec_ssot`。
- **现状(起点)**:`../02-mechanism/05-run-inner/01-agent-loop/baseline.md`、`../03-assemble/baseline.md`、`../02-middleware/baseline.md`(6 槽 3 真 3 空)、`../04-run-outer/01-graph-exec/baseline.md`、`../02-iterate/baseline.md`(仅节点级 batch)。
- **实现前必读源码(先回读关键符号 + 现状再动手)**:
  - `core/graph_assembler.py:437-576`(`_build_skill_node` + 手写 loop,待替换)、`:240-300`(节点级 batch 包装 + 接线)、`:325`(`_build_logic_node`)、`:287`(`_wrap_phase_runtime_node`,11-io 落点)
  - `middleware/factory.py:29`(`build_middleware_chain` 6 槽)/`:68`(单槽 live)、`middleware/__init__.py:58`(顺序契约)
  - `core/manifest.py:121`(`BatchSpec`)、`core/loader.py:528`(子图 io 1:1 强校)

## 3. 文件归属(并发锁,IR1)
- **本 WS owns(可改/建)**:见 frontmatter `owns_files`。
- **禁止触碰**:`middleware/tracing.py`/`tool_error.py`/`loop_detection.py`→**WS-E2**;`core/checkpointer.py`/`state.py`→**WS-E5**;`core/exceptions.py`/`error_registry.py`/`result.py`→**WS-E3**;`callbacks/events.py`/`emit.py`→**WS-E4**;`core/purity.py`→**WS-E6**;`middleware/nudge_injector.py`/exit middleware→**WS-E8**。
- **共享协调**:`graph_assembler.py` 内 create_agent/LOGIC/iterate/11-io 多处改 → **内部串行(§7)**,不并发编辑。`loader.py` **仅** `:528` 子图 io 那段归本 WS,其余 loader 勿动。

## 4. 现状锚点(baseline)
手写 ReAct loop live(`:483-576`);AGENT 只接单槽 middleware(`factory.py:68`);LOGIC action 用可变 Context facade;仅节点级 batch、无 loop/图级;子图 io 1:1 强校(`loader.py:528`)。详见各 baseline。

## 5. 目标行为(可测的契约)
- **create_agent**(agent-loop §2):AGENT phase → `create_agent(model=GatewayChatModel, tools=业务+framework+finish_task+subagent, middleware=6槽, checkpointer 经 ns="<id>/agent")` → 一次 `invoke` → finish_task;**不再**手拼 ToolMessage / 无 tool_calls 裸退。`model` 吃 `GatewayChatModel`(AL2 核心:provider 差异归 gateway,引擎不分支)。
- **6 槽接线**(middleware §2):`build_middleware_chain` 6 槽按 `__init__.py:58` 顺序接进 AGENT。
- **LOGIC 干净契约**(graph-exec LE1-3):`_build_logic_node` action = `def <name>(inputs)->dict` 纯返回、只读 inputs;砍 Context `set/update/delete`;硬禁 action 里 `run_skill`/FS(purity 扫描器拦,码归 WS-E6 协调)。
- **iterate**(02-iterate §2):节点级 loop(`accumulate{var,init,from,merge}`)/ 图级 batch(`Send`)/ 图级 loop=B(引擎包 loop-body,一 thread + `ns=iter{k}`);统一 `iterate` 配置(兼容现 `batch`)。
- **11-io**(graph-exec E1-E3):子图 io 放宽(`loader.py:528` 只校 outputs)、文件导入→黑板 lazy(`:287` 前置步)、io.outputs artifact 路径标注。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4;抽 alignment §6)
- ★ **create_agent 端到端**(D-test-3):`create_agent(model=GatewayChatModel)` 跑通,gateway usage / thinking blocks / tool-call metadata **不丢**;多轮 tool loop **不裸退**。
- ★ **6 槽接线**:live `assemble_graph` 的 AGENT phase 传 **6 槽** middleware(非单槽)。
- **LOGIC 纯返回**:action 同输入同输出(无 LLM、确定性);Context mutation / `run_skill` / FS 命中编译期 `[F-v3-logic-action-purity-violation]` FATAL。
- **iterate 图级 loop=B**:引擎包 loop-body(一 thread + `ns=iter{k}`),**非 N 次独立 invoke**;loop 累积 checkpoint 体积 O(N)。
- **11-io**:子图 inputs 放宽(父子 io 非 1:1 仍跑通);文件 lazy 注入(跑到节点才注,非图启动)。
- **无回归**:predict 分支(`PredictGatewayChatModel`)、usage 归属、thinking 不拍平 —— 各有专测。
- **真实 e2e**(非 CI 闸,必须真跑):一条真 skill 经 create_agent 跑通工具循环 + finish_task。

## 7. 内部子步骤顺序(严格串行,IR1 共享 graph_assembler.py)
1. **create_agent 构造**(K1/K2):`_build_skill_node`(`:437`)手写 loop(`:483-576`)→ create_agent 一次构造 + invoke;tools 直接交 create_agent。
2. **6 槽接线**(A1):`build_middleware_chain` 6 槽接进(现单槽 `:300`/`factory.py:68`)。
3. **LOGIC 干净契约**(I1/LE1-3):`_build_logic_node`(`:325`)纯返回 + 砍 Context mutation。
4. **iterate 执行**(I3):`:240-300` 扩 loop/图级;`manifest.py` BatchSpec→IterateSpec。
5. **11-io 接线**(I5):`loader.py:528` 子图 io 放宽 + `:287` 文件导入/artifact。

## 8. 验收标准(硬退出,IR4)
- [ ] §6 全部测试绿(含 ★ create_agent + 6 槽 先 RED 后 GREEN)。
- [ ] AGENT phase 走 create_agent 且传 6 槽;手写 loop 已退役(无残留 `for _ in range(max_turns)`)。
- [ ] LOGIC action 纯返回;Context mutation / run_skill / FS 命中 purity FATAL(与 WS-E6 协调码就绪)。
- [ ] iterate 图级 loop=B(一 thread + ns)+ 节点级 loop accumulate;子图 io 放宽。
- [ ] **无回归**:predict / usage / thinking blocks / tool-call metadata —— 各有专测且绿。
- [ ] 至少一条**真实 e2e**(create_agent 工具循环)人工跑通并记录。
- [ ] `uv run pytest packages/graph-agent/tests -q` 全绿;`uv run mypy`(改动文件)0 error。

## 9. 不做(范围锁定,IR7)
- 不实现中间件**后 3 槽逻辑**(Tracing/ToolError/LoopDetection)= **WS-E2**(本 WS 只接线 6 槽外壳)。
- 不做 checkpoint 内层 delta/compaction(E5)、错误 V2(E3)、V4 trace 事件(E4)、purity 扫描器本体(E6,本 WS 只触发其码)、退出闸(E8)、resume/golden(E7)。
- 不动 gateway 内部(只用 `GatewayChatModel` 接口)。
- 范围外问题 → 记 `docs/deferred-items.md`。

## 10. baseline 回写指令(IR6,实现后)
照真实代码改:`01-agent-loop/baseline.md`(手写 loop 退役、create_agent live)、`03-assemble/baseline.md`(_build_skill_node 收口)、`02-middleware/baseline.md`(6 槽接 live)、`graph-exec/baseline.md`(LOGIC 纯返回、iterate loop/图级 live、11-io 子图 io 放宽/文件导入)、`02-iterate/baseline.md`(loop/图级 live)。回写后 baseline = 真实代码(此时"目标当现状"物理上不可能)。

## 11. 评审检查点
- **契约门(Claude 审测试,放 Gemini 前)**:★ 两条(create_agent metadata 不丢、6 槽接线)是否**忠实编码** alignment 目标;LOGIC 纯返回测试是否覆盖 Context mutation/run_skill/FS 三类违例。
- **Codex 审查退出** = §8 全满足(非主观满意)。
- **Claude 终审**:① create_agent 编排外壳/provider 中立是否守住 **AL2 核心决策**(不被 provider 格式统一推翻);② baseline 回写诚实(对真实代码);③ e2e 非 mock 到绿。
