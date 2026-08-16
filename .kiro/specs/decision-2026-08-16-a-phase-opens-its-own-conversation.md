# 决议:一个相位开启它自己的对话

- 日期:2026-08-16
- 范围:`packages/graph-agent/src/graph_agent/runtime/state_mapper.py`(`StateMapper.build_phase_input`)
- 用户裁决:2026-08-16「相位之间的对话串台 要改」
- 触发:`story-deconstruction-v3-lab` 真跑 `2026-08-15T12-40-22_bb6e358a` 的现场证据

## 决策

相位的 agent 以**空 messages** 启动。相位之间的数据只走黑板(`io.inputs` / `io.outputs`);
上游相位的对话记录不再作为第二条未声明的入口递进来。

写回不动:`wrap_phase_output` 仍把该相位产出的 messages 并回全局通道,所以整次运行的
对话记录、checkpoint、HITL resume 一律不变。**改的是"递给相位什么",不是"运行留下什么"。**

## 这不是新规矩,是一条只执行了一半的旧裁决

用户在九轮定稿 Round 8 第 3 条直接定过调:

> 3. phase 间默认强隔离（`messages = []` by-design）+ 按需挖掘机制（context_access opt-in）
> —— `docs.backup-2026-05-20/archive/superpowers_history/2026-04-27-prompt-schema-9round-final-plan.md:79`

同文件 `:97` 把它列为设计哲学第 2 条:「Phase 间默认彻底隔离记忆（`messages = []`）。依赖明确
声明的 IoInput/IoOutput 传递核心数据」。这条裁决今天仍然有效并被现行决议加锁——
`docs/design/2026-08-15-legacy-cognitive-features-migration-decision.md:184`:

> **出生档案。** 用户直接定调,九轮定稿 Round 8 第 3 条:「phase 间默认强隔离(messages=[]
> +按需挖掘机制(context_access opt-in)」。**opt-in 语义是用户裁定的,必须原样保留。**

**决定性的一条**:live 代码自己引用了这条裁决,却只实现了后半句。
`core/graph_assembler.py` 的 `_cognitive_framework_tools` docstring 原文:

> the context-access readers stay opt-in behind the phase's ``context_access``
> declaration (Round 8: strong isolation by default)

"按需挖掘"(`context_access` opt-in)已经落地;"默认强隔离"从来没接线。所以这不是设计留白下
的自由选择,是同一条裁决被执行了一半。

MVP0 曾有明文(`docs/engine/mvp0/state-and-io-contract/mvp0-alignment.md:55`:
「`scratch={}`、`messages=[]`,阻断草稿和 ReAct 对话跨 phase 泄漏」),MVP1 **没有正面重述**——
而 `02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md:17` 自己标着运行时流正文
「🚨 待 mvp1 自写」。本 PR 一并补写,免得下次还得靠推导(见"同批补写的设计正文")。

## 漂移是怎么进来的:两个透传点,都没有决议记录

| 透传点 | 引入提交 | 日期 | 提交标题 |
|---|---|---|---|
| `runtime/state_mapper.py:169` `messages=list(state.get("messages", []))` | `353fbb8a` | 2026-05-31 | Refine Copilot role cards and test feedback |
| `core/graph_assembler.py:2194` `"messages": state["messages"]` | `3edd12d0` | 2026-06-07 | checkpoint(engine): WS-E1 step1 create_agent core start |

两条提交的标题都与"相位间对话语义"无关,仓内查不到任何相关决议。

## 现场证据(真跑,不是推导)

`.workspace/runs/2026-08-15T12-40-22_bb6e358a`,DeepSeek V4 Flash,42 次相位执行:

1. **`continuity` 相位开场 61 条消息,其中 60 条属于别的相位。** 11 条 human 消息全部是别的相位的
   nudge 与死循环诊断,包括一条原文写着「工具 `finish_task` 在 phase `foreshadow` 中连续或滑窗内
   重复执行了 3 次」——一条关于**另一个相位**的诊断,被当作给 continuity 的指令递了进去。
2. **`foreshadow` 与 `prop` 相位开场继承了 `entity_and_characters` 的整段已完成对话**(含它被驳回的
   通知和两次 `PHASE_COMPLETE`),随后照着上一个相位的样子提交了实体/角色字段,被 `finish_task` 以
   `Extra inputs are not permitted` 驳回,烧掉若干轮重试。
3. 六个并行维度相位**全部**以 10 条消息起步(自己 2 条 + 继承 8 条)。
4. 42 次相位执行只有 38 次 `runtime_input_injected`,`continuity` 与 `settings` 一次都没有。

**第 4 条要说准确**:这不等于"相位瞎跑"。作者写的系统提示词自己会插值 `{字段}`——实测 continuity 的
系统提示词里确实带着它要检查的事件 ID、角色名和道具名。丢掉的是**引擎自己那份结构化输入 JSON 块**,
不是数据本身。机制:`middleware/runtime_input.py:64` 的判据是「整份历史里一条 HumanMessage 都没有
才注入」,而 nudge / dead-end / 死循环诊断全都以 HumanMessage 写进共享通道
(`exit_control.py:209,306,327`、`execution_control.py:271`、`loop_detection.py:134`),
所以第一次 nudge 之后这个块就再也不投了。

## 修在哪一层,以及为什么不是另一层

改 `build_phase_input`(mapper),不是改 `graph_assembler.py:2194`。

`PhaseNodeWrapper._wrapped`(`state_mapper.py:451-456`)先调 `build_phase_input` 造出相位切片,
再把它交给相位节点;`_skill_node` 收到的 `state` 就是这份切片。所以改 mapper 一处,两个透传点
同时归零,而且 `graph_assembler.py:2213-2215` 的 `orig_msg_count = len(orig_messages)` 会跟着
自动归零——那个基准是用来切出"本次新增的消息"的,下游挂着未知工具校验、token 记账和
`completed_tool_call` 事件三件事。

**只改 assembler 那一行会更糟**:入参空了而基准仍按旧 state 计算 → `new_messages` 恒为空 →
上述三件事**全部静默失效**,而现有测试全是单相位(基准本来就是 0)抓不到。这是本次最危险的一个
分叉,记在这里以免以后有人"顺手简化"。

## 借了什么、拒绝了什么

借的是**进程式的参数传递语义**:被调用方拿到的是显式声明的参数,不是调用方的栈。
本仓已有的两处同形实现是直接参照物——SUBGRAPH 节点(`graph_assembler.py:1638`)与 subagent
(`:2916`)**今天就已经是 `messages=[]`**。缺口精确落在**同一张图内相邻相位之间**,所以这次改动是把
既有语义补齐到最后一处,不是引入新语义。

拒绝的是 variant B(连写回一起停)。写回停掉会动到 HITL:`core/runner.py` 的 resume 路径从
`graph.get_state(...).values["messages"]` 找未完成的 tool call,停写回会读到空表;
`tests/e2e/test_ws_e1_create_agent_step1.py:163` 也从 `result["messages"]` 取 usage_metadata。
入参侧已经解决全部已观察到的危害,写回侧的代价没有对应收益——**不为将来可能的需求预留**。

## middleware 影响:三槽净修复,零槽失效

PR C/D/E 之后的链是 10 槽(契约 8 槽 `middleware/__init__.py:65-74` + 装配器前置 2 槽
`graph_assembler.py:2111-2119`)。逐槽核对:

| 槽 | 读 messages 的方式 | 隔离后 |
|---|---|---|
| RuntimeInput(前置) | 全量扫「有没有 HumanMessage」 | **修好**:下游相位重新拿到自己的输入 JSON 块 |
| ToolHistoryIntegrity(前置) | 每次请求无状态重建 | 无害,少扫一段 |
| ProtocolValidation | 不读 | 无影响 |
| CognitiveFlow | 只读 `messages[-1]` | 无影响 |
| ExecutionControl | 全量反扫连续同工具 error | **修好**:不再把上游相位的失败流当本相位 dead-end |
| Compaction | 全量数 token | **回到设计尺度**(下详) |
| Tracing / ToolError | 不读 | 无影响 |
| LoopDetection | 最近 5 条 ToolMessage 签名计数 | **修好**:六个并行相位各写一条 `PHASE_COMPLETE` 就能灌满窗口误报 |
| ExitControl | 只读 `messages[-1]` | messages 侧无影响 |

**Compaction 的尺度**:代码上它数的是继承来的整份历史,所以实际尺度是"从 run 开始到本相位为止";
而它的参数出处 `middleware/compaction.py:51-55` 注释原文写着「User ruling P0-1 (nine-round
finalization)」——**和 Round 8 是同一份定稿**。同一位用户在同一次定稿里既要求相位间隔离、又要求挂
压缩,所以压缩从来就是相位内的机制。「1000 章」那个极限场景的 O(N²) 来自**同一相位跑 1000 轮**
(loop / batch),不是跨相位。隔离之后压缩才第一次运行在它被设计的尺度上。

## 不变的东西(澄清用)

- 全局 `WorkflowState.messages` 通道**仍在累积**每个相位的产出,trace / checkpoint 体积不变。
- HITL / resume 不受影响:checkpoint 按 `agent:<phase>` 分车道,恢复点靠
  (thread_id, checkpoint_ns) + 业务 data 键定位,不靠跨相位对话。
- 引擎公开 API 不变:`RunResult` 不含 messages,`result.context` 只装终态黑板。
- Studio 不需要改一行:trace 投影层显式丢弃 messages。

## 验收判据

`packages/graph-agent/tests/runtime/test_phase_conversation_isolation.py`(两个顺序 AGENT 相位,
alpha 第一轮故意只出文本不调工具从而触发 nudge):

1. beta 的开场消息条数**等于** alpha 的开场条数;
2. alpha 被 nudge 之后,beta 仍然拿得到自己声明的 `alpha_out` 输入;
3. 任何非 alpha 的相位都不会看到写给 alpha 的 nudge;
4. 两个相位都仍然被记录(隔离改的是递什么,不是留什么)。

回归:`uv run pytest packages/graph-agent/tests` → 1510 passed(基线 1506 + 本次 4 条),零条既有
测试需要改动。四个"看着最像会红"的都不会红,理由各不相同:
`test_batch_item_isolation.py:210` 是相对量断言(item 2 与 item 1 比);
`test_v030_deltachannel_checkpoint.py` 走手搭普通节点而非相位节点;
`test_mvp1_smoke.py:387` 断言在手工合成的 state 上;
`test_gamma2_state_io_red.py:55` 断言的恰恰是 `child_state["messages"] == []`,同方向。

## 已知遗留(明写,不装作解决)

1. **相位内**同源缺陷仍在:本相位一旦被 nudge,它自己后续每一轮也拿不到输入 JSON 块了
   (判据仍是「有没有 HumanMessage」这个代理指标)。隔离修不了这条,需要换判据(按标记判断
   "这一次调用是否已经投过输入"),另立一条。
2. `flow.working_memory` 是**第二条**跨相位通道(`core/state.py:223-229` 的
   `_FLOW_DICT_MERGE_FIELDS` 含 `working_memory`;`middleware/exit_control.py:152-157` 的 planning
   闸读它),engine 源码内无任何一处在相位边界重置它。是否同样隔离需要单独裁决——这次不动。
3. 「隔离之后下游相位不再照抄上游字段」在机制上必然,但**要真跑一次
   `story-deconstruction-v3-lab` 才算坐实**。本 PR 只交离线证据。
