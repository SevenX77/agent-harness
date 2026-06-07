---
doc: state-checkpoint-storage-model
status: 留底（轴① 决策档案;实现 SSOT 已迁 03-checkpoint/08-messages-state/02-iterate;保留递归拓扑 + CK1-6 + D-test 深度细节备锁前回填）
owns: 引擎执行的【嵌套拓扑 + checkpoint 一套 base + 存储纪律(delta/compact)】跨关注点权威模型
related:
  - ../01-agent-loop/mvp1-alignment.md（agent loop = 内层图,经 ns 挂同一 checkpointer）
  - ../10-iteration-and-resume/mvp1-alignment.md（iterate / 图级 loop / resume = 本模型的应用)
  - change-invalidation-model.md（互补:本篇管"存什么/存多少",那篇管"何时失效")
  - uncovered-areas.md（#3 checkpointer×middleware = 本模型的头号 D-test)
ground_truth:
  - packages/graph-agent（file:line 已核）
  - langgraph 1.2.2（checkpoint_ns / get_state_history / Send 已确认存在）
---
> 🔖 **本文 = 轴① 决策留底(workflow archive),非实现 SSOT。** 实现真相已迁入 [`03-checkpoint`](../../02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md)(共享 base / blackboard)+ [`08-messages-state`](../../02-mechanism/05-run-inner/08-messages-state/mvp1-alignment.md)(内层 messages)+ [`02-iterate`](../../02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md)(图级 loop=B / CK3)。正式模块 = 现状 SSOT(条理化版);本文保留**更深的决策细节**(递归拓扑图 §2.1、delta/compact 矩阵 §2.4、durability §2.5、CK1-6 全集 §4、7 条 D-test §5、6 段 PM 原话 §3)作锁前回填备查。
<!-- 核对进度:已迁 7 块 / 未迁 7 块 / 2026-06-04 -->

~~# State / Checkpoint / Storage 模型~~ → ✅[已迁入](../../02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md#1-定义)

> **Tier**: engine 执行核心 | **Owns**: 执行嵌套拓扑 · checkpoint 唯一 base · 存储去体积/压缩纪律 | **Status**: drafted | **Related**: 01-agent-loop · 10-iteration · change-invalidation-model | **决策记录**: ../../../design/agent-loop-planA-create-agent-migration.md

~~## 1. 定义~~ → ✅[已迁入](../../02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md#1-定义)

引擎里所有"执行重复 + 状态续跑"的形态——agent loop(模型↔工具)、节点 iterate、subgraph、图级 loop——都收敛到**一个 LangGraph thread checkpointer,靠 `checkpoint_ns` 嵌套分层**(唯一 base)。存储靠两条正交纪律兜底:**delta**(去体积/存储表示)+ **compact**(内容压缩/有界化);纪律按**"连乘后的大 N × state 增长"**施加,无固定次要层。

<!-- ⚠️ 未迁入（正式 checkpoint/messages/iterate 仅摘要承载，缺递归拓扑、delta/compact 矩阵、durability、完整 PM 原话、CK 决策与 D-test 细节） → 应归入:02-mechanism/04-run-outer/03-checkpoint + 02-mechanism/05-run-inner/08-messages-state -->
## 2. 数据流 / 机制

<!-- ⚠️ 未迁入（正式 checkpoint/messages/iterate 仅摘要承载，缺递归拓扑、delta/compact 矩阵、durability、完整 PM 原话、CK 决策与 D-test 细节） → 应归入:02-mechanism/04-run-outer/03-checkpoint + 02-mechanism/05-run-inner/08-messages-state -->
### 2.1 执行嵌套拓扑(递归,尺度无关)

```
thread(唯一 checkpointer)
└ 图 G(StateGraph(WorkflowState);phase=节点=super-step,graph_assembler.py:106-151)
   ├ phase(LOGIC)        super-step,存 G 的 blackboard(WorkflowState.data)
   ├ phase(AGENT)        super-step
   │    └ agent loop = create_agent 内层图,ns="<id>/agent",每 model/tool 步存 messages(AgentState)
   ├ phase(SUBGRAPH) → 嵌套图 G'(递归:G' 内部同规则,ns="<id>")
   └ 任意 phase/子图 + iterate×N → N 遍,每遍 ns="<id>/iter{k}"
```
- **subgraph 就是一张图**;循环子图 N 次 = 外层把它跑 N 遍。
- **图级 loop**(整图自循环 N 次):见 2.3(引擎包 loop-body)。
- 每层只 checkpoint **它自己的 state**:agent loop 层 = messages;phase/iterate/图层 = blackboard。数据天然按层分。

~~### 2.2 唯一 base + checkpoint_ns(含 agent loop)~~ → ✅[已迁入](../../02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md#2-数据流--机制)

- **唯一 checkpointer**:外层 `builder.compile(checkpointer=...)`(graph_assembler.py:151)。所有嵌套层**经 `checkpoint_ns` 挂进同一个 saver**,不另起内层 saver 实例。langgraph 1.2.2 的 `checkpoint_ns` 提供嵌套命名空间,`get_state_history` 提供历史寻址。
- **phase=super-step**:节点级/debug 续跑是 LangGraph 原生(每 super-step 一存)。
- **agent loop 也 checkpoint(关键,纠正前稿)**:agent loop 经 `ns="<id>/agent"` 入同一 base,每 model/tool 步存档 → **HITL/interrupt/mid-conversation 续跑成立**。证据:引擎用 LangGraph `interrupt()`(`cognitive_flow.py:33` import、`:95` `_interrupt_fn or interrupt`、`:292` attended `interrupt_fn(payload)`、`:300` `source="human_interrupt"`),而 `interrupt` 依赖 checkpoint。命名空间隔离正好解掉"内层 checkpointer 污染外层"的顾虑(uncovered-areas #3)。
- **resume 寻址**:`resume_run(run_id, from=<node_id>|<node_id>:<iter>, context_overrides?)` → `get_state_history` 列档 → 选 `checkpoint_id`(+`checkpoint_ns`)→ `update_state` 套 overrides / 注入 `ToolMessage`(HitL)→ 带该 checkpoint 重 `invoke`。

~~### 2.3 图级 loop = B(引擎包 loop-body)~~ → ✅[已迁入](../../02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md#2-数据流--机制)

引擎是 **DAG-only**(编译期无环校验 `[F-v3-graph-phase-cycle]`,12-compile-runtime-flow),用户**画不出回边**。图级 loop 由**引擎注入**:把整张 DAG 当循环体、套一个 loop 控制器,**一次 LangGraph 执行 + 引擎注入回边**,每遍 `ns="iter{k}"`,全在**一个 thread**。
- 否决 A(runner 外层 `for: invoke` N 次 + 各遍独立 sub-thread):那不是一套 base,跨遍 resume 成 runner 的活。
- 印证:"最顶层图自循环 N 次"没有父图驱动,必须有驱动者 → 引擎把它降格成"被循环的体" = 与 subgraph-loop 同构。

<!-- ⚠️ 未迁入（正式 checkpoint/messages/iterate 仅摘要承载，缺递归拓扑、delta/compact 矩阵、durability、完整 PM 原话、CK 决策与 D-test 细节） → 应归入:02-mechanism/04-run-outer/03-checkpoint + 02-mechanism/05-run-inner/08-messages-state -->
### 2.4 存储纪律:delta vs compact(两条正交线)

| | delta(去体积) | compact(压缩/有界) |
|---|---|---|
| 本质 | checkpoint 存储表示:存增量+周期快照,不每次全拷贝 | 内容缩减:大块换摘要,全文旁挂 sidecar/artifact |
| 救什么 | 磁盘/DB 体积 | live token(上下文窗口+成本)& 状态无界增长 |
| 有损? | 无损 | 有损/外移 |

**施加位置 = 连乘大 N**:某层 checkpoint 数 = 根→该层路上**每个 loop 乘数的连乘**;need = checkpoint 数 × state 增长。**无固定次要层**——大 N 在哪层(节点 iterate / 子图循环 / 最外层图循环)就压哪层;一层只有"O(1) 遍且 state 有界"才真次要。

按"层存什么"分治:

| 增长源 | 在哪层 checkpoint | delta | compact |
|---|---|---|---|
| **messages**(对话) | agent loop(每步;长对话/多步) | `DeltaChannel`(`state.py:214` messages 已有,snapshot_frequency=50) | summarization middleware(超窗才触发)+ sidecar 存全文 |
| **blackboard accumulator**(跨遍累积) | iterate / 图级 loop / 子图循环 | `data` 通道补 delta reducer(现为普通字段,每 super-step 全量,**待补**) | 有界 accumulator:`{rolling_summary, recent_window[K], artifact_refs[]}`,全文 → artifact 落盘 |

**delta 的 snapshot 频率 = 平衡旋钮(承 PM)**:纯 delta 不利于断点恢复——重建第 X 步的 state 要从上一个 snapshot 回放所有 diff。做法 = **每 N 步存一次全量 snapshot、中间 N-1 步存 diff**(messages 现 `snapshot_frequency=50`)。N 偏小 = snapshot 多 = 体积大;N 偏大 = 回放成本高、resume 慢。**最优 N 是效率平衡点,需实测定**(随 backend / state 大小 / resume 频率变化);messages 与 blackboard 两条 delta 通道各自调,与 §2.5 durability 联动。

<!-- ⚠️ 未迁入（正式 checkpoint/messages/iterate 仅摘要承载，缺递归拓扑、delta/compact 矩阵、durability、完整 PM 原话、CK 决策与 D-test 细节） → 应归入:02-mechanism/04-run-outer/03-checkpoint + 02-mechanism/05-run-inner/08-messages-state -->
### 2.5 durability 旋钮

有 checkpointer 时 LangGraph 按 super-step 存档;**粒度/持久化时机由 durability 模式控制**,取值需 D-test:HITL 至少需"中断点 + phase 边界"存;mid-loop 崩溃恢复需更密。它直接决定大 N 场景的 checkpoint 总量与写盘开销。

<!-- ⚠️ 未迁入（正式 checkpoint/messages/iterate 仅摘要承载，缺递归拓扑、delta/compact 矩阵、durability、完整 PM 原话、CK 决策与 D-test 细节） → 应归入:02-mechanism/04-run-outer/03-checkpoint + 02-mechanism/05-run-inner/08-messages-state -->
## 3. 设计决策基础(用户原话)

> 极限场景:"写一部1000章的小说, 或者分析拆解一部1000章的小说转成剧本"

> 递归/尺度无关:"如果我是设定最外层loop 1000次呢也是有可能的呀. 而且如果中间N=1000的是一个subgraph呢? 这个subgraph不就等于他的外层图循环1000次吗?"

> HITL 必须 checkpoint agent loop(推翻"内层不 checkpoint"):"agent loop现在不做checkpoint, 那哪来的人类打断对话后继续这个功能? 我和外层langgraph对话个啥? 都没有llm调用"

> 图级 loop 选 B:"我也选B"

> 无固定次要层(质疑"外层少数 phase 不用 delta/compact"):"我问这个问题的原因是你说'外层少数 phase' 所以不需要delta和compact?"

<!-- ⚠️ 未迁入（正式 checkpoint/messages/iterate 仅摘要承载，缺递归拓扑、delta/compact 矩阵、durability、完整 PM 原话、CK 决策与 D-test 细节） → 应归入:02-mechanism/04-run-outer/03-checkpoint + 02-mechanism/05-run-inner/08-messages-state -->
## 4. 决策 + 动机

| ID | 决策 | 动机 |
|---|---|---|
| CK1 | 唯一 base + `checkpoint_ns` 嵌套,不另起内层 saver | 统一 resume(`get_state_history` 全局寻址);engine-prompt 铁律"不要两套" |
| CK2 | **agent loop 也经 ns 入 checkpoint**(纠正前稿"内层不 checkpoint") | 否则无 mid-conversation HITL;`interrupt()` 依赖 checkpoint(cognitive_flow.py:292) |
| CK3 | 图级 loop = **B(引擎包 loop-body,一 thread+ns/iter)** | DAG-only 下唯一"一套 base"形态;与 subgraph-loop 同构;否决 runner 外 N invoke |
| CK4 | delta/compact 跟**连乘大 N**,无固定次要层 | 外层图循环 1000× 时,"外层 phase"=3×1000 累积档,正是主战场 |
| CK5 | messages 与 blackboard **分治**(DeltaChannel/summarization vs delta/有界+artifact) | 两者增长源/兜底机制不同,挂错层白做 |
| CK6 | compact 是 1000 章的**可行性前提**,非优化 | 不 compact 上下文 O(N²) 且爆窗口(第1000章塞999章=超所有模型);compact 后 O(N) |

<!-- ⚠️ 未迁入（正式 checkpoint/messages/iterate 仅摘要承载，缺递归拓扑、delta/compact 矩阵、durability、完整 PM 原话、CK 决策与 D-test 细节） → 应归入:02-mechanism/04-run-outer/03-checkpoint + 02-mechanism/05-run-inner/08-messages-state -->
## 5. 测试关键点

1. **HITL 续跑**:agent loop 内 `interrupt()` → resume 从**对话中断点**续(不是 phase 起点重跑)。
2. **B 图级 loop**:声明 GRAPH.md 图级 iterate → 引擎包 loop-body(**一个 thread + ns=iter{k}**),而非 N 次独立 invoke / 独立 sub-thread。
3. **嵌套 ns 寻址(D-test,头号风险,uncovered #3)**:子图 / agent loop 在父 thread 下按 `checkpoint_ns` 逐 super-step 存,`get_state_history` 能跨 ns 寻址续跑——在 langgraph 1.2.2 + GatewayChatModel 下成立。
4. **blackboard delta**:1000 遍 loop 的 checkpoint **总体积 O(N) 非 O(N²)**。
5. **有界 blackboard**:喂第 k 遍的上下文**体积恒定(不随 k 增)**,全文在 artifact 可取。
6. **messages summarization**:长 agent loop messages 被摘要、全文进 sidecar;predict mock 仍能模拟该形态(承 09 G5)。
7. **durability**:选定粒度下,HITL 可续 + checkpoint 总量可控。

~~## 6. 涉及 region / platform~~ → ✅[已迁入](../../02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md#7-涉及-region--platform)

engine 全权拥有机制;studio 侧 `resume_run` / HITL UI 经 api 契约消费(见 api-engine-studio-contract §4)。

~~## 7. gaps / 待设计(实现属 kiro 实施层)~~ → ✅[已迁入](../../02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md#8-gaps--待设计)

1. `data`(blackboard)通道 delta reducer 形态(append-accumulator 友好)。
2. `accumulate.merge` 增 `rolling-summary` 模式(有界 accumulator)。
3. summarization middleware + sidecar **从 legacy 死簇搬回 live**(现搁浅 `phase_nodes/llm_phase_node.py:809` / `phase_executor.py`,assemble_graph 路径无 compaction)。
4. durability 取值(D-test 3/7)。
5. 引擎包 loop-body 的 compile 实现(DAG-only 下注入回边 + 计数 + accumulate)。

~~## 交叉引用(链接,不复制)~~ → ✅[已迁入](../../02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md#交叉引用-链接-不复制)
- 01-agent-loop(agent loop 经 ns 入 checkpoint + summarization middleware 边界)
- 10-iteration §3/§4(iterate / 图级 loop / resume = 本模型应用;§4 引本篇为 SSOT)
- api-engine-studio-contract §4(resume 寻址契约)
- change-invalidation-model(失效,与本篇互补)
- uncovered-areas #3(checkpointer×middleware D-test)
