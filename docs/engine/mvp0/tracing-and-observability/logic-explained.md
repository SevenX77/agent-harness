# tracing-and-observability 运行逻辑人话版

署名：Codex
日期：2026-05-26
定位：只解释当前 trace / callback 体系真实怎么运行，不做源码导览，不讲实现写法。

## 1. 一句话结论

`tracing-and-observability` 定义的是“运行过程中发生了什么，如何变成事件”。

当前主线是：

```text
真实运行点 / 装配点
  -> 构造 Pydantic CallbackEvent
  -> _safe_emit_event(event_sink, event)
  -> _CompositeEventSink fan-out
       -> _TraceJsonlSink 写 <workspace>/runs/<run_id>/trace.jsonl
       -> _SubscriberSink 调 event_subscriber(event)
       -> _CallbackSink 兼容内部 legacy callback.on_event(event)
```

PR E 之后，`log_ambiguity` 的业务反馈事件、装配期 builtin reference reader 的 enter / exit / fallback 事件都已经接到这条主线。它们不会替代已有 tool trace，而是并列补充业务含义。

Round 32 PR-1 (T3) 之后，V0.3.0 目录型 `GRAPH.md` 主运行路径不再暴露 public `callbacks` list。public `run_skill()` 的实时出口是 `event_subscriber: Callable[[CallbackEvent], None] | None`，默认落盘出口永远由 SDK 内部 `_TraceJsonlSink` 负责。`RunResult.trace_path` 指向真实存在的 `trace.jsonl`，不再指向 `{run_id}_summary.json`。

## 2. 事件模型是什么

事件模型是一组 Pydantic model。每个事件都有一个固定的 `event_type`，并通过 `CallbackEvent` discriminated union 解析。

例子：

```json
{
  "event_type": "tool_call",
  "phase_name": "main",
  "tool_name": "log_ambiguity",
  "args": {},
  "result": "{\"status\":\"recorded\"}"
}
```

再比如 builtin reader fallback：

```json
{
  "event_type": "builtin_subagent_fallback",
  "run_id": null,
  "phase_name": "main",
  "builtin_name": "reference_reader",
  "fallback_reason": "remote_timeout",
  "fallback_strategy": "raw_excerpt_3000_tokens",
  "excerpt_token_limit": 3000,
  "warning": "[F-v3-reference-reader-failed] timeout"
}
```

事件不允许随便塞未声明字段。`events.py` 的 Pydantic model 使用 `extra="forbid"`，所以 Studio 或离线分析工具不需要猜某个字段是不是协议的一部分。

## 3. 每个事件共享什么字段

所有 `CallbackEvent` 都继承这些公共字段：

| 字段 | 人话解释 |
|---|---|
| `schema_version` | 事件协议版本，当前为 `"1.0"`。 |
| `timestamp` | 事件构造时间，UTC ISO 字符串。 |
| `sub_run_id` | 并发/子运行分组时可用；没有分组时为 `null`。 |
| `group_key` | parallel map 这类分组场景可用；没有分组时为 `null`。 |

注意：不是每个事件都有 `run_id`。例如 `AmbiguityLoggedEvent` 没有 `run_id` 字段；`BuiltinSubagent*Event` 有 `run_id: str | None = None`，装配期明确使用 `None`。

## 4. Callback 怎么分发事件

Callback 只有一个接口：`on_event(event)`，直接收 typed event（决议
2026-08-15 边分段 D7：旧的 8 个 `on_*` 钩子与它们的翻译层已删除）。基类默认实现
是 no-op —— 没要事件的消费方就不会被告知，事件也不会在半路被改写成另一种形状。

消费方覆写 `on_event()` 并按事件类型自行分派；不关心的类型直接落到 else 分支被忽略，
不产生 warning。引擎装配给中间件的 `_EventSinkCallbackAdapter` 就只有这一个方法，
所以"发送端调了别的方法名"这件事在结构上不可能再发生。

## 5. Event sink 怎么写文件和分发

T3 后的主落盘路径不是 `TracingCallback`，而是 `graph_agent.callbacks.emit` 里的私有 sink 组合。入口在 `runner._prepare_v030_event_sink()`：它固定创建 `_TraceJsonlSink(trace_output)`，按需追加 `_SubscriberSink(event_subscriber)`，内部兼容场景才追加 `_CallbackSink(callbacks)`，最后返回 `_CompositeEventSink`，见 `packages/graph-agent/src/graph_agent/core/runner.py:237-248`。

| 类 / 方法 | 字段 / 路径 | 为什么这么设计 | 干什么用 | 失败时行为 / 错误码 |
|---|---|---|---|---|
| `_TraceJsonlSink.__init__(trace_dir)` | `self.path = trace_dir / "trace.jsonl"`；初始化时 `mkdir(parents=True)` 并清空文件，见 `callbacks/emit.py:15-21` | trace 文件名和 run 目录由 SDK 决定，调用方不能再通过 public callback 决定写到哪里 | 给每次 run 建立唯一 typed event stream：`<workspace>/runs/<run_id>/trace.jsonl` | 目录/文件创建失败会直接抛出底层 IO 异常；当前 T3 不再用 `TraceWriteError` 包装 save 阶段，因为没有 summary save 阶段 |
| `_TraceJsonlSink.emit(event)` | `event.model_dump(mode="json")` 或原对象；每个事件 append 一行 JSON，见 `callbacks/emit.py:23-26` | 每事件即时落盘，不等 run 结束汇总，崩溃前事件也能留下 | 写 `run_started`、`phase_start`、`llm_call`、`tool_call`、`phase_end`、`run_ended`、gateway fallback 等 typed event | 写入异常会被外层 `_CompositeEventSink.emit()` 捕获并 `logger.exception`，继续 fan-out 到其它 sink；没有 `[F-v3-*]` 业务错误码 |
| `_SubscriberSink.emit(event)` | 调 `event_subscriber(event)`，见 `callbacks/emit.py:29-34` | public API 只暴露函数式实时订阅，不再要求用户继承 Callback class | Studio WebSocket queue、Predict trace adapter、测试 spy 都走这里 | 订阅器异常由 `_CompositeEventSink.emit()` 捕获记录，不能破坏 trace 落盘 |
| `_CallbackSink.emit(event)` | 遍历内部 `callbacks`，只调用可调用的 `callback.on_event(event)`，见 `callbacks/emit.py:37-45` | 保留 private 兼容：旧测试、Predict 内部桥或尚未迁完的私有调用仍可复用 legacy callback 对象 | 不是 public `run_skill` API；只服务内部过渡 | 单个 callback 异常由 `_CompositeEventSink.emit()` 捕获记录，继续后续 sink |
| `_CompositeEventSink.emit(event)` | `self._sinks`；`trace_path` 指向第一个 `_TraceJsonlSink.path`，见 `callbacks/emit.py:48-65` | fan-out 统一在一个对象里，runner/graph_assembler 不关心有几个出口 | 同一事件同时落盘、推 subscriber、兼容 legacy callback | 每个 sink 独立 try/except；观测失败不应中断业务 run |
| `_safe_emit_event(callbacks, event)` | 接受 `.emit` sink、直接 callable subscriber、或 legacy callback iterable，见 `callbacks/emit.py:68-101` | 让 runner、graph_assembler、builtin subagent 都通过同一派发入口 | 消除各处手写 callback 循环导致的漏发/双发差异 | 记录 `logger.exception` 后继续；未知 iterable callback 抛错不传播 |

`run_skill()` 的 public 签名见 `packages/graph-agent/src/graph_agent/core/runner.py:65-79`。`event_subscriber` 会传入 `_run_skill_dict()` 和 `_run_v030_skill_dict()`，见 `runner.py:90-103`、`runner.py:145-160`、`runner.py:298-308`。`_run_v030_skill_dict()` 用 `workspace_dir / "runs" / run_id` 构造 `trace_output`，创建 event sink 后立刻发 `RunStartedEvent`，见 `runner.py:315-331`；成功时发 `RunEndedEvent(status="completed")` 并返回 `trace_path=str(event_sink.trace_path)`，见 `runner.py:376-395`；异常时发 `RunEndedEvent(status="crashed")` 后继续抛异常，见 `runner.py:352-364`。

同一个 run 目录还会写 `result.json`、`final_state.json`、`metrics.json`，见 `runner.py:230-234`；声明 `target: file` 且没有显式路径的输出默认进入 `artifacts/`，见 `runner.py:264-295`。T3 主线没有 run-id summary JSON，也没有 tracing callback 的结束后保存步骤。

## 5.1 V0.3.0 phase wrapper 现在发哪些事件

V0.3.0 phase lifecycle 的发射点在 `_wrap_phase_runtime_node()`，覆盖 LOGIC / SUBGRAPH / Agent 三类节点，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:218-249`。这是 T3 单源设计：phase start/end 只在 wrapper 发，runner 不再按 `assembled.phase_ids` 批量“猜测”生命周期，Agent 节点内部也不再重复发 phase start/end。

`PhaseStartEvent` 在 wrapper 调用节点前发出，字段形态是完整 blackboard data 快照：

```json
{
  "inputs": {"topic": "T"},
  "phase_outputs": {},
  "scratch": {}
}
```

这个形态来自 `_observable_data_context()`，它固定返回 `{inputs, phase_outputs, scratch}` 三段，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:614-620`。这里不能只发 inputs 子集，因为 Studio 需要同一套 timeline 展示逻辑看每个 phase 的输入输出。

`LLMCallEvent` 只在 Agent 节点的每次 `model.invoke(...)` 返回后发出，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:431-445`。token 使用量通过 `_extract_token_usage()` 归一，支持 `input_tokens/output_tokens`、`prompt_tokens/completion_tokens`、`total_input_tokens/total_output_tokens`，缺失或不可转整数时降级为 `0`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:645-663`。

`ToolCallEvent` 在每个工具成功返回后发出，覆盖普通工具、framework tool、subagent tool 和 `finish_task`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:468-475`。事件里的 `args` 必须是 dict；非 dict 入参按空 dict 处理。事件里的 `result` 必须是 string，dict/list 会用 `json.dumps(..., ensure_ascii=False, default=str)` 变成 JSON 字符串，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:677-682`。

`PhaseEndEvent` 在 `_wrap_phase_runtime_node()` 的 `finally` 中统一发出，见 `graph_assembler.py:236-247`。它覆盖正常返回、`finish_task` 早返回和异常路径；异常路径发完 end 后继续向外抛。因为 phase lifecycle 只在 wrapper 发，所以不需要 Agent 内部的防重状态，也避免 runner 批量假发造成双写。

`PhaseEndEvent.context` 同样是完整 data 结构。`_phase_end_context()` 会把 phase 输出包成 `{"inputs": {}, "phase_outputs": {phase_id: ...}, "scratch": {}}`；如果 response 已经是完整 blackboard data，则保留完整结构，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:623-642`。

## 6. tool trace 与 `log_ambiguity`

`log_ambiguity` 是普通工具，也是业务反馈入口。PR E 的原则是并列投递：

```text
tool lifecycle trace
  + ambiguity_logged 业务事件
```

当前 typed tool 事件是 `ToolCallEvent(event_type="tool_call")`，不是拆成 `TOOL_CALL_START` / `TOOL_CALL_END` 两个 Pydantic 事件。Agent loop 构造事件后经 `_safe_emit_event(callbacks, event)` 进入 event sink，默认由 `_TraceJsonlSink.emit()` 写入 `trace.jsonl`。字段包括：

| 字段 | 人话解释 |
|---|---|
| `phase_name` | 当前 phase。 |
| `tool_name` | 工具名，例如 `log_ambiguity`。 |
| `args` | 工具参数，尽量是已解析 dict。 |
| `result` | 工具返回文本。 |
| `duration_ms` | 工具耗时，可能为 `null`。 |

`ambiguity_logged` 不是 tool result 的替代品。它是给 Studio ambiguity feedback 面板消费的结构化业务事件。

## 7. `_callbacks` 怎么进入 `log_ambiguity` ctx

`log_ambiguity` 底层函数 `_emit_ambiguity_logged(ctx, record)` 只认 `ctx["_callbacks"]`：

```text
ctx["_callbacks"] 是 list
  -> 遍历 callback.on_event(AmbiguityLoggedEvent)

ctx["_callbacks"] 不存在或不是 list
  -> 静默 return
```

PR E 修的是 runtime/tool path 的注入缺口：

1. `callback_bridge.py` 在 `on_tool_start` 时用 ContextVar `_CURRENT_TOOL_CALLBACKS` 记录当前 phase 和 callbacks。
2. 同一个 tool run 的 `on_tool_end` / `on_tool_error` 会 reset 这个 ContextVar，避免污染后续工具。
3. `tool_wrapper.py` 在真正调用带 `ctx` / `context` 参数的工具前，通过 `_tool_context_with_callbacks()` 读取 ContextVar。
4. 如果 ContextVar 里有 callbacks list，就用 `setdefault` 给工具 ctx 注入：
   - `_callbacks`
   - `_current_phase`

这里用 `setdefault` 是为了不覆盖测试或调用方已经显式放进 ctx 的值。

## 8. `AmbiguityLoggedEvent` 字段

`log_ambiguity` 成功记录后会构造 `AmbiguityLoggedEvent`：

| 字段 | 来源 | 人话解释 |
|---|---|---|
| `event_type` | 固定值 `"ambiguity_logged"` | Studio 路由到 ambiguity 面板。 |
| `phase_name` | `record["phase"]` | 当前 Agent phase；没有时可以为 `null`。 |
| `ambiguity_type` | 工具入参 | 歧义类型。 |
| `question` | 工具入参 | 模型遇到的模糊点。 |
| `decision` | 工具入参 | 本次运行采用的决定。 |
| `reason` | 工具入参 | 决定理由，默认空字符串。 |
| `related_refs` | 从 `question + reason` 抽取 `@reference:<id>` | 关联 reference id。 |
| `related_protocols` | 从 `question + reason` 抽取 `@protocol:<id>` | 关联 protocol id。 |

callback 抛错不会阻断工具返回。`_emit_ambiguity_logged` 会 warning 后继续下一个 callback。

## 9. builtin reference reader 事件怎么来

`reference_reader` 发生在图装配期，也就是 `graph.invoke()` 之前。此时没有真实 run，所以 builtin reader 事件使用：

| 字段 | 当前值 |
|---|---|
| `run_id` | `None` |
| `phase_name` | 当前目标 phase，例如 `"main"` |
| `builtin_name` | `"reference_reader"` |

事件通道来自 runner 创建的 `_CompositeEventSink`：

- `runner._run_v030_skill_dict()` 创建 event sink 后调用 `assemble_graph(..., callbacks=event_sink)`，见 `runner.py:319-342`。
- `assemble_graph()` 把同一个 sink 传到 `_build_reference_reader_markdown()`，见 `graph_assembler.py:366-372`。
- builtin reader 事件经 `_emit_builtin_subagent_event()` 调 `_safe_emit_event(callbacks, event)`，见 `graph_assembler.py:825-826`。

没有 `event_subscriber` 时，`_TraceJsonlSink` 仍然存在，所以 reference reader 等事件默认也会进入 `trace.jsonl`。这像黑匣子：仪表盘可以不接，黑匣子仍然记录。

## 10. `BUILTIN_SUBAGENT_ENTER`

只要 phase 声明了 references，装配期 reader 调用前先发 `BuiltinSubagentEnterEvent`：

| 字段 | 人话解释 |
|---|---|
| `event_type` | 固定值 `"builtin_subagent_enter"`。 |
| `run_id` | 装配期为 `None`。 |
| `phase_name` | 目标 Agent phase。 |
| `builtin_name` | `"reference_reader"`。 |
| `payload.reference_ids` | 本 phase 声明的 reference id 列表。 |

references 为空时不发 builtin reader 事件。

## 11. `BUILTIN_SUBAGENT_EXIT`

reader 成功返回非空 markdown 时，发 `BuiltinSubagentExitEvent`：

| 字段 | 人话解释 |
|---|---|
| `event_type` | 固定值 `"builtin_subagent_exit"`。 |
| `run_id` | 装配期为 `None`。 |
| `phase_name` | 目标 Agent phase。 |
| `builtin_name` | `"reference_reader"`。 |
| `payload.reference_ids` | 本次 reader 输入 reference id。 |
| `payload.markdown_length` | reader 返回 markdown 的字符长度。 |

EXIT payload 不包含 reference 原文，也不包含最终注入 prompt 的完整 knowledge base。

## 12. `BUILTIN_SUBAGENT_FALLBACK`

reader 超时、异常、配置缺失或输出无效时，发 `BuiltinSubagentFallbackEvent`，然后走 fallback markdown，把原始 reference 摘要注入 `<knowledge_base>`，让 Agent run 继续。

事件字段：

| 字段 | 人话解释 |
|---|---|
| `event_type` | 固定值 `"builtin_subagent_fallback"`。 |
| `run_id` | 装配期为 `None`。 |
| `phase_name` | 目标 Agent phase。 |
| `builtin_name` | `"reference_reader"`。 |
| `fallback_reason` | 5 个 Literal 之一：`remote_timeout` / `remote_error` / `config_missing` / `invalid_output` / `local_io_error`。 |
| `fallback_strategy` | 当前固定为 `"raw_excerpt_3000_tokens"`。 |
| `excerpt_token_limit` | 当前为 `3000`。 |
| `warning` | 短警告文本，经 `_short_warning()` 截到最多 500 字符。 |

fallback reason 映射规则：

| 情况 | `fallback_reason` |
|---|---|
| `TimeoutError`，或错误文本含 `timeout` / `timed out` | `remote_timeout` |
| `OSError` | `local_io_error` |
| 错误文本含 `missing config` / `config_missing` | `config_missing` |
| 错误文本含 `invalid` / `empty` / `missing markdown` | `invalid_output` |
| 其他异常 | `remote_error` |

事件 payload 绝不放 reference 原文、fallback markdown 或 `<knowledge_base>` 内容。原文只进入业务 prompt 的 fallback knowledge base，不进入 trace event。

## 13. path invalid 为什么特殊

如果 reference path 越界或非法，会走 `[F-v3-resource-reference-path-invalid]`。这类错误是 FATAL：

```text
BUILTIN_SUBAGENT_ENTER
  -> path invalid
  -> re-raise GraphAgentFatalError / SkillLoadError
  -> 不发 BUILTIN_SUBAGENT_FALLBACK
```

原因是 path invalid 不是“reader 服务失败后可降级”，而是资源边界被破坏。把它伪装成 fallback 会误导 Studio 和用户。

## 14. gateway fallback 事件怎么来

模型 gateway 在 provider 调用失败并切换下一个候选时，会发 `llm_fallback` 事件。

例子：

```text
openai/gpt-a 超时
  -> 标记 down
  -> 准备尝试 anthropic/claude-b
  -> 发 LLMFallbackEvent
```

事件里会有失败 provider、下一个 provider、原因和 phase name。

当前这条事件是 gateway 直接遍历 `event_callbacks` 并调用 `callback.on_event(event)` 发出的，不是通过全局 runtime trace dispatcher。为了让 gateway 的 callback 契约接回 T3 的 sink，`graph_assembler._callback_tuple()` 对 `.emit` 型 sink 包 `_EventSinkCallbackAdapter`：adapter 暴露 `on_event(event) -> sink.emit(event)`，再传给 `model_resolver.resolve(callbacks=...)`，见 `graph_assembler.py:519-540`。这样 gateway 的 `LLMFallbackEvent` 会同时进入 `_TraceJsonlSink` 和 `_SubscriberSink`。

`LLMFallbackEvent.code` 可带 `[F-v3-gateway-all-providers-failed]` 等 gateway 错误码。`_callback_tuple()` 对未知 callbacks 对象不再静默返回空 tuple，而是 `raise TypeError("unsupported callbacks object: ...")`，见 `graph_assembler.py:526-529`。这是为了避免 provider fallback 已经发生但 trace/subscriber 无声丢事件的静默降级。

## 15. prompt capture 怎么工作

`TracingClientProxy` 是一个透明代理，用来包住 chat model。

模型真正调用前，它先发 `prompt_captured` 事件，然后再把调用转给原模型。

如果构造事件失败，或者某个 callback 报错，proxy 会记录日志并继续调用模型。trace 失败不能影响真实模型调用。

## 16. 最容易误解的点

### 有事件模型不代表所有路径都会发事件

事件 class 已经定义，不等于每个 graph skill phase 都会发对应事件。PR E 只接了 ambiguity feedback 和 builtin reference reader 装配期事件。PR-2 进一步把 V0.3.0 Agent `_skill_node` 接上了 `phase_start`、`llm_call`、`tool_call`、`phase_end`。LOGIC / SUBGRAPH 节点和其他目标态事件仍要按各自 runtime 接线状态判断，不能只看 event class 是否存在。

### `warning` 不是 `warning_message`

`BuiltinSubagentFallbackEvent` 的真实字段是 `warning`。写成 `warning_message` 会被 Pydantic 拒绝。

### `phase_name` 不是 `phase_id`

当前 typed event schema 使用 `phase_name`。文档或测试里把它写成 `phase_id`，是在讲旧目标态，不是当前 API。

### `_TraceJsonlSink` 不会自己观察运行

它只是 event sink。只有 runner、graph_assembler、gateway adapter 调它的 `emit()`，它才会写文件。

### callback 失败不会中断业务

多个地方都选择记录观测出口异常并继续运行。trace 是观测能力，不应该让业务 run 因为 UI/日志失败而失败。

T3 把这个隔离逻辑收敛到 `graph_agent.callbacks.emit._safe_emit_event(callbacks, event)` 和 `_CompositeEventSink.emit(event)`。它们会识别 `.emit` sink、函数式 subscriber 或 legacy callback iterable；某个出口抛错时记录 `logger.exception`，然后继续其它出口，见 `packages/graph-agent/src/graph_agent/callbacks/emit.py:48-101`。

## 17. 总图

```text
log_ambiguity tool
  -> callback bridge 暂存 callbacks/phase
  -> tool wrapper 注入 ctx["_callbacks"]
  -> log_ambiguity 写业务记录
  -> AmbiguityLoggedEvent via on_event
  -> ToolCallEvent via on_event

reference reader assembly
  -> assemble_graph(callbacks=...)
  -> BuiltinSubagentEnterEvent
  -> reader.run()
       -> BuiltinSubagentExitEvent
       or BuiltinSubagentFallbackEvent
  -> fallback markdown 只进 prompt，不进 event payload

V0.3.0 Agent phase
  -> _wrap_phase_runtime_node
       -> PhaseStartEvent(context={inputs, phase_outputs, scratch})
  -> model.invoke()
       -> LLMCallEvent(tokens normalized; missing -> 0)
  -> tool.invoke()
       -> ToolCallEvent(result stringified)
  -> normal / max-turn / exception exit
       -> wrapper finally sends PhaseEndEvent once

V0.3.0 runner
  -> _prepare_v030_event_sink()
       -> _TraceJsonlSink(<workspace>/runs/<run_id>/trace.jsonl)
       -> optional _SubscriberSink(event_subscriber)
       -> optional private _CallbackSink(callbacks)
  -> RunStartedEvent
  -> graph.invoke()
  -> RunEndedEvent(completed/crashed)
  -> trace_path = real trace.jsonl path
```
