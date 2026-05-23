# graph-agent-gateway 运行逻辑人话版

署名：Codex  
日期：2026-05-23  
定位：只解释当前模型网关真实怎么运行，不做源码导览，不讲实现写法。

## 1. 一句话结论

`graph-agent-gateway` 负责把“我要某个逻辑角色的模型”变成一个 LangChain 可调用的 chat model。

它的主线是：

```text
role_name / model_override
  -> ModelResolver 读取角色配置
  -> 生成 provider/model 候选链
  -> 返回 GatewayChatModel
  -> GatewayChatModel 调 provider
  -> provider 失败时按候选链 fallback
```

它不解析 skill，不调度 phase，不管理 `data` 黑板，也不决定 child skill 在哪里。

## 2. 核心术语

### role_name

`role_name` 是业务侧想要的模型角色。

例如：

```text
planner
writer
critic
balanced
```

它不是 provider 名，也不是具体模型名。resolver 会根据配置把它解析成候选模型链。

### model_override

`model_override` 是调用方强制指定某个模型 code。

如果 override 命中配置里的 model，resolver 会直接用这个模型的 provider chain；如果没命中，当前源码会记录 warning，然后退回 role-based resolution。

### ResolvedRole

`ResolvedRole` 是配置解析后的角色结果。它里面最关键的是 `call_chain`：一个 provider/model 候选列表。

例子：

```text
role = "writer"
call_chain =
  1. openai/gpt-x
  2. anthropic/claude-y
  3. openrouter/model-z
```

resolver 只负责组装这个候选链；真正调用和 fallback 发生在 `GatewayChatModel`。

### GatewayChatModel

`GatewayChatModel` 是 LangChain `BaseChatModel` 兼容 adapter。

Agent runtime 只需要把它当 chat model 调用。它内部会负责：

- 把 LangChain messages 转成 provider 请求。
- 带上 max tokens、temperature、reasoning、tools 等参数。
- 调用候选 provider。
- provider 失败时切下一个。
- 成功后把 provider 响应转回 LangChain `AIMessage`。

## 3. resolver 怎么解析模型

一次解析大致是这样：

1. 调用方传入 `role_name`，可选 `thinking_enabled`、`model_override`、callbacks、phase name。
2. resolver 读取角色配置。
3. 如果 `model_override` 命中配置，就使用 override 对应的模型链。
4. 否则按 `role_name` 找角色。
5. 如果角色配置存在，追加 peer model fallback 候选。
6. 如果角色配置不存在，当前会退到最小模型工厂。
7. 返回一个 `GatewayChatModel`。

例子：

```text
resolve(role_name="writer")
  -> writer 对应 primary_model = claude
  -> peer group 里还有 gpt
  -> GatewayChatModel(call_chain=[anthropic/claude, openai/gpt])
```

如果调用方没有传 role，resolver 会使用默认角色；默认值可以由环境变量覆盖，否则是 `balanced`。

## 4. provider fallback 怎么发生

`GatewayChatModel` 被调用时，会按候选链逐个尝试。

流程是：

```text
for candidate in call_chain:
  如果 provider/model 已标记 down，跳过
  如果启用 probe 且 probe 失败，标记 down 并跳过
  真正调用 provider
  成功：返回 AIMessage
  失败：记录失败，标记 down，发 fallback event，试下一个

全部失败：抛 RuntimeError
```

例子：

```text
候选链:
  1. openai/gpt-a
  2. anthropic/claude-b

openai/gpt-a 超时
  -> 标记 openai/gpt-a down
  -> 发 llm_fallback 事件: from openai/gpt-a to anthropic/claude-b
  -> 调 anthropic/claude-b

anthropic/claude-b 成功
  -> 返回模型结果
```

如果两个都失败，最终错误大致是：

```text
All LLM fallback candidates failed for role=writer: ...
```

当前这里仍是普通 `RuntimeError` 文本，不是统一的结构化 gateway error。

## 5. tools 是怎么绑定的

Agent runtime 通常会调用 `chat_model.bind_tools(tools)`。

`GatewayChatModel.bind_tools()` 不会立刻调用 provider。它会返回一个携带工具 schema 的新模型对象。后续真正 `_generate()` 时，工具信息才会传给 provider 调用。

例子：

```text
原模型:
  GatewayChatModel(role="writer")

绑定工具:
  bind_tools([finish_task, search])

得到:
  GatewayChatModel(role="writer", bound_tools=[finish_task, search])
```

## 6. usage 和响应怎么返回

provider 返回后，gateway 会把结果转成 LangChain `ChatResult`。

它会尽量保留：

- content。
- tool calls。
- reasoning content。
- provider。
- model。
- finish reason。
- token usage。

例子：

```json
{
  "content": "Done",
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 5
  },
  "tool_calls": []
}
```

会变成一个 `AIMessage`，并在 metadata 里带 provider/model/usage。

## 7. Predict 模式怎么短路真实调用

resolver 上如果挂了 predict mock strategy，就不会返回普通 `GatewayChatModel`，而是返回 predict 版本的 gateway chat model。

人话就是：

```text
正常模式:
  resolver -> GatewayChatModel -> 真实 provider

Predict 模式:
  resolver -> PredictGatewayChatModel -> mock strategy
```

这样可以复用同一套模型接口，但不真的打外部 provider。

## 8. 当前和 runtime 的关系

当前 graph skill runtime 主线还没有把生产级 `ModelResolver` 作为强 DI 接进 Agent phase。

graph skill path 主要靠 `mock_llm` 传入 chat model。没有传 chat model 时，Agent phase 会在运行期失败。

也就是说，gateway 代码本身已经能解析和调用 provider，但当前 graph skill 主路径还没有完整使用它作为生产模型注入边界。

## 9. 最容易误解的点

### resolver 不负责真正 fallback

resolver 只是组装候选链。真实 provider 调用失败后切下一个，是 `GatewayChatModel` 做的。

### role 不是模型名

`writer`、`critic` 这类 role 会被配置解析成模型链。它们不等同于 provider 的模型 id。

### 全部失败当前不是结构化 gateway error

当前全失败会抛普通 `RuntimeError` 文本。目标态里的结构化错误码还没有完全落地。

### gateway 不管理业务 state

gateway 只消费 messages 并返回模型回复。它不读写 `BlackboardState.data`。

## 10. 总图

```text
role_name / model_override
  -> ModelResolver
  -> RoleConfigData
  -> ResolvedRole.call_chain
  -> GatewayChatModel
  -> provider probe / dispatch
  -> fallback event on failure
  -> ChatResult / RuntimeError
```
