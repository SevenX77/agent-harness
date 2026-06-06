---
ws_id: WS-E1-create-agent-core
modules: [01-agent-loop, 03-assemble, 02-middleware, 04-run-outer/01-graph-exec, 02-iterate]
depends_on: []          # gateway WS-1(GatewayChatModel 稳)是 soft 依赖,不阻塞:可先用现有 GatewayChatModel
blocks: [WS-E2, WS-E5, WS-E8]
owns_files:
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py   # 热点:create_agent/6槽接线/subagent重接线(_invoke_subagent_tool_t21,:1057+)/LOGIC节点/iterate/11-io 接线
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
- **create_agent**(agent-loop §2):AGENT phase → `create_agent(model=GatewayChatModel, tools=业务+framework+finish_task+subagent, middleware=6槽, checkpointer)` → 一次 `invoke` → finish_task;**不再**手拼 ToolMessage / 无 tool_calls 裸退。`model` 吃 `GatewayChatModel`(AL2 核心:provider 差异归 gateway,引擎不分支)。
- **subagent 在 create_agent 下存活**(P0,迁移断裂点):现状手写 loop 按工具名拦截 subagent(`graph_assembler.py:535-544`:`if name in subagent_by_tool_name → _invoke_subagent_tool_t21(... runtime=subagent_runtime_by_tool_name[name])`),**绕过** loader 给 subagent 工具挂的 placeholder func(`loader.py:709` `_pending_call_subagent_tool` 直接 `raise NotImplementedError`)。删掉手写 loop、把 `all_tools` 裸交 create_agent 后,create_agent 原生 tool 节点会去调那个 placeholder → 炸 `NotImplementedError`,**核心路径断裂**。本 WS 必须在交给 create_agent 前,把 subagent 工具的 func **重接** 到引擎派发闭包(复用 `_invoke_subagent_tool_t21` + `_subagent_runtime_map`,均在 `graph_assembler.py` 内、已 owns,**不动** `loader.py:709`)。验收:create_agent 工具循环里调 subagent → 走引擎真派发,**不命中** placeholder。
- **6 槽接线**(middleware §2):`build_middleware_chain` 6 槽按 `__init__.py:58` 顺序接进 AGENT。**与 create_agent 同一垂直切片**(create_agent 构造本身要消费这 6 槽,二者不可分步,见 §7 步骤 1)。
- **checkpointer 仅接线、不优化**(E1/E5 边界):本 WS 只让 create_agent **接受** `checkpointer` 参数并按 `ns="<id>/agent"` 挂到共享 base(接线层);loop=B 产出**累积** checkpoint(一 thread + `ns=iter{k}`,体积随 N 增长属**预期现状**)。checkpoint 内层 **delta/compaction/state 模型优化 = WS-E5**,不在本 WS 验收(§9)。
- **LOGIC 干净契约**(graph-exec LE1-3):`_build_logic_node` action = `def <name>(inputs)->dict` 纯返回、只读 inputs;砍 Context `set/update/delete`;**FS 写禁令现成可测**(`purity.py` 扫 os/shutil/tempfile/写模式 → `loader.py:367/770` 已发 `[F-v3-logic-action-purity-violation]` FATAL);**`run_skill` 禁令 gated 在 WS-E6**(`purity.py` 现**不扫** `run_skill`,需 E6 补该扫描码,本 WS 此项验收待 E6 就绪后开)。
- **iterate**(02-iterate §2):节点级 loop(`accumulate{var,init,from,merge}`)/ 图级 batch(`Send`)/ 图级 loop=B(引擎包 loop-body,一 thread + `ns=iter{k}`);统一 `iterate` 配置(兼容现 `batch`)。
- **11-io**(graph-exec E1-E3):子图 io 放宽(`loader.py:528` 只校 outputs,已 owns)、文件导入→黑板 lazy(`:287` 前置步)、io.outputs artifact 路径标注。**owns 范围内可完成**(graph_assembler 仅 import io helper `phase_inputs_from_state`,不编辑 io 模块);若 impl 期发现 lazy 注入确需改 `io/storage.py`/`tools/builtin/read_file.py`,届时再追加 owns(**待确认,不预先认领**)。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4;抽 alignment §6)
- ★ **create_agent 端到端**(D-test-3):`create_agent(model=GatewayChatModel)` 跑通,gateway usage / thinking blocks / tool-call metadata **不丢**;多轮 tool loop **不裸退**。
- ★ **6 槽接线**:live `assemble_graph` 的 AGENT phase 传 **6 槽** middleware(非单槽)。
- ★ **subagent 在 create_agent 下不命中 placeholder**(P0 回归,迁移断裂点专测):create_agent 工具循环里调一个 subagent 工具 → 走引擎真派发(`_invoke_subagent_tool_t21`),**绝不**触发 `loader.py:709` `_pending_call_subagent_tool` 的 `NotImplementedError`。
- **LOGIC 纯返回**:action 同输入同输出(无 LLM、确定性);Context mutation / FS 写命中编译期 `[F-v3-logic-action-purity-violation]` FATAL(**FS 写现成可测**);`run_skill` 违例命中 FATAL = **gated 测试,待 WS-E6 补 run_skill 扫描码后开**(标 `xfail/skip` + 注明依赖 E6)。
- **iterate 图级 loop=B**:引擎包 loop-body(一 thread + `ns=iter{k}`),**非 N 次独立 invoke**;loop 产出累积 checkpoint(体积随 N 增长属预期;**delta/compaction 不在本 WS 测**,归 E5)。
- **11-io**:子图 inputs 放宽(父子 io 非 1:1 仍跑通);文件 lazy 注入(跑到节点才注,非图启动)。
- **无回归**(写成具体契约,非一行带过):
  - **predict 分支**:`predict_context` 经 `_build_skill_node(... predict_context=...)`(`:435`)透传到 `_resolve_phase_chat_model`,resolver 在 predict 下返回 `PredictGatewayChatModel`;迁 create_agent 后 `PredictGatewayChatModel.bind_tools()` **仍拦截**(干跑/mock 不真调模型),predict usage 归零不被 create_agent 改坏。
  - **usage 归属 / thinking 不拍平**:gateway 模型路径(`GatewayChatModel`/resolver 返回的 gateway 模型,**非仅** fake model)下,token usage 归属正确、thinking blocks 不被 create_agent 拍平。
- **真实 e2e**(非 CI 闸,必须真跑):一条真 skill 经 create_agent 跑通工具循环 + finish_task。

## 7. 内部子步骤顺序(严格串行,IR1 共享 graph_assembler.py;每步 RED→GREEN→契约门 gate 后才进下一步)
> **为何不拆成 E1a-E1e 独立 WS**(回应 codex round-1 建议):五个关注点**全改 `graph_assembler.py` 同一文件**,拆成多 WS **零并发收益**(同文件不能并行锁),只增协调开销;与 IMPL_PLAN §一「graph_assembler.py = 串行热点,只能一条串行链」+ gateway WS1 范例一致。采纳 codex **粒度顾虑的实质**:把内部步骤升级为**逐步 gated TDD 检查点**,并把最高风险的跨边界项(subagent 存活)拎成独立 gated 步,而非碎成多 WS。详见 §12。

1. **create_agent 构造 + 6 槽接线**(K1/K2 + A1,**同一垂直切片**——create_agent 构造本身要消费 6 槽,不可分步):`_build_skill_node`(`:437`)手写 loop(`:483-576`)→ create_agent 一次构造 + invoke;`build_middleware_chain` 6 槽(现单槽 `:300`/`factory.py:68`)随构造一并接进;`checkpointer` 作为参数接受(接线层,不优化)。
2. **subagent 在 create_agent 下重接线**(P0 gated 步,迁移断裂点):把 subagent 工具的 func 重接到引擎派发闭包(`_invoke_subagent_tool_t21`/`_subagent_runtime_map`,均在 graph_assembler 内),使 create_agent 原生 tool 节点调 subagent 时走真派发、**不命中** `loader.py:709` placeholder。本步 ★ 回归测试(§6)绿才进步骤 3。
3. **LOGIC 干净契约**(I1/LE1-3):`_build_logic_node`(`:325`)纯返回 + 砍 Context mutation;FS 写 FATAL 现成可测,`run_skill` FATAL 待 E6(标 gated)。
4. **iterate 执行**(I3):`:240-300` 扩 loop/图级;`manifest.py` BatchSpec→IterateSpec。
5. **11-io 接线**(I5):`loader.py:528` 子图 io 放宽 + `:287` 文件导入/artifact。

## 8. 验收标准(硬退出,IR4)
- [ ] §6 全部测试绿(含 ★ create_agent + 6 槽 + subagent 先 RED 后 GREEN)。
- [ ] AGENT phase 走 create_agent 且传 6 槽;手写 loop 已退役(无残留 `for _ in range(max_turns)`)。
- [ ] **subagent 在 create_agent 下走引擎真派发**(`_invoke_subagent_tool_t21`),**不命中** `loader.py:709` placeholder(★ 回归测试绿)。
- [ ] LOGIC action 纯返回;Context mutation / **FS 写**命中 purity FATAL(现成可测)。
- [ ] **`run_skill` action 禁令** = gated 项:E6 补 run_skill 扫描码后该测试转绿;**未就绪前以 `xfail/skip` 显式标注**,不算阻塞本 WS 退出(依赖记 §11 / `docs/deferred-items.md`)。
- [ ] iterate 图级 loop=B(一 thread + ns)+ 节点级 loop accumulate;子图 io 放宽。
- [ ] **checkpointer 仅接线**:create_agent 接受 checkpointer 参数 + ns 挂共享 base;loop=B 产出累积 checkpoint(预期)。**delta/compaction 不在本 WS 验收**(= WS-E5)。
- [ ] **无回归**:predict(`predict_context` 透传 + `PredictGatewayChatModel.bind_tools()` 仍拦截)/ usage 归属 / thinking blocks / tool-call metadata —— 各有专测且绿(gateway 模型路径,非仅 fake)。
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
