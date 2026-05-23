# execution-runtime 运行逻辑人话版

署名：Codex  
日期：2026-05-23  
定位：只解释当前执行运行时真实怎么运行，不做源码导览，不讲实现写法。

## 1. 一句话结论

`execution-runtime` 负责把已经编译好的 skill 真正跑起来。

它的主线是：

```text
run_skill()
  -> 判断这是 graph skill 还是 legacy SKILL.md
  -> graph skill 走 compile_skill()
  -> assemble_graph()
  -> graph.invoke(initial_state)
  -> 返回 WorkflowResult
```

编译器负责把文件变成 `CompiledSkill`；runtime 负责把 `CompiledSkill` 装成 LangGraph，并执行每个 phase。

## 2. 运行入口怎么分流

公开入口是 `run_skill()`。它会把成功结果包装成 `WorkflowResult`，失败时如果是已知 GraphAgent 错误，也会包装成失败的 `WorkflowResult`。

当前有两条运行路径：

| 输入形状 | 当前走向 |
|---|---|
| 传入目录，目录里有 `GRAPH.md` | 走当前 graph skill 路径。 |
| 传入 legacy `SKILL.md` 文件 | 走旧 harness 路径。 |

本解释主要讲 graph skill 路径。

例子：

```text
run_skill("/skills/demo_graph", topic="solar")

/skills/demo_graph/
  GRAPH.md
  phases/

=> 走 graph skill 路径
```

## 3. 初始 state 怎么创建

graph skill 路径会先编译 skill，再装配 LangGraph，然后创建初始 state。

初始 state 大概是：

```json
{
  "data": {
    "topic": "solar"
  },
  "flow": {},
  "messages": [],
  "run_id": "本次运行 id"
}
```

这里要注意：用户输入会直接进入 `data`。当前不会先按根级 input schema 做运行入口过滤。

如果调用方传了 `thread_id`，它会被当作 run id；否则运行时会生成一个新的 id。

## 4. graph 是怎么装起来的

`assemble_graph()` 会拿到 `CompiledSkill`，创建一张 LangGraph。

它做三件事：

1. 给每个 phase 加一个节点。
2. 根据 `depends_on` 加边。
3. 找到没有下游依赖的 terminal phase，连到 END。

例子：

```yaml
phases:
  - id: prepare
    depends_on: []
  - id: analyze
    depends_on: [prepare]
  - id: report
    depends_on: [analyze]
```

会变成：

```text
START -> prepare -> analyze -> report -> END
```

如果两个 phase 都不依赖任何 phase，它们都会从 START 出发，LangGraph 会把它们作为并行分支处理。

## 5. phase 节点怎么选择执行器

每个 phase 的 AST 类型决定运行方式：

| phase 类型 | 当前运行方式 |
|---|---|
| LOGIC | 调 Python action，算出 `data` delta。 |
| Agent / SKILL | 跑 LLM 工具循环，通常用 `finish_task` 结束。 |
| SUBGRAPH | 编译并运行另一个 child graph，再把 child graph 的差异作为结果返回。 |

如果 phase AST 上带 `io`，runtime 会先用 `PhaseWrapper` 套一层输入/输出边界。没有 `io` 的 phase 直接运行原始节点。

## 6. LOGIC phase 怎么跑

LOGIC phase 会把当前 `data` 复制一份，包成 `Context` 给 Python action。

action 有两种写结果方式：

1. 修改 Context 里的数据。
2. 直接返回 dict。

runtime 会把 action 前后的数据做对比，得到变化量。

例子：

```text
运行前 data:
  {"topic": " Solar "}

action 写入:
  clean_topic = "Solar"

返回 delta:
  {"data": {"clean_topic": "Solar"}}
```

如果 action 直接返回：

```json
{
  "clean_topic": "Solar"
}
```

也会被合进 delta。

如果根级 output schema 声明了允许输出 key，LOGIC 返回 dict 的 key 还会被这层静态约束检查。

## 7. Agent / SKILL phase 怎么跑

Agent phase 是 LLM 工具循环。

它会准备：

- system prompt。
- 当前 messages。
- business tools。
- critic/reviewer/auditor 这类 framework tools。
- subagent tools。
- `finish_task` 工具。

然后进入循环：

```text
模型 invoke(messages)
  -> 如果没有 tool call，循环结束
  -> 如果有 tool call，逐个执行工具
  -> 工具结果作为 ToolMessage 追加到 messages
  -> 如果工具是 finish_task，就返回 phase 结果
```

例子：模型调用 `finish_task`，工具返回：

```json
{
  "ok": true,
  "data": {
    "answer": "Solar is renewable."
  }
}
```

phase 名叫 `answer` 时，runtime 返回的业务 delta 是：

```json
{
  "data": {
    "answer": {
      "answer": "Solar is renewable."
    }
  }
}
```

同时，完整的 `finish_task` 结果会放进 `flow.finish_task_result`。

如果 `finish_task` 返回 `ok: false`，runtime 不写业务 `data`，但工具结果仍会进入 messages 和 flow。

## 8. finish_task 做什么

`finish_task` 是 Agent 告诉 runtime“这个 phase 完成了”的工具。

它接收 Markdown。runtime 会尝试把 Markdown 解析成 dict，再按输出 schema 校验。

例子：

```markdown
## answer
Solar is renewable.

## confidence
0.8
```

如果输出 schema 有 `answer` 和 `confidence`，解析后大致变成：

```json
{
  "answer": "Solar is renewable.",
  "confidence": 0.8
}
```

解析或校验失败时，工具返回结构化错误；如果配置了 patcher，可能尝试让模型修补 Markdown。

## 9. SUBGRAPH phase 怎么跑

SUBGRAPH phase 会启动另一个完整 skill graph。

流程是：

```text
拿当前 state.data 作为 before_data
  -> 用 before_data 启动 child graph
  -> child graph messages 从空开始
  -> child graph 跑完
  -> 对比 before_data 和 child result data
  -> 把差异作为父 phase 的 data delta
```

例子：

```text
父 data:
  {"chapter": "text"}

child graph 最终 data:
  {"chapter": "text", "events": ["A meets B"]}

SUBGRAPH 返回:
  {"data": {"events": ["A meets B"]}}
```

SUBGRAPH 的 `flow` 也会从 child result 带回父图。

## 10. subagent tool 怎么跑

subagent 是 Agent phase 里的工具，不是 graph 拓扑上的普通 phase。

父 Agent 调用 subagent tool 时，参数必须是：

```json
{
  "inputs": [
    { "scene_text": "A enters." }
  ]
}
```

每个 input item 会触发一次 child graph run。当前 child graph 的初始 `data` 是：

```text
父 phase-local data + 这个 input item
```

child graph 从空 messages 开始，并带着父 run id 相关 metadata。多个 input item 会并发执行，但有并发上限。

subagent 返回的是 tool result，不会直接 patch 父图 `data`。父 Agent 必须在后续 `finish_task` 里采用这些结果，它们才会进入父 phase 输出。

## 11. callbacks 和 trace 当前在哪里断开

当前 graph skill dict runner 接收 `callbacks` 参数，但会直接丢弃它。也就是说，这条新 graph path 目前不会像 legacy harness 那样自动把 phase start、tool call、LLM call 等事件写进 callback trace。

但 subagent child graph 的 RunnableConfig 会保留 parent config 里的 callbacks。如果外层调用确实通过 LangGraph config 传了 callbacks，child run 可以继续带上这些 callback metadata。

这和目标态“runtime 主线完整发 trace event”不同。

## 12. 错误怎么返回

公开 `run_skill()` 只捕获 GraphAgent 系列错误，并包装成 `WorkflowResult(success=False)`。

普通 Python 异常不一定会被包装；它可能直接向上抛。

例子：

```text
SkillLoadError
  -> 返回 success=False 的 WorkflowResult

RuntimeError
  -> 可能直接冒泡
```

Agent phase 没有 chat model 时，当前会抛运行错误。因为 graph skill dict runner 只有在传了 `mock_llm` 时才把它作为 chat model；没有真实 model resolver 注入路径。

## 13. 最容易误解的点

### runtime 不重新解析 Markdown

Markdown 已经在 compilation 阶段被解析成 AST。runtime 消费的是编译产物。

### callbacks 参数当前没有接入 graph skill dict runner

这条路径会 `del callbacks`。所以不要以为传了 `TracingCallback` 就一定会得到完整 graph skill trace。

### Agent 不会自动看到 data 文本

Agent state 里有 phase-local data，但模型能不能看到，要看 prompt 和工具是否暴露这些数据。

### subagent 结果不会自动写父 data

subagent 是工具调用。它的结果先回到父 LLM，不直接进入父图业务黑板。

## 14. 总图

```text
run_skill()
  -> _run_skill_dict()
  -> graph skill path
  -> compile_skill()
  -> assemble_graph()
  -> StateGraph(BlackboardState)
  -> LOGIC / Agent / SUBGRAPH nodes
  -> graph.invoke(initial_state)
  -> result.data -> WorkflowResult.context
```
