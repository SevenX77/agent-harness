---
module: 02-mechanism/04-run-outer/03-checkpoint
doc: mvp1-alignment
status: audited-ready（**U5 单元锁定 2026-06-05**;WS-E5/E7 回写:外层 super-step checkpoint + WorkflowState.messages DeltaChannel + AGENT namespace checkpoint + Engine resume_skill 已 live;data delta/compaction/Studio resume 产品仍待实现;文件未 FROZEN）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行外层）
---

# 03-checkpoint — 机制 B · 外层状态持久化 + 共享 base

> **Tier**: 机制层 B · 运行·外层(尺度无关) | **Owns**: **共享 checkpointer base**(建外层,经 `checkpoint_ns` 内外层共用)· 外层 blackboard 存储/delta/有界 · durability | **现状**: A 摘要成段;records 深度未迁完 | **Related**: `05-run-inner/08-messages-state`(内层 messages,双向)· `02-iterate`(图级 loop)· `data-contracts`(state schema)· `03-api-contract`(resume)

## 1. 定义
checkpoint = **一个共享 base**(LangGraph thread checkpointer,**建在外层 `builder.compile(checkpointer=)`**),节点/iterate/图级/**内层 agent loop** 都经 `checkpoint_ns` 挂同一个 saver(不另起内层 saver)。WS-E5 后,AGENT 内层已用 `NamespaceCheckpointer` 写 `agent:<phase>` / `iter{k}.agent:<phase>`;WS-E7 后,Engine `resume_skill` 已能按 checkpoint_id/checkpoint_ns 消费这些 checkpoint。**两层各管各 state**:外层这边管 **blackboard**(`WorkflowState.data`);内层 messages 在 `08-messages-state`。

## 2. 数据流 / 机制
本域承接共享 checkpoint 的**外层/base 部分**(模型经多轮 PM 收敛)。

> **现状 vs 目标(铁律:不得把目标当现状)**:**live 今天已有**——① 外层图 super-step checkpoint(`resolve_checkpointer("auto")` → `assemble_graph(checkpointer=)` → `builder.compile(checkpointer=)`);② `WorkflowState.messages` 的 `DeltaChannel(snapshot_frequency=50)` 通道(`state.py:214`);③ AGENT 内层 `NamespaceCheckpointer` 共享 base 并写 `agent:<phase>` / graph iterate 内 `iter{k}.agent:<phase>`;④ `runner.py:resume_skill` 可按 `checkpoint_id` 或 `checkpoint_ns` latest 恢复,并支持 context overrides / HITL ToolMessage 注入;⑤ `interrupt()` 原语(`cognitive_flow.py:292`)。**仍未 live**:blackboard data delta reducer、messages compaction、durability 调参产品化、Studio HTTP/UI resume。

**目标执行嵌套拓扑(递归,尺度无关;部分 live)**——所有"执行重复 + 状态续跑"形态(agent loop / iterate / subgraph / 图级 loop)收敛到**一个 thread checkpointer**,靠 `checkpoint_ns` 嵌套分层:
```
thread(唯一 checkpointer,builder.compile checkpointer= → graph_assembler.py:151)
└ 图 G(StateGraph(WorkflowState);phase = 节点 = super-step)
   ├ phase(LOGIC)      super-step,存 blackboard(WorkflowState.data)
   ├ phase(AGENT)      └ agent loop = create_agent 内层图,ns="<id>/agent",每 model/tool 步存 messages(归 08-messages-state)
   ├ phase(SUBGRAPH) → 嵌套图 G'(递归:G' 内同规则,ns="<id>")
   └ phase + iterate×N → N 遍,每遍 ns="<id>/iter{k}"
```
- **subgraph 就是一张图**;循环子图 N 次 = 外层跑它 N 遍。每层只 checkpoint **它自己的 state**(agent loop = messages;phase/iterate/图 = blackboard),数据天然按层分。
- 唯一 base + `checkpoint_ns`:不另起内层 saver;`get_state_history` 全局寻址续跑。

**blackboard 存储纪律(两条正交线)**:
- **delta(去体积,无损)**:`data` 通道补 delta reducer(现为普通字段、每 super-step 全量,**待补**)——存增量 + 周期快照,救磁盘/DB 体积。
- **compact(有界,有损/外移)**:有界 accumulator `{rolling_summary, recent_window[K], artifact_refs[]}`,全文 → artifact 落盘——救 live token & 状态无界增长。
- **施加位置 = 连乘大 N**(某层 checkpoint 数 = 根→该层每个 loop 乘数的连乘 × state 增长):**无固定次要层**,大 N 在哪层就压哪层;一层只有"O(1) 遍且 state 有界"才真次要。
- **delta snapshot 频率 = 平衡旋钮**:每 N 步存全量、中间存 diff(messages 现 `snapshot_frequency=50`);N 小 = 体积大,N 大 = 回放/resume 慢,最优 N 需实测(随 backend/state 大小/resume 频率变)。

**durability 旋钮**:有 checkpointer 时 LangGraph 按 super-step 存档,**粒度/时机由 durability 模式控制**(D-test 定):HITL 至少需"中断点 + phase 边界"存,mid-loop 崩溃恢复需更密;直接决定大 N 场景 checkpoint 总量与写盘开销。

- 图级 loop=B(引擎包 loop-body)的 checkpoint 归 `02-iterate`(双向)。

## 3. 接口契约
`assemble_graph(..., checkpointer=)` 注入(归 `03-assemble`);嵌套 ns 寻址(外层 super-step ↔ 内层 agent step,经 `08-messages-state`);Engine `resume_skill` 选 checkpoint_id / checkpoint_ns latest → `update_state` → re-invoke;Studio HTTP resume 仍归 `03-api-contract` 后续薄接;state schema 归 `data-contracts`。

## 4. 设计决策基础(用户原话)
> 两层各一套(2026-06-03 PM):"checkpoint 不是 in/out 分别单独一套吗?" → 一个共享 base、两层各管各 state(外 blackboard / 内 messages)。
> HITL 必须 checkpoint agent loop:"agent loop现在不做checkpoint, 那哪来的人类打断对话后继续这个功能? 我和外层langgraph对话个啥? 都没有llm调用"
> 极限场景(尺度来源):"写一部1000章的小说, 或者分析拆解一部1000章的小说转成剧本"
> 递归/尺度无关:"如果我是设定最外层loop 1000次呢也是有可能的呀. 而且如果中间N=1000的是一个subgraph呢? 这个subgraph不就等于他的外层图循环1000次吗?"
> 无固定次要层(质疑"外层少数 phase 不用 delta/compact"):"我问这个问题的原因是你说'外层少数 phase' 所以不需要delta和compact?"
> 图级 loop 选 B:"我也选B"

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| CK1 | 唯一 base + `checkpoint_ns` 嵌套,base 建外层(`compile` 时,`graph_assembler.py:151`),不另起内层 saver | 统一 resume(`get_state_history` 全局寻址);engine 铁律"不要两套" |
| CK2 | **agent loop 也经 ns 入 checkpoint**(纠正前稿"内层不 checkpoint") | 否则无 mid-conversation HITL;`interrupt()` 依赖 checkpoint(`cognitive_flow.py:292`)——细节归 `08-messages-state` |
| CK3 | 图级 loop = **B(引擎包 loop-body,一 thread + ns/iter)** | DAG-only 下唯一"一套 base"形态;与 subgraph-loop 同构(归 `02-iterate`) |
| CK4 | delta/compact 跟**连乘大 N**,无固定次要层 | 外层图循环 1000× 时外层 phase 累积档正是主战场 |
| CK5 | blackboard(本域)与 messages(`08-messages-state`)分治 | 两者增长源/兜底不同,挂错层白做 |
| CK6 | compact 是 1000 章的**可行性前提**,非优化 | 不 compact 上下文 O(N²) 爆窗口;compact 后 O(N)——细节归 `08-messages-state` |

## 6. 测试关键点(D-test)
1. **嵌套 ns 寻址续跑**:AGENT namespace checkpoint + Engine `resume_skill` 已有 WS-E5/WS-E7 覆盖;后续仍需 Studio route/UI 与更大规模 durability 实测。
2. **HITL 续跑**:agent loop 内 `interrupt()` → resume 从对话中断点续(非 phase 起点重跑;细节归 `08-messages-state`)。
3. **B 图级 loop**:图级 iterate → 引擎包 loop-body(一 thread + ns=iter{k}),非 N 次独立 invoke/独立 sub-thread(归 `02-iterate`)。
4. **blackboard delta**:1000 遍 loop checkpoint 总体积 O(N) 非 O(N²)。
5. **有界 blackboard**:喂第 k 遍上下文体积恒定(不随 k 增),全文在 artifact 可取。
6. **durability**:选定粒度下 HITL 可续 + checkpoint 总量可控。
7. **内层 create_agent checkpointer**:WS-E5 已改为通过 `NamespaceCheckpointer` 复用共享 base;实现需继续守住 thread_id/state schema/middleware state/ToolMessage 序列化边界,避免 runtime 对象污染 checkpoint。

## 7. 涉及 region / platform
engine 全权;studio 侧 resume_run/HITL UI 经 `03-api-contract` 消费。

## 8. gaps / 待设计
1. `data`(blackboard)通道 delta reducer(append-accumulator 友好)。
2. 有界 accumulator(`accumulate.merge` 加 rolling-summary)。
3. durability 取值(D-test)。
4. **持久化边界硬约束(源 uncovered #3)**:middleware 内 callback/runtime/compiled graph 等对象**不得进入可持久化 state**(只写可序列化标记 + messages);legacy precedent `PhaseExecutor.__getstate__`(`phase_executor.py:82`)fail-fast 禁 pickle `_phase_executor`,正说明 runtime 对象混存 checkpoint 是高风险点。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `05-run-inner/08-messages-state`(内层 messages,**双向:共享 base**)· `02-iterate`(图级 loop)· `data-contracts` · `03-api-contract`(resume C2)
