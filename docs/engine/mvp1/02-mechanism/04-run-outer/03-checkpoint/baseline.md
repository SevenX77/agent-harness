---
module: 02-mechanism/04-run-outer/03-checkpoint
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；run/thread 级已接,内层未挂、data 无 delta reducer）
---

# 03-checkpoint — Baseline(当下代码实现逻辑)

> **Scope**: 共享 checkpointer base 的现状:`checkpointer.py`(backend 工厂)、`assemble_graph` 的 `builder.compile(checkpointer=)` 接线、`state.py` 的 `data`/`messages` 通道(messages 已用 DeltaChannel,data 还是普通字段)。
> **现状一句话**:checkpoint 已接到 **run/thread 级**——`resolve_checkpointer("auto")` 造 saver(memory/sqlite/postgres),`assemble_graph` 传给 `builder.compile(checkpointer=)`(`graph_assembler.py:151`),`graph.invoke` 用 `thread_id=run_id`,LangGraph 在 thread 内每 super-step 存档。**但内层 agent loop 现在不挂 checkpoint,`data` 黑板通道也还没 delta reducer(每 super-step 全量)。**

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

## API
- `checkpointer_context(*, backend="memory", ...)`(`:39`)/ `resolve_checkpointer(spec)`——造 saver。
- `assemble_graph(..., checkpointer=)`(`graph_assembler.py:88/151`)——注入点(归 `03-assemble`)。

## Data Model / State
state schema `WorkflowState`(归 `data-contracts`):`data`(blackboard,本域外层管)/`messages`(内层,归 `08-messages-state`)。checkpoint 存的是整个 WorkflowState 快照。

## 当前边界(这个模块现在不是什么)
- **只到 run/thread 级**:现状无节点级精准 resume、无嵌套 `checkpoint_ns` 分层。
- **内层不挂**:agent loop 当前不在内层挂 checkpointer(mvp1 要经 `ns="<id>/agent"` 挂同一 base,使 HITL 续跑成立)——归 `08-messages-state`。
- **data 无 delta**:`data` 通道每 super-step 全量(mvp1 要补 delta reducer)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 粒度 | run/thread 级(`runner.py:663`) | 节点级 + 嵌套 `checkpoint_ns`(图⊃phase⊃iterate⊃agent) |
| 内层 agent loop | 不挂 checkpoint | 经 `ns="<id>/agent"` 挂同一 base(HITL) |
| data 通道 | 普通字段全量(`state.py:212`) | delta reducer(O(N) 非 O(N²)) |
| 有界 accumulator | 无 | rolling_summary + recent_window + artifact_refs |

> **验"是否按 mvp1 改了"**:① 1000 遍 loop checkpoint 总体积是否 O(N);② interrupt→人改 context→resume 是否从断点恢复(嵌套 ns 寻址 D-test);③ 内层 agent step 是否在 `ns="<id>/agent"` 下存档。

## 读代码主路径提示
`resolve_checkpointer`(`checkpointer.py`)→ `runner.py:663` 接线 → `graph_assembler.py:151` compile 传入 → state 通道 `state.py:212/214`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `05-run-inner/08-messages-state`(内层 messages,双向)· `02-iterate`(图级 loop)· `data-contracts`(state schema)· `03-api-contract`(resume C2)
