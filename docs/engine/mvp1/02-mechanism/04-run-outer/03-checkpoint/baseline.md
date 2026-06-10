---
module: 02-mechanism/04-run-outer/03-checkpoint
doc: baseline
status: audited-ready（WS-E7 回写:run/thread 级 checkpoint 已接,AGENT 内层经 NamespaceCheckpointer 挂共享 base,graph iterate 内 agent namespace 保留 iter{k};Engine resume_skill 已消费 checkpoint_id/checkpoint_ns latest;data 无 delta reducer、Studio resume UI/HTTP 后续）
---

# 03-checkpoint — Baseline(当下代码实现逻辑)

> **Scope**: 共享 checkpointer base 的现状:`checkpointer.py`(backend 工厂)、`assemble_graph` 的 `builder.compile(checkpointer=)` 接线、AGENT 内层 namespace wrapper、graph iterate 与 agent namespace 组合、`state.py` 的 `data`/`messages` 通道(messages 已用 DeltaChannel,data 还是普通字段)。
> **现状一句话**:checkpoint 已接到 **run/thread 级 + AGENT 内层 namespace**——`resolve_checkpointer("auto")` 造 saver(memory/sqlite/postgres),`assemble_graph` 传给 `builder.compile(checkpointer=)`,AGENT `create_agent(..., checkpointer=NamespaceCheckpointer(base,"agent:<phase>"))` 复用同一 base,`graph.invoke` 用同一 `thread_id`,LangGraph 在 thread 内按 namespace 存档。graph-level iterate 内的 AGENT checkpoint 会保留 `iter{k}.agent:<phase>` 组合 namespace。WS-E7 后,Engine `resume_skill` 可按 `checkpoint_id` 或 `checkpoint_ns` latest 选择 checkpoint 并重 invoke;`data` 黑板通道仍无 delta reducer(每 super-step 全量)。

## UI/UX
N/A。

## 前端逻辑
N/A —— studio 的 [Resume]/HITL UI 经 `03-api-contract` 消费,不直接调本域。

## 后端功能

### 1. checkpointer 工厂(checkpointer.py)
`checkpointer_context(..., backend="memory")`(`checkpointer.py:39`)按 backend 造 LangGraph checkpointer:memory(`:46`)/ sqlite(`_resolve_sqlite_conn_str` `:30`)/ postgres(连接串必填 `:24`)。`resolve_checkpointer("auto")` 读环境变量选 backend(`runner.py:663` 调)。
> **checkpointer(LangGraph)第一次出现需定义**:thread 级状态存档器——每个 super-step(一个 node 执行)后存一份 state,支持 `get_state_history` 回溯 + resume。

### 2. 接线:run 路径
`_run_v030_skill_dict`(`runner.py:623`)`active_checkpointer = resolve_checkpointer("auto")`(`:663`)→ `assemble_graph(..., checkpointer=)`(`:667`)→ `builder.compile(checkpointer=checkpointer)`(`graph_assembler.py:151`)→ `graph.invoke(config={"thread_id": run_id})`。**整 run 一个 thread**;LangGraph 在 thread 内按 super-step 自动存。

### 3. state 通道(state.py):messages 已 delta,data 未
`WorkflowState`(`state.py:203` 区)两通道:
- `data: BusinessData`(`:212`)——业务黑板,**普通字段、无 delta reducer**(每 super-step 全量存,大 N 时是 O(N²) 隐患)。
- `messages: Annotated[list, DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)]`(`:214`)——**已用增量快照通道**(每 50 步一快照),归 `08-messages-state`。

### 4. WS-E5:AGENT 内层 namespace + graph iterate 组合
`graph_assembler.py` 现有 `NamespaceCheckpointer(base_checkpointer,target_ns)` 包装 AGENT 内层 saver。外层 graph 传入显式 checkpointer 时,AGENT 内层不另起独立 saver,而是把同一个 base 作为 `base_checkpointer` 包装,目标 namespace 为 `agent:<phase_id>`。同一 `thread_id` 下可分别查询外层 `checkpoint_ns=""` 与 AGENT 内层 `checkpoint_ns="agent:<phase>"`。

graph-level iterate 调整为在每轮 graph invoke 期间设置一个进程内 context marker(`active_outer_ns`),值为 `iter{k}`。AGENT 内层 `NamespaceCheckpointer` 写 checkpoint 时把当前 outer namespace 与 agent namespace 组合为 `iter{k}.agent:<phase>`;因此 iterate round 与 agent/phase scope 不互相覆盖。该 marker 在 batch/loop 每轮结束后 reset,避免后续非 iterate AGENT checkpoint 泄漏前一轮 namespace。

## API
- `checkpointer_context(*, backend="memory", ...)`(`:39`)/ `resolve_checkpointer(spec)`——造 saver。
- `assemble_graph(..., checkpointer=)`——外层 base 注入点(归 `03-assemble`)。
- `graph_assembler.py:NamespaceCheckpointer`——AGENT 内层 namespace wrapper;写入 base 时按 `checkpoint_ns` 分层,读取 wrapper tuple 时还原内层视角。
- `graph_assembler.py:active_outer_ns`——graph iterate 运行期间的 namespace 组合 marker,只用于 checkpoint namespace 组合,不写入 `WorkflowState.data`。
- `runner.py:resume_skill`——Engine 进程内 resume API;支持 `checkpoint_id` 精确选择、`checkpoint_ns` latest 选择、`context_overrides`、HITL `ToolMessage` 注入。

## Data Model / State
state schema `WorkflowState`(归 `data-contracts`):`data`(blackboard,本域外层管)/`messages`(内层,归 `08-messages-state`)。checkpoint 存的是整个 WorkflowState 快照。

## 当前边界(这个模块现在不是什么)
- **Engine resume API 已有,但不是完整 Studio 产品**:外层/AGENT/graph-iterate+AGENT checkpoint 可按 namespace 区分,`resume_skill` 已可消费 checkpoint;但 Studio `resume_run` HTTP route、checkpoint 选择 UI 与用户态错误展示仍未闭环。
- **内层 AGENT 已挂共享 base,但没有 messages compaction**:AGENT `create_agent` 已复用外层 base checkpointer 并写 `agent:<phase>` / `iter{k}.agent:<phase>` namespace;messages summarization/sidecar 仍归 `08-messages-state` 后续。
- **data 无 delta**:`data` 通道每 super-step 全量(mvp1 要补 delta reducer)。
- **持久化边界(现状证据)**:`PhaseExecutor.__getstate__`(`phase_executor.py:82`)fail-fast 禁 pickle `_phase_executor`——runtime 对象(callback/runtime/compiled graph)不得入可持久化 checkpoint state(legacy 路线约束,mvp1 沿用,见 alignment §8 #4)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 粒度 | run/thread 级 + AGENT 内层 namespace;graph iterate 内 agent checkpoint 保留 `iter{k}.agent:<phase>` | 节点级 + 嵌套 `checkpoint_ns`(图⊃phase⊃iterate⊃agent) + resume 产品闭环 |
| 内层 agent loop | 经 `agent:<phase>` 挂同一 base;在 graph iterate 内组合为 `iter{k}.agent:<phase>` | HITL/resume 可从内层对话断点续跑 |
| data 通道 | 普通字段全量(`state.py:212`) | delta reducer(O(N) 非 O(N²)) |
| 有界 accumulator | 无 | rolling_summary + recent_window + artifact_refs |

> **验"是否按 mvp1 改了"**:① 同一 base/thread 下外层 `""` 与 AGENT `agent:<phase>` history 是否可区分;② graph iterate 内 AGENT checkpoint 是否保留 `iter{k}.agent:<phase>`;③ `resume_skill` 能从 checkpoint_id/checkpoint_ns 恢复并应用 overrides/HITL response;④ 1000 遍 loop checkpoint 总体积是否 O(N)(仍未满足,data delta 后续);⑤ Studio HTTP/UI resume 是否闭环(仍未满足)。

## 读代码主路径提示
`resolve_checkpointer`(`checkpointer.py`)→ `runner.py:663` 接线 → `graph_assembler.py:151` compile 传入 → state 通道 `state.py:212/214`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `05-run-inner/08-messages-state`(内层 messages,双向)· `02-iterate`(图级 loop)· `data-contracts`(state schema)· `03-api-contract`(resume C2)
