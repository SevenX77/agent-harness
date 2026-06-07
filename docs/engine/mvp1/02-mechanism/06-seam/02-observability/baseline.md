---
module: 02-mechanism/06-seam/02-observability
doc: baseline
status: drafted（现状对齐 WS-E4 schema-only 实现；36 类 typed event + callbacks；V4 边操作事件 schema/union/export 已落地；内联 emit 待迁 Tracing 中间件；真实 runtime emit 接线仍待后续 WS）
---

# 02-observability — Baseline(当下代码实现逻辑)

> **Scope**: 引擎执行的可观测事件流现状:`callbacks/events.py`(36 类 typed event)、`callbacks/{emit,tracing,serialize,metrics,logging_cb,base}.py`、trace.jsonl 落盘。
> **现状一句话**:把"发生了什么"以 **36 类 typed `CallbackEvent`** 发出(`callbacks/events.py`,`_EventBase` + `event_type` Literal 判别)——经回调 + `trace.jsonl` 落盘 + WS。当前 `LLMCallEvent`/`ToolCallEvent` 的真实 runtime emit 仍是**内联在 `graph_assembler` 手写 loop 里**(见 `01-agent-loop` §3),mvp1 要迁到 Tracing 中间件；WS-E4 只补齐 V4 trace schema 契约。**它是事件流,不是"所有消息"**。

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

### 3. 内联 emit 现状(待迁中间件)
当前 `graph_assembler.py:515-555`(手写 loop 内)内联 emit `LLMCallEvent`/`ToolCallEvent`(见 `01-agent-loop` §3)。mvp1 迁到 Tracing 中间件后**不能让现有事件覆盖变少**。有些事件内嵌内容快照(`LLMCallEvent.messages`、`CompactionEvent.content_ref`)= 为 trace 复制,不拥有消息状态。

### 4. 边操作事件现状(节点间 dot 操作,源 11-io)
"节点间操作"(上节点 end→下节点 start 之间)已有 typed event schema:`ArtifactSavedEvent`(io.outputs artifact 落盘)、`CompactionEvent`(截断/摘要)、`BlackboardReduceEvent`、`InputDispatchEvent`、`InputFileInjectedEvent`。
- `BlackboardReduceEvent` / `InputDispatchEvent` / `InputFileInjectedEvent` 当前是 schema/union/export/default-callback/JSONL contract 已落地；真实 emit 接线尚未实现。
- ⚠️ **缺口**:黑板 reduce、输入分发、文件注入的 runtime 发射点仍未接入；后续归 WS-E2 / graph-exec / io 工作。

## API
- 事件 schema:`_EventBase` + `event_type` 判别(`events.py:42`)。
- emit 机制 + `trace.jsonl` 落盘 → `03-api-contract`(事件协议)。

## Data Model / State
36 类 `CallbackEvent`(`events.py`);`trace.jsonl` 一行一 event。不拥有 messages(归 `08-messages-state`)/ RunResult(归 `data-contracts`)。

## 当前边界(这个模块现在不是什么)
- **不是"所有消息"**:事件(发生了 X)≠ messages(对话)≠ RunResult(返回)。
- **Tracing 中间件还没逻辑**:现内联 emit(`graph_assembler.py:515`),Tracing 槽 no-op(`02-middleware`)。
- **subagent lifecycle 事件缺(A2)**:子代理 start/end/error 未补(与 `07-subagent` 协同)。
- **V4 边操作事件只到 schema contract**:`BlackboardReduceEvent`/`InputDispatchEvent`/`InputFileInjectedEvent` 已能被 typed union、默认 callback、JSONL 和 public contract 消费,但真实 runtime emit 未接。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 发射点 | 内联在手写 loop(`graph_assembler.py:515`) | 迁到 Tracing 中间件(`02-middleware` 槽 4) |
| subagent 事件 | 缺(A2) | 补 start/end/error |
| V4 trace | 现 36 类；微观拓扑字段已在 `LLMCallEvent`/`ToolCallEvent` schema；3 个边操作事件 schema 已落地但 runtime emit 未接 | 接入真实微观/边操作 emit；Prompt 三视图已满足；reducer 前后态 diff 维持前端近似 |

> **验"是否按 mvp1 改了"**:① 迁到 create_agent/Tracing 中间件后现有 LLMCallEvent/ToolCallEvent 覆盖不减;② 微观事件 `parent_node_id` 正确关联外层 phase;③ trace.jsonl 一行一 event、predict trace usage 归零。

## 读代码主路径提示
事件 schema `callbacks/events.py`(36 类)→ callbacks `emit/tracing/serialize/metrics.py` → 现内联 emit 点 `graph_assembler.py:515-555` → trace 落点 `<workspace>/runs/<run_id>/trace.jsonl`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `02-middleware`(Tracing 槽,双向)· `07-subagent`(lifecycle)· `03-api-contract`(事件协议)· `data-contracts`
