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
  -> callback.on_event(event) 或 legacy on_* hook
  -> TracingCallback 写 tracing.jsonl
```

PR E 之后，`log_ambiguity` 的业务反馈事件、装配期 builtin reference reader 的 enter / exit / fallback 事件都已经接到这条主线。它们不会替代已有 tool trace，而是并列补充业务含义。

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

Callback 有两套接口：

1. 新接口：`on_event(event)`，直接收 typed event。
2. 旧接口：`on_phase_start()`、`on_tool_call()`、`on_llm_call()` 等。

默认 `Callback.on_event()` 分三类处理：

| 类别 | 行为 |
|---|---|
| 有 legacy hook 的事件 | 转回旧接口，例如 `PhaseStartEvent -> on_phase_start()`、`ToolCallEvent -> on_tool_call()`。 |
| 已知 typed-only 事件 | debug no-op。没有旧 hook，但这是合法事件，不 warning。 |
| 未识别事件 | 打 warning：`Callback.on_event received unrecognised event type ...`。 |

PR E 把这 4 个事件加入了 typed-only 合法列表：

- `AmbiguityLoggedEvent`
- `BuiltinSubagentEnterEvent`
- `BuiltinSubagentExitEvent`
- `BuiltinSubagentFallbackEvent`

所以普通 `Callback()` 收到这些事件不会误报 unknown；真正消费它们的 callback 仍应覆盖 `on_event()`。

## 5. TracingCallback 怎么写文件

`TracingCallback` 是当前主要 trace sink。

它会写两种文件形状：

1. legacy JSONL：按旧 event shape 写到带 run id 的 jsonl 文件。
2. typed JSONL：把 Pydantic event 直接写到固定名字 `tracing.jsonl`。

收到 typed event 时，`TracingCallback.on_event()` 直接调用 `event.model_dump_json()` 追加到 `tracing.jsonl`。因此 PR E 新增投递的 `ambiguity_logged` 和 `builtin_subagent_*` 事件只要进入 callback list，就能落盘。

## 6. tool trace 与 `log_ambiguity`

`log_ambiguity` 是普通工具，也是业务反馈入口。PR E 的原则是并列投递：

```text
tool lifecycle trace
  + ambiguity_logged 业务事件
```

当前 typed tool 事件是 `ToolCallEvent(event_type="tool_call")`，不是拆成 `TOOL_CALL_START` / `TOOL_CALL_END` 两个 Pydantic 事件。`TracingCallback.on_tool_call()` 会写出这个 `tool_call` 事件，字段包括：

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

callbacks 通道来自 `assemble_graph(..., callbacks=None)`：

- `loader.load_workflow_from_md(..., callbacks=...)` 会透传到 `assemble_graph()`。
- `runner._run_v030_skill_dict(..., callbacks=...)` 会透传到 `assemble_graph()`。
- `assemble_graph()` 再把 callbacks 传到 `_build_reference_reader_markdown()`。

没有 callbacks 时，reference reader 仍正常生成 prompt knowledge base，只是不发 trace。

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

当前这条事件是 gateway 直接遍历 callbacks 发出的，不是通过一个全局 runtime trace dispatcher。

## 15. prompt capture 怎么工作

`TracingClientProxy` 是一个透明代理，用来包住 chat model。

模型真正调用前，它先发 `prompt_captured` 事件，然后再把调用转给原模型。

如果构造事件失败，或者某个 callback 报错，proxy 会记录日志并继续调用模型。trace 失败不能影响真实模型调用。

## 16. 最容易误解的点

### 有事件模型不代表所有路径都会发事件

事件 class 已经定义，不等于每个 graph skill phase 都会发对应事件。PR E 只接了 ambiguity feedback 和 builtin reference reader 装配期事件，不等于完整 phase lifecycle 已全部接线。

### `warning` 不是 `warning_message`

`BuiltinSubagentFallbackEvent` 的真实字段是 `warning`。写成 `warning_message` 会被 Pydantic 拒绝。

### `phase_name` 不是 `phase_id`

当前 typed event schema 使用 `phase_name`。文档或测试里把它写成 `phase_id`，是在讲旧目标态，不是当前 API。

### TracingCallback 不会自己观察运行

它只是 callback sink。只有运行时调用它，它才会写文件。

### callback 失败不会中断业务

多个地方都选择吞掉 callback 异常并继续运行。trace 是观测能力，不应该让业务 run 因为 UI/日志失败而失败。

## 17. 总图

```text
log_ambiguity tool
  -> callback bridge 暂存 callbacks/phase
  -> tool wrapper 注入 ctx["_callbacks"]
  -> log_ambiguity 写业务记录
  -> AmbiguityLoggedEvent via on_event
  -> tool_call via legacy on_tool_call

reference reader assembly
  -> assemble_graph(callbacks=...)
  -> BuiltinSubagentEnterEvent
  -> reader.run()
       -> BuiltinSubagentExitEvent
       or BuiltinSubagentFallbackEvent
  -> fallback markdown 只进 prompt，不进 event payload
```
