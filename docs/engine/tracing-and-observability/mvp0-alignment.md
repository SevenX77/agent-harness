# tracing-and-observability (engine) — MVP0 Alignment (V0.3.0 graph_skill)

> **Status**: Rewritten by a1 (Codex) for V0.3.0 graph_skill, 2026-05-23
> **Scope**: Runtime / assembly trace event protocol, Agent tool trace, builtin reference reader subagent trace, ambiguity feedback event, async logger, Studio trace payload。
> **配套**: 见 [skill-spec README](../skill-spec/README.md), [execution-runtime alignment](../execution-runtime/mvp0-alignment.md), [state-and-io-contract alignment](../state-and-io-contract/mvp0-alignment.md)。

## V0.3.0 改造摘要

本文件保留 V2.1 MVP0 的历史方向，但其中“运行主线恢复 public callbacks list”的方向已被 Round 32 PR-1 / T3 明确替代：**[SUPERSEDED by V0.3.0 event_subscriber cutover]**。当前源码事实是 Pydantic `CallbackEvent` union + 小写 `event_type` 字符串；public `run_skill()` 暴露 `event_subscriber`，SDK 内部用 event sink 写 `trace.jsonl`。`TraceEventKind` / `AgentTraceEvent` 仍是目标态描述，不是已落地 API。

| 改造点 | 新语义 | 决议来源 |
|---|---|---|
| C14 | 新增 `ambiguity_logged`, `log_ambiguity` 不只是一条普通 `tool_call`, 还要投递业务反馈事件 | [Studio V0.3.0 新需求 #3](../../studio/V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md) |
| C15 | builtin reference reader subagent 使用 `builtin_subagent_enter` / `builtin_subagent_exit`, 与用户 subagent 区分 | [Builtin Modules](../skill-spec/09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名) |
| 改造点 3 | 装配期 reader 失败发 `builtin_subagent_fallback` WARN, 携带 timeout/error/config missing/invalid/local IO 原因 | [Reference 三机制](../skill-spec/08-resource-mechanisms-spec.md#reference-三机制生命周期) |
| T3 | public `callbacks` list 切到 `event_subscriber`; 默认 trace 单写 `<workspace>/runs/<run_id>/trace.jsonl`; phase lifecycle 由 common wrapper 单源发出 | Round 32 PR-1 event_subscriber cutover |

Tracing 不决定业务执行, 只记录真实 runtime / assembly 调用点。任何 trace payload 都必须来自 StateMapper / runtime 已校验数据, 不记录未授权全局黑板。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

Studio TracePanel、Ambiguity Feedback 面板、Canvas 节点状态和 Edge Inspection 都消费本模块输出的结构化事件。Engine 只负责事件协议和投递, 不负责 React 展示。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 React 逻辑。

前端不应推断 phase 生命周期或 reader fallback。它只订阅事件流。当前已落地的 PR E 事件名是小写 typed event: `tool_call` 补工具结果, `ambiguity_logged` 进入 ambiguity 面板, `builtin_subagent_fallback` 标记 reference reader 降级。`NODE_START` / `NODE_END` 仍属于后续目标态。

## 后端功能

### 1. Runtime Callback 与 Trace 事件分发体系恢复 (P1-4)

MVP0 SHOULD 把 trace 接回 graph runtime 主线。T3 后 live API 不再是 public `callbacks` list，而是 `event_subscriber` + 内部 `_CompositeEventSink`。事件应由真实执行点发出, 不是由顶层 `graph.invoke()` 外围猜测。

| 事件 | 触发点 | 必填 payload | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|
| `phase_start` | `_wrap_phase_runtime_node` 调用 LOGIC / SUBGRAPH / Agent 节点前 | `phase_name`, `context={inputs, phase_outputs, scratch}` | context 来自 normalized blackboard | — | 展示节点开始与输入 |
| `phase_end` | `_wrap_phase_runtime_node` 节点返回或异常 finally | `phase_name`, `context={inputs, phase_outputs, scratch}` | response data 翻译为 phase_outputs | — | 展示节点结果 |
| `LLM_CALL_START` | Agent model invoke 前 | `phase_id`, `messages_summary` | prompt 可截断, 不泄漏 secrets | — | 展示模型调用开始 |
| `LLM_CALL_END` | Agent model invoke 后 | `phase_id`, `response_summary`, `usage` | response 可截断 | — | 展示模型响应 |
| `TOOL_CALL_START` | Tool invoke 前 | `phase_id`, `tool_name`, `tool_call_id`, `validated_args` | args 必须是校验后结构 | — | 展示工具调用请求 |
| `TOOL_CALL_END` | Tool invoke 后 | `phase_id`, `tool_name`, `tool_call_id`, `success`, `result_summary` | result 必须可 JSON 化 / 可截断 | `[F-v3-tool-argument-invalid]` | 展示工具调用结果 |
| `SUBAGENT_ENTER` / `SUBAGENT_EXIT` | 用户 subagent graph 进入 / 退出 | `subagent_name`, `target_skill`, `depth` | 只用于用户注册 subagent | `[F-v3-skill-not-registered]` | 展示用户委派边界 |
| `EXCEPTION` | runtime 捕获异常 | `error_code`, `message`, `phase_id` | code 必须是 `[F-v3-*]` | domain-specific | 标红失败 |

事件投递点 SHOULD 靠近 phase wrapper、tool wrapper、model invocation wrapper、subagent wrapper。只包顶层 run 无法满足 Studio Debug。

### 2. AMBIGUITY_LOGGED trace event (C14)

Agent cognitive template 要求规则不清晰时调用 `log_ambiguity`。Runtime MUST 在 `log_ambiguity` tool 成功后追加投递 `AmbiguityLoggedEvent(event_type="ambiguity_logged")`, 不能只发普通 `ToolCallEvent(event_type="tool_call")`。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `phase_name` | string/null | 否 | `None` | 当前 Agent phase, 由 tool ctx 注入 | — | Canvas / TracePanel 定位 |
| `event_type` | Literal | 是 | `ambiguity_logged` | 固定值 | — | 前端路由到 ambiguity 面板 |
| `ambiguity_type` | string | 是 | 无 | 非空; 建议枚举 `rule_gap` / `input_missing` / `conflict` / `other` | `[F-v3-tool-argument-invalid]` | 问题分类 |
| `question` | string | 是 | 无 | 原始模糊问题 | `[F-v3-tool-argument-invalid]` | 问题正文 |
| `decision` | string | 是 | 无 | Agent 采取的保守决策 | `[F-v3-tool-argument-invalid]` | 反馈闭环核心 |
| `reason` | string | 否 | `""` | 可为空; 可截断 | `[F-v3-tool-argument-invalid]` | 决策理由 |
| `related_refs` | list[string] | 否 | `[]` | 从 `@reference:<id>` 提取 | — | 关联资料 |
| `related_protocols` | list[string] | 否 | `[]` | 从 `@protocol:<id>` 提取 | — | 关联规则 |

> 注 (live 行为对齐): 上表 `[F-v3-tool-argument-invalid]` 是**目标态入参校验契约**。当前 live `log_ambiguity` (cognitive/ambiguity.py) 对这些字段以 `str(... or "")` **容错处理**, 不主动抛该码; 字段真正缺失时表现为 `AmbiguityLoggedEvent` 的 Pydantic ValidationError。严格入参校验属后续目标态。

投递顺序:

1. tool wrapper / callback bridge 记录普通 tool lifecycle。
2. `log_ambiguity` 成功写业务记录。
3. `_emit_ambiguity_logged` 经 `callback.on_event(...)` 并列投递 `ambiguity_logged`。
4. Agent loop 继续发 `ToolCallEvent(event_type="tool_call")`，不被业务事件替代；默认 `_TraceJsonlSink` 会把两类事件都写入 `trace.jsonl`。

Studio 需求来源见 [V0.3.0 New Requirements](../../studio/V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md), builtin tools 背景见 [Builtin Modules](../skill-spec/09-builtin-modules-spec.md#按需调取-tools-read_reference--read_example)。

### 3. Builtin Subagent 与 Reference Tools 的 trace 归属 (C15)

Builtin reference reader subagent 与用户 subagent 语义不同。MVP0 MUST 新增 builtin 专属事件, 避免 Studio 把装配期系统预读误认为用户 Agent 委派。

| 事件 | 触发点 | 必填 payload | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|
| `builtin_subagent_enter` | builtin reader 调用前 | `run_id=None`, `phase_name`, `builtin_name`, `payload.reference_ids` | `builtin_name="reference_reader"` | — | 标记系统预读开始 |
| `builtin_subagent_exit` | builtin reader 成功返回 | `run_id=None`, `phase_name`, `builtin_name`, `payload.reference_ids`, `payload.markdown_length` | 输出 markdown 已生成 | — | 标记系统预读成功 |
| `builtin_subagent_fallback` | builtin reader 降级 | `run_id=None`, `phase_name`, `builtin_name`, `fallback_reason`, `fallback_strategy`, `excerpt_token_limit`, `warning` | WARN event | `[F-v3-reference-reader-failed]` | 标记系统预读降级 |
| `tool_call` | `read_reference` / `read_example` 返回后 | `phase_name`, `tool_name`, `args`, `result`, `duration_ms` | Q13 per-tool `tool_name` 必填 | `[F-v3-resource-reference-not-found]` / `[F-v3-resource-example-not-found]` | 运行期资料读取结果 |

`read_reference` 和 `read_example` 不需要专属 event kind; 它们走通用 `tool_call`, 但 payload 中 `tool_name` 必须分别是 `read_reference` / `read_example`。这与 Q13 per-tool `tool_name` 决议一致。

规范终点: [Builtin Modules](../skill-spec/09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名), [read_reference / read_example tools](../skill-spec/09-builtin-modules-spec.md#按需调取-tools-read_reference--read_example), [MVP0 Q13](../MVP0-DECISIONS-EXPLAINED-2026-05-21.md#q13)。

### 4. 装配期 Reader Fallback Trace 链路 (改造点 3)

Builtin reference reader 发生在 Agent prompt 装配期, 可能调用本地或远端模型 / 服务。MVP0 MUST 让这段“静默期”进入 trace。

```text
builtin_subagent_enter
  -> local/remote reference reader call
  -> builtin_subagent_exit

or

builtin_subagent_enter
  -> timeout/error/config missing
  -> builtin_subagent_fallback (WARN)
  -> fallback raw excerpt injected into knowledge_base
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `run_id` | string/null | 是 | `None` | 装配期无 run id | — | 标明这是 graph.invoke 前事件 |
| `phase_name` | string | 是 | 无 | 目标 Agent phase | — | Canvas 定位 |
| `builtin_name` | string | 是 | `reference_reader` | 当前只允许 reference reader | — | 系统组件名 |
| `fallback_reason` | enum | fallback 时必填 | 无 | `remote_timeout` / `remote_error` / `config_missing` / `invalid_output` / `local_io_error` | `[F-v3-reference-reader-failed]` | 告诉 Studio 降级原因 |
| `fallback_strategy` | string | fallback 时必填 | `raw_excerpt_3000_tokens` | 非空 | `[F-v3-reference-reader-failed]` | 告诉用户如何继续 |
| `payload.reference_ids` | list[string] | enter/exit 时提供 | `[]` | 当前 Agent references id | — | 资料范围 |
| `excerpt_token_limit` | integer | fallback 时必填 | `3000` | `> 0` | — | fallback 体积边界 |
| `warning` | string | fallback 时必填 | 无 | 可读, `_short_warning()` 最多 500 字符 | `[F-v3-reference-reader-failed]` | TracePanel 展示 |

Fallback 是 WARN, 不阻断 Agent run。`[F-v3-resource-reference-path-invalid]` 是 FATAL path 边界错误, 会 re-raise, 不发 fallback。Reference 机制见 [Reference 三机制生命周期](../skill-spec/08-resource-mechanisms-spec.md#reference-三机制生命周期)。

### 5. 异步日志记录器构建 [SUPERSEDED live path note]

MVP0 历史目标曾希望异步 writer 批量写 `tracing.jsonl` 或推送 event bus。T3 live path 没有引入异步队列；当前 SDK 同步 append `<workspace>/runs/<run_id>/trace.jsonl`，实时 UI 通过 `_SubscriberSink(event_subscriber)` fan-out。该异步 logger 仍可作为未来目标态讨论，但不能再描述为当前实现。

| 字段 / 设置 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `queue_max_size` | integer | 否 | `10000` | `> 0` | — | backpressure |
| `drop_policy` | enum | 否 | `drop_low_value` | 不得丢 `EXCEPTION`, `NODE_END`, fallback events | — | 防止日志拖垮业务 |
| `payload_max_bytes` | integer | 否 | `65536` | 超限截断并标记 | — | 防止单事件过大 |
| `file_rotate_mb` | integer | 否 | `50` | `> 0` | — | 控制磁盘体积 |
| `write_failure` | WARN | 否 | continue | T3 live path 由 `_CompositeEventSink.emit()` 捕获单 sink 异常并继续其它 sink | `[F-v3-runtime-phase-failed]` 仅用于业务异常, 不用于普通写盘 WARN | 保持 runtime 可用 |

高价值事件不能丢: `EXCEPTION`, `BUILTIN_SUBAGENT_FALLBACK`, `AMBIGUITY_LOGGED`, `NODE_END`。

## API

### 1. 当前 CallbackEvent union 与 TraceEventKind 目标态

当前已实现 API 是 Pydantic `CallbackEvent` union, 事件类型通过各 model 的 `event_type: Literal[...]` 字段区分, 不存在已落地的 `TraceEventKind` enum。以下 enum 只作为后续统一 trace facade 的目标态, 不能按当前源码 API 调用。

### 2. TraceEventKind 枚举规范 (目标态)

```python
class TraceEventKind(StrEnum):
    NODE_START = "node_start"
    NODE_END = "node_end"
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_END = "llm_call_end"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    SUBAGENT_ENTER = "subagent_enter"
    SUBAGENT_EXIT = "subagent_exit"
    BUILTIN_SUBAGENT_ENTER = "builtin_subagent_enter"
    BUILTIN_SUBAGENT_EXIT = "builtin_subagent_exit"
    BUILTIN_SUBAGENT_FALLBACK = "builtin_subagent_fallback"
    AMBIGUITY_LOGGED = "ambiguity_logged"
    EXCEPTION = "exception"
```

| 枚举 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `TOOL_CALL_*` | event kind | 是 | 无 | payload 必含 `tool_name` | `[F-v3-tool-argument-invalid]` | Q13 工具级追踪 |
| `BUILTIN_SUBAGENT_*` | event kind | 是 | 无 | 只用于 engine builtin subagent | `[F-v3-reference-reader-failed]` for fallback | 区分系统预读 |
| `AMBIGUITY_LOGGED` | event kind | 是 | 无 | 只由 `log_ambiguity` 成功调用触发 | `[F-v3-tool-argument-invalid]` | Studio ambiguity 面板 |
| `EXCEPTION` | event kind | 是 | 无 | payload 必含 `[F-v3-*]` code | domain-specific | 失败定位 |

枚举只做 additive 扩展, 不重命名已发布值。

### 3. TracingCallback V2 接口定义 (历史目标态，已被 T3 public API 替代)

```python
class V2TracingCallback:
    def on_event(self, event: AgentTraceEvent) -> None: ...
```

推荐 facade:

```python
def on_tool_call_start(run_id: str, phase_id: str, tool_name: str, tool_call_id: str, args: dict) -> None: ...
def on_tool_call_end(run_id: str, phase_id: str, tool_name: str, tool_call_id: str, result: dict) -> None: ...
def on_builtin_subagent_fallback(run_id: str, phase_id: str, payload: dict) -> None: ...
def on_ambiguity_logged(run_id: str, phase_id: str, payload: dict) -> None: ...
```

Callback 实现可写文件、推 event bus 或转 WebSocket。当前源码入口是 public `event_subscriber(event: CallbackEvent)`；继承式 `Callback.on_event(event)` 和 legacy `on_*` hook 只作为内部兼容 sink 使用，不再是 public `run_skill` 的配置面。

### 3.1 T3 live event sink API

| 字段 / 类 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `run_skill(..., event_subscriber=...)` | `Callable[[CallbackEvent], None] | None` | 否 | `None` | public API；订阅器只接收 typed event，不决定落盘路径 | 订阅器异常被记录并隔离 | Studio timeline / tests 实时消费 |
| `_TraceJsonlSink.path` | Path | 是 | `<workspace>/runs/<run_id>/trace.jsonl` | SDK 内部固定文件名，初始化清空，之后逐事件 append | IO 异常记录在 sink 派发层；无 summary `TraceWriteError` 阶段 | 默认黑匣子落盘 |
| `_SubscriberSink` | private sink | 否 | 无 | 包装 public subscriber，调用 `subscriber(event)` | 单 sink 异常不阻断其它 sink | WebSocket / queue / Predict bridge |
| `_CallbackSink` | private sink | 否 | 无 | 只调用 legacy `callback.on_event(event)` | 单 sink 异常不阻断其它 sink | 兼容旧内部对象 |
| `_CompositeEventSink.trace_path` | Path/null | 是 | 第一个 `_TraceJsonlSink.path` | fan-out 到所有 sink | 单 sink 失败继续 fan-out | `WorkflowResult.trace_path` 来源 |
| `_EventSinkCallbackAdapter.on_event` | method | resolver 需要 gateway fallback 时 | 无 | `.on_event(event) -> sink.emit(event)` | 未识别 callbacks 对象 `TypeError`，杜绝静默吞事件 | 让 gateway `LLMFallbackEvent` 回到 sink |

## Data Model / State

### 1. AgentTraceEvent JSON Schema

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `run_id` | string | 目标态字段 | 无 | 同一次 run 内稳定; 当前并非所有 CallbackEvent 都有该字段 | — | 全局归属 |
| `phase_name` | string | phase 相关事件必填 | 无 | 当前源码字段名是 `phase_name` | — | Canvas 定位 |
| `event_type` | Literal string | 是 | 无 | 当前为 Pydantic Literal, 不是已落地 enum | — | 前端路由 |
| `timestamp_ms` | integer | 是 | 无 | 单调递增用于排序 | — | 时间线 |
| `iso_time` | string | 否 | 无 | UTC ISO 8601 | — | 审计 |
| `severity` | enum | 否 | `INFO` | `INFO` / `WARN` / `ERROR` | — | UI 样式 |
| `payload` | dict | 是 | `{}` | 按 event type schema; 超限截断 | event-specific | 事件正文 |

### 2. ToolTracePayload

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `tool_name` | string | 是 | 无 | 真实 tool 名, 如 `read_reference` | — | Q13 per-tool 定位 |
| `tool_call_id` | string | 是 | 无 | 同一请求/响应共享 | — | correlation id |
| `validated_args` | dict | start 必填 | `{}` | 已通过 tool schema 校验 | `[F-v3-tool-argument-invalid]` | 展示实际执行参数 |
| `success` | boolean | end 必填 | 无 | true/false | — | UI 状态 |
| `result_summary` | dict/string | end 必填 | 无 | 可截断; 不泄漏 secrets | — | 展示结果 |
| `error_code` | string | 失败时必填 | 无 | `[F-v3-*]` | domain-specific | 失败定位 |

### 3. BuiltinSubagentTracePayload

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `run_id` | string/null | 是 | `None` | 装配期 builtin reader 没有 invoke run id | — | 全局归属 |
| `phase_name` | string | 是 | 无 | 目标 Agent phase | — | Canvas 定位 |
| `builtin_name` | string | 是 | `reference_reader` | 当前只允许 `reference_reader` | — | 系统组件名 |
| `payload.reference_ids` | list[string] | enter/exit 时提供 | `[]` | 当前 Agent references id | — | 资料范围 |
| `payload.markdown_length` | integer | exit 时提供 | 无 | reader 返回 markdown 字符长度 | — | 成功输出摘要 |
| `fallback_reason` | enum | fallback 时必填 | 无 | `remote_timeout` / `remote_error` / `config_missing` / `invalid_output` / `local_io_error` | `[F-v3-reference-reader-failed]` | 降级原因 |
| `fallback_strategy` | string | fallback 时必填 | 无 | 非空 | `[F-v3-reference-reader-failed]` | 降级方式 |
| `excerpt_token_limit` | integer/null | fallback 时提供 | `3000` | fallback excerpt 上限 | — | 体积边界 |
| `warning` | string | fallback 时提供 | `""` | 短文本; 当前最多 500 字符 | `[F-v3-reference-reader-failed]` | 展示警告 |

## Cross-feature Interaction

### 1. Studio Trace 与 Ambiguity Feedback

`AMBIGUITY_LOGGED` 是 Studio ambiguity feedback 面板的数据源。TracePanel 可以仍显示 `log_ambiguity` tool call, 但产品侧的“待反馈问题列表”应消费专属事件, 避免从普通 tool result 中解析业务语义。

### 2. StateMapper 与 Edge Inspection

`NODE_START.phase_input` 和 `NODE_END.phase_output` 必须来自 [state-and-io-contract](../state-and-io-contract/mvp0-alignment.md#后端功能) 的 StateMapper 沙盒结果, 不得记录全局父黑板。Edge Inspection 可以用上游 output 和下游 input 推导边上传递字段。

### 3. Execution Runtime 调用点绑定

Tracing 不模拟运行过程。它由 [execution-runtime](../execution-runtime/mvp0-alignment.md#后端功能) 在真实 model/tool/subagent/SUBGRAPH/reference-reader 调用点发出事件。`read_reference` / `read_example` 运行期事件走 TOOL_CALL, 装配期 reference reader 走 BUILTIN_SUBAGENT。

### 4. 安全与截断

Trace payload 不保存 provider API key、HTTP headers、完整大文档或未截断 prompt。长字符串、reference 原文、tool result 必须截断并标记 `truncated=true`。Debug 全量输出只能通过显式本地调试开关打开。

## 与当前源码的差异

本文件包含历史目标态和 T3 live path。当前 trace / event_subscriber 体系的源码事实为：

| 本文件目标态 | 当前源码事实 |
|---|---|
| runtime 在 phase start/end、LLM、tool、subagent 等真实调用点发事件 | **已部分对齐 (T3)**: `_wrap_phase_runtime_node` 单源发 LOGIC / SUBGRAPH / Agent 的 `phase_start` / `phase_end`; Agent loop 发 `llm_call` / `tool_call`; runner 只发 `run_started` / `run_ended`。 |
| 统一 `AgentTraceEvent` / `TraceEventKind` schema | 当前主要是 Pydantic `CallbackEvent` union，事件名是小写字符串；不要把目标 enum 当已实现 API。 |
| `NODE_START` / `NODE_END` payload 来自 StateMapper 沙盒输入输出 | live API 名称是 `phase_start` / `phase_end`；graph skill path 已在 `_wrap_phase_runtime_node` 中发这些事件。 |
| TOOL_CALL start/end 分离并带 `tool_call_id` | 当前 `ToolCallEvent` 是单个 `tool_call` 事件，字段为 `phase_name/tool_name/args/result/duration_ms`。 |
| builtin reference reader enter/exit/fallback 在装配期真实发出 | 当前已通过 `assemble_graph(..., callbacks=event_sink)` 接线；缺省状态下 `_TraceJsonlSink` 也能接管事件流并强制自动落盘到 `trace.jsonl`。 |
| fallback 事件通过统一 tracing 底座发出 | 当前 gateway fallback 仍直接遍历 resolver 得到的 `callbacks` 并调 `on_event`；T3 用 `_EventSinkCallbackAdapter` 把 event sink 包成 callback 形对象，避免 fallback 事件被吞。 |
| prompt、reference、tool result 按统一策略截断 | 当前部分 proxy / tracing 能做轻量序列化，但没有全局统一截断策略覆盖所有 graph skill 事件。 |
| 异步日志记录器 (queue / drop policy / payload 上限 / 文件轮转) | **目标态 (MVP0 SHOULD)，T3 未实现**；当前 `_TraceJsonlSink` 同步 append JSONL，无异步队列 / 背压 / 轮转。 |
