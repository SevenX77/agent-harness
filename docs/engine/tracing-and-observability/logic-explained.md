# tracing-and-observability 运行逻辑人话版

署名：Codex  
日期：2026-05-23  
定位：只解释当前 trace / callback 体系真实怎么运行，不做源码导览，不讲实现写法。

## 1. 一句话结论

`tracing-and-observability` 定义的是“运行过程中发生了什么，如何变成事件”。

它的核心由三层组成：

```text
事件模型
  -> Callback.on_event / legacy on_* hook
  -> TracingCallback 写 JSONL / tracing.jsonl
```

事件协议本身已经比较完整；legacy harness 路径也会发不少事件。但当前 graph skill dict runner 会丢弃 callbacks，所以 graph skill 主路径还没有完整接入这套 trace 主线。

## 2. 事件模型是什么

事件模型是一组 Pydantic model。每个事件都有一个固定的 `event_type`。

例子：

```json
{
  "event_type": "phase_start",
  "phase_name": "analyze",
  "context": { "topic": "solar" }
}
```

再比如模型 fallback：

```json
{
  "event_type": "llm_fallback",
  "phase_name": "analyze",
  "from_provider": "openai/gpt-a",
  "to_provider": "anthropic/claude-b",
  "reason": "TimeoutError: timed out"
}
```

所有事件最后组成一个 discriminated union。人话就是：读 JSON 时，根据 `event_type` 判断它应该还原成哪种事件对象。

## 3. 每个事件共享什么字段

每个事件都会带一些公共字段：

| 字段 | 人话解释 |
|---|---|
| `schema_version` | 事件协议版本。 |
| `timestamp` | 事件发生时间。 |
| `sub_run_id` | 并发/子运行分组时可用。 |
| `group_key` | parallel map 这类分组场景可用。 |

事件不允许随便塞未声明字段。这样 Studio 或离线分析工具读 trace 时，不需要猜某个字段到底是不是协议的一部分。

## 4. Callback 怎么分发事件

Callback 有两套接口：

1. 新接口：`on_event(event)`，直接收 typed event。
2. 旧接口：`on_phase_start()`、`on_tool_call()`、`on_llm_call()` 等。

默认 `on_event()` 会把一部分 typed event 转回旧接口。

例子：

```text
PhaseStartEvent
  -> Callback.on_event(event)
  -> 默认分发到 on_phase_start(phase_name, context)
```

但有些新事件没有旧接口，比如：

- `prompt_captured`
- `llm_fallback`
- `run_started`
- `heartbeat`
- `model_resolved`

这些事件如果 callback 想消费，就必须直接覆盖 `on_event()`。

## 5. TracingCallback 怎么写文件

`TracingCallback` 是当前主要的 trace sink。

它会写两种文件形状：

1. legacy JSONL：按旧 event shape 写到带 run id 的 jsonl 文件。
2. typed JSONL：把 Pydantic event 直接写到固定名字 `tracing.jsonl`。

例子：收到 `PhaseStartEvent` 后，typed trace 里会有一行 JSON：

```json
{"event_type":"phase_start","phase_name":"analyze","context":{"topic":"solar"}}
```

同时，legacy trace 里也可能写一行旧格式事件，用于兼容已有工具。

## 6. prompt capture 怎么工作

`TracingClientProxy` 是一个透明代理，用来包住 chat model。

模型真正调用前，它先发 `prompt_captured` 事件，然后再把调用转给原模型。

例子：

```text
Agent 准备调用 LLM
  -> TracingClientProxy 收到 messages
  -> 发 PromptCapturedEvent
  -> 调真实 chat_model.invoke(messages)
```

如果构造事件失败，或者某个 callback 报错，proxy 会记录日志并继续调用模型。trace 失败不能影响真实模型调用。

## 7. gateway fallback 事件怎么来

模型 gateway 在 provider 调用失败并切换下一个候选时，会发 `llm_fallback` 事件。

例子：

```text
openai/gpt-a 超时
  -> 标记 down
  -> 准备尝试 anthropic/claude-b
  -> 发 LLMFallbackEvent
```

事件里会有失败 provider、下一个 provider、原因和 phase name。

当前这条事件是 gateway 直接遍历 callbacks 发出的，不是通过一个统一的 runtime trace dispatcher。

## 8. ambiguity 事件怎么来

`log_ambiguity` 成功记录业务歧义后，会尝试发 `ambiguity_logged` 事件。

例子：

```json
{
  "event_type": "ambiguity_logged",
  "ambiguity_type": "schema",
  "question": "Should missing fields be inferred?",
  "decision": "Do not infer.",
  "reason": "Need explicit data."
}
```

它依赖上下文里存在 callbacks。没有 callbacks 时，它只完成业务记录，不会产生事件。

## 9. builtin subagent 事件是什么

事件协议里已经定义了 builtin subagent 相关事件：

- `builtin_subagent_enter`
- `builtin_subagent_exit`
- `builtin_subagent_fallback`

它们用于区分 Engine 内置能力和用户声明的 subagent。

但当前 state / runtime 主线里，reference reader 的完整 enter/exit/fallback 发射流程并不能只从这套事件模型推出。事件模型有了，不等于所有运行路径都已经发事件。

## 10. 当前 graph skill trace 的断点

当前 graph skill dict runner 接收 `callbacks` 参数，但会直接丢弃。

结果是：即使调用方传了 `TracingCallback`，graph skill 主路径也不会自动产生完整的 phase start、phase end、LLM call、tool call 事件。

这点和 legacy harness 路径不同。legacy harness 里 callbacks 是主线服务，很多 phase node 会主动调用 callback hook。

所以当前要区分：

| 路径 | trace 状态 |
|---|---|
| legacy SKILL.md harness | callbacks 主线接入较多。 |
| 当前 graph skill dict runner | callbacks 参数目前被丢弃，trace 主线未完整接入。 |
| gateway fallback | 如果 gateway model 有 callbacks，会直接发 fallback event。 |
| TracingClientProxy | 如果显式包住模型并传 callbacks，会发 prompt capture。 |

## 11. 最容易误解的点

### 有事件模型不代表运行时已经发事件

事件 class 已经定义，不等于每个 graph skill phase 都会发对应事件。

### TracingCallback 不会自己观察运行

它只是 callback sink。只有运行时调用它，它才会写文件。

### callback 失败不会中断业务

多个地方都选择吞掉 callback 异常并继续运行。trace 是观测能力，不应该让业务 run 因为 UI/日志失败而失败。

### typed event 和 legacy hook 是并存关系

新事件走 `on_event()`；部分旧事件可以被默认分发回旧 hook。两套不是完全等价。

## 12. 总图

```text
运行点产生事实
  -> 构造 typed CallbackEvent
  -> callback.on_event(event)
  -> TracingCallback 写 tracing.jsonl

legacy hook 路径:
  -> callback.on_phase_start / on_tool_call / ...
  -> TracingCallback 同时写 legacy jsonl + typed event
```

当前缺口：

```text
graph skill dict runner
  -> callbacks 参数被丢弃
  -> graph phase 主线事件尚未完整接入
```
