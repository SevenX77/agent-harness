---
module: 02-mechanism/06-seam/02-observability
doc: baseline
status: drafted（WS-E1-io + WS-E4 runtime 后:36 类 typed event + callbacks;TracingMiddleware tool hook 已发 ToolCallEvent;V4 InputDispatch/BlackboardReduce/InputFileInjected runtime emit 已接入）
---

# 02-observability — Baseline(当下代码实现逻辑)

> **现状一句话**:把"发生了什么"以 **36 类 typed `CallbackEvent`** 发出(`callbacks/events.py`,`_EventBase` + `event_type` Literal 判别)——经回调 + `trace.jsonl` 落盘 + WS。WS-E2 已让 `TracingMiddleware` 在 tool hook 中对 `ToolMessage` 结果发 `ToolCallEvent`,并由 `factory.py` 向 Tracing 槽传 callbacks;WS-E1-io 已在声明式 file input 成功注入时发 `InputFileInjectedEvent`;WS-E4 runtime 已让 phase input dispatch 与声明式 accumulate/reducer 发出 `InputDispatchEvent` / `BlackboardReduceEvent`。LLM hook 深覆盖、`parent_node_id` 真实关联外层 phase 仍是后续工作。**它是事件流,不是"所有消息"**。

## UI/UX
N/A —— trace 被 studio trace-inspector 消费(前端挂载归 studio)。

## 前端逻辑
N/A。

## 后端功能

### 1. 事件 schema(events.py)
`_EventBase` + **36 个** event 子类(`PhaseStartEvent`/`PhaseEndEvent`/`LLMCallEvent`/`ToolCallEvent`/… 各带 `event_type: Literal[...]` 判别字段)。判别联合(discriminated union),SSOT = `callbacks/events.py`。

WS-E4 schema-only 已落地:
- `LLMCallEvent` / `ToolCallEvent` 支持微观拓扑字段 `parent_node_id: str | None = None`、`node_type: str | None = None`；旧构造方式默认 `None`。
- 3 个 V4 边操作事件已定义并进入 `CallbackEvent` union、`events.__all__`、默认 `Callback.on_event` typed-only 识别集合:
  - `BlackboardReduceEvent`
  - `InputDispatchEvent`
  - `InputFileInjectedEvent`
- `_TraceJsonlSink` 无需专门改动；现有 `model_dump(mode="json")` 通用路径可把新增 typed events 写成一行一 JSON object。

### 2. callbacks 系统
`callbacks/`:`emit.py`(发射)、`tracing.py`(trace 收集)、`serialize.py`(序列化)、`metrics.py`(指标)、`logging_cb.py`、`base.py`。事件经 `event_subscriber` 回调 + `trace.jsonl`(落盘 SSOT,落点 `<workspace>/runs/<run_id>/`)+ WS。
> **CallbackEvent 第一次出现需定义**:引擎执行过程中发出的 typed 事件(phase 起止、LLM 调用、工具调用…),供观测/trace,**不是**对话 messages、也不是返回的 RunResult。

### 3. TracingMiddleware tool emit 现状
`TracingMiddleware` 已实现 sync/async tool hook:`wrap_tool_call` / `awrap_tool_call` 调 handler 后原样返回结果;当结果是 `ToolMessage` 时,构造 `ToolCallEvent` 并向 callbacks 发出。当前事件字段来自既有 schema:
- `phase_name`:当前 phase。
- `tool_name`:ToolCallRequest 的 tool name。
- `args`:ToolCallRequest 的 args;非 dict 时包成 `{"args": raw}`。
- `result`:ToolMessage content 的字符串/JSON 摘要。
- `duration_ms`:hook 内 `perf_counter` 测得耗时。
- `parent_node_id=None`:WS-E2 没有新增父节点定位来源。
- `node_type="tool"`:使用既有 `ToolCallEvent` 字段。

callback 派发失败只记录 warning,不破坏工具执行。该实现只记录 tool hook;LLM hook 深覆盖、trace.jsonl 端到端覆盖、`parent_node_id` 真实关联外层 phase 仍未在 WS-E2 完成。有些事件内嵌内容快照(`LLMCallEvent.messages`、`CompactionEvent.content_ref`)= 为 trace 复制,不拥有消息状态。

### 4. 边操作事件现状(节点间 dot 操作,源 11-io)
"节点间操作"(上节点 end→下节点 start 之间)已有 typed event schema:`ArtifactSavedEvent`(io.outputs artifact 落盘)、`CompactionEvent`(截断/摘要)、`BlackboardReduceEvent`、`InputDispatchEvent`、`InputFileInjectedEvent`。
- `InputFileInjectedEvent` 已在 runtime_config import binding 输入成功注入普通 blackboard 后发出;事件包含 `from_phase`、`to_phase`、`changed_keys`、`blackboard_snapshot`、`file_ref`、`target_field`。该发射点位于 graph-exec/io 接线,不是 Studio DTO。
- `InputDispatchEvent` runtime emit 已接入 `graph_assembler.py:_wrap_phase_runtime_node` 返回的节点入口拦截器:phase 执行前按 `io.inputs.properties` 从 business blackboard 计算 `dispatched_keys`/`changed_keys`,携带 dispatch 时的 `blackboard_snapshot`,经通用 callbacks/event sink 发出并写入 `trace.jsonl`。非 iterate 执行 `branch_index=None`;phase/graph iterate 执行期间由 runtime contextvar 写入稳定的 1-based `branch_index`。
- `BlackboardReduceEvent` runtime emit 已接入声明式 loop accumulate:每次 `_merge_accumulator` 后、`StateManager.update_business(... accumulate.var=acc)` 写回后发出,携带声明的 `accumulate.merge`、`changed_keys=[accumulate.var]` 与操作后的 blackboard snapshot。engine 不计算 authoritative before/after diff;OB5 仍由 consumer 用 snapshot 近似。

## API
- 事件 schema:`_EventBase` + `event_type` 判别(`events.py:42`)。
- emit 机制 + `trace.jsonl` 落盘 → `03-api-contract`(事件协议)。

## Data Model / State
36 类 `CallbackEvent`(`events.py`);`trace.jsonl` 一行一 event。不拥有 messages(归 `08-messages-state`)/ RunResult(归 `data-contracts`)。

## 当前边界(这个模块现在不是什么)
- **不是"所有消息"**:事件(发生了 X)≠ messages(对话)≠ RunResult(返回)。
- **Tracing 中间件只完成 tool hook 最小覆盖**:尚未声明 LLM hook 深覆盖、trace.jsonl 端到端写入、真实 `parent_node_id` 关联已经完成。
- **subagent lifecycle 事件缺(A2)**:子代理 start/end/error 未补(与 `07-subagent` 协同)。
- **V4 边操作事件已部分 runtime 接入**:`InputDispatchEvent`、`BlackboardReduceEvent`、`InputFileInjectedEvent` 已有真实 runtime emit;reducer authoritative before/after diff、真实 `parent_node_id` 关联仍未完成。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 发射点 | TracingMiddleware tool hook 已发 `ToolCallEvent`;LLM hook 深覆盖仍待后续 | 迁到 Tracing 中间件且覆盖不减 |
| subagent 事件 | 缺(A2) | 补 start/end/error |
| V4 trace | 现 36 类；微观拓扑字段已在 `LLMCallEvent`/`ToolCallEvent` schema；`InputDispatchEvent`、`BlackboardReduceEvent`、`InputFileInjectedEvent` runtime emit 已接入 callbacks + `trace.jsonl` | 接入真实微观/边操作 emit；Prompt 三视图已满足；reducer 前后态 diff 维持前端近似 |

> **验"是否按 mvp1 改了"**:① 迁到 create_agent/Tracing 中间件后现有 LLMCallEvent/ToolCallEvent 覆盖不减;② 微观事件 `parent_node_id` 正确关联外层 phase;③ trace.jsonl 一行一 event、predict trace usage 归零。

## 读代码主路径提示
事件 schema `callbacks/events.py`(36 类)→ callbacks `emit/tracing/serialize/metrics.py` → Tracing tool hook `middleware/tracing.py` / runtime edge emit `core/graph_assembler.py:_wrap_phase_runtime_node`、`_build_loop_iterate_phase`、`_run_graph_loop_iterate` → trace 落点 `<workspace>/runs/<run_id>/trace.jsonl`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `02-middleware`(Tracing 槽,双向)· `07-subagent`(lifecycle)· `03-api-contract`(事件协议)· `data-contracts`
