# state-and-io-contract 运行逻辑人话版

署名：Codex  
日期：2026-05-23  
定位：只解释当前源码真实怎么运行，不做源码导览，不讲实现写法。

## 1. 一句话结论

这个模块的核心任务，是给 graph-agent 的运行过程加一层“黑板边界”。

整张图运行时共享一份状态，最重要的是业务数据 `data`。运行入口会把用户输入直接放进 `data`；每个 phase 执行后，再把自己产生的变化合回 `data`。

如果某个 phase 声明了 `io.inputs` / `io.outputs`，系统会在它外面套一层边界：

- 运行前：只把 `io.inputs.properties` 声明过的字段交给它。
- 运行后：只允许它写 `io.outputs.properties` 声明过的字段。
- 合并时：如果新结果写了全局 `data` 里已经存在的顶层 key，就报冲突。

所以它不是旧版 `context_mapping`。它不做字段重命名，不做复杂转换，也不负责完整 JSON Schema 校验。它更像“phase 能看什么、能写什么”的门禁。

## 2. 先把术语讲清楚

### BlackboardState

`BlackboardState` 可以理解成整张运行图共用的一块黑板。每个 phase 都围绕这块黑板运行。

它主要分四个区：

| 区域 | 人话解释 |
|---|---|
| `data` | 业务数据区。外部输入、LOGIC 结果、SUBGRAPH 结果、Agent 完成结果，最终都会以某种形式进入这里。 |
| `flow` | 框架控制区。比如 `finish_task` 的工具结果、subagent 校验重试次数、critic 指标。它不是主要业务输出。 |
| `messages` | LLM 对话历史。主要给 Agent / SKILL phase 使用。 |
| `run_id` | 本次运行的标识，用来串起 trace、父子调用和日志。 |

### data

`data` 是业务黑板。运行开始时，用户传给 `run_skill()` 的输入会直接放进这里。

例如用户输入：

```json
{
  "topic": "solar energy",
  "draft": "old text",
  "debug": true
}
```

初始 `data` 就是：

```json
{
  "topic": "solar energy",
  "draft": "old text",
  "debug": true
}
```

当前入口不会先按根级 `io.inputs` 删除 `debug`，也不会自动检查 `topic` 是不是 string，或者给缺失字段填默认值。

### flow

`flow` 是运行控制信息。

例如 Agent 调用 `finish_task` 后，工具返回值会记录在 `flow.finish_task_result`。subagent 参数校验失败时，重试次数会记录在 `flow.subagent_validation_retries`。这些信息帮助引擎继续运行和诊断问题，但不应该当成主要业务产物。

### messages

`messages` 是对话历史。

Agent phase 会把 system prompt 放到前面，再接上已有 messages，然后开始 LLM 工具调用循环。模型回复、工具结果、`finish_task` 调用结果都会追加进去。

SUBGRAPH 和 subagent child graph 会从空 messages 开始，不继承父 Agent 的聊天历史。

### reducer

reducer 是 LangGraph 合并状态的规则。

当前 `data` 的 reducer 很保守：新结果里的顶层 key 只要已经存在于旧 `data`，就报冲突。它不是普通 dict update，也不是最后写入者覆盖前者。

### StateMapper

`StateMapper` 是这个模块最核心的边界组件。

它只做两件事：

1. phase 运行前，按 `io.inputs` 从全局 `data` 里切出局部 `data`。
2. phase 运行后，按 `io.outputs` 检查返回的 `data` 字段。

它只看 JSON Schema 顶层 `properties` 的字段名。当前它不处理 `required`、类型转换、默认值、嵌套 schema 校验。

### PhaseWrapper

`PhaseWrapper` 是把 `StateMapper` 套到 phase 外面的壳。

有这个壳的 phase，运行顺序是：

```text
全局 state
  -> 按 io.inputs 切一份 phase-local state
  -> 执行真正的 phase
  -> 按 io.outputs 检查 phase 返回值
  -> 交给 LangGraph 合并
```

当前源码里，只有 phase AST 上真的带 `io` 的节点才会套上这层 wrapper。Agent 和 SUBGRAPH 可以带 `io`；LOGIC 当前没有 phase-level `io` 字段，所以通常不会经过这层输入切片。

## 3. 一次运行从哪里开始

一次 skill 运行，大致是这样：

1. 运行入口收到用户输入。
2. 编译器读取 `GRAPH.md`、phase 文件、根级 IO schema、phase 配置和 subagent 配置。
3. 引擎把每个 phase 装成 LangGraph 节点，并按依赖关系连成图。
4. 初始状态被创建出来：`data` 放用户输入，`flow` 是空对象，`messages` 是空列表，`run_id` 是本次运行 ID。
5. LangGraph 按依赖顺序执行 phase。
6. 每个 phase 返回自己的状态变化。
7. reducer 把这些变化合回全局 `BlackboardState`。
8. 运行结束后，最终 `data` 作为主要上下文返回。

根级 IO schema 当前更多是编译期和部分运行节点的参考：它会被读取和校验，也会参与 LOGIC 输出 key 检查、终点 Agent 的 `finish_task` 输出校验、subagent 入参模型生成。但运行入口不会先用它把用户输入严格漏斗化。

## 4. phase 输入是怎么被切出来的

当某个 phase 带有 `io.inputs` 时，系统不会把整张 `data` 黑板交给它，而是只给它一份切片。

假设全局 `data` 是：

```json
{
  "topic": "solar energy",
  "draft": "old text",
  "debug": true
}
```

某个 Agent phase 的 `io.inputs` 声明了：

```json
{
  "type": "object",
  "properties": {
    "topic": {},
    "draft": {}
  }
}
```

那么这个 phase 看到的局部 `data` 是：

```json
{
  "topic": "solar energy",
  "draft": "old text"
}
```

`debug` 没有声明，所以不会进入这个 phase 的局部 `data`。

再看一个容易误解的例子：

```json
{
  "type": "object",
  "properties": {
    "topic": { "type": "string" }
  },
  "required": ["topic"]
}
```

当前 `StateMapper` 只会看 `properties` 里的字段名 `topic`。它不会在这一层检查 `topic` 的类型，也不会因为 `required` 缺失而在这里报错。

如果 schema 没有可读的 `properties`，当前实现会把原始输入复制过去，而不是报错。

## 5. phase 输出是怎么被拦住的

phase 跑完后，如果返回值里有 `data`，`StateMapper` 会检查它写了哪些字段。

假设 phase 的 `io.outputs` 声明了：

```json
{
  "type": "object",
  "properties": {
    "summary": {},
    "score": {}
  }
}
```

如果 phase 返回：

```json
{
  "data": {
    "summary": "usable",
    "score": 0.8
  }
}
```

这会通过，因为 `summary` 和 `score` 都声明过。

如果 phase 返回：

```json
{
  "data": {
    "summary": "usable",
    "internal_note": "not declared"
  }
}
```

这会被拦住，因为 `internal_note` 没有出现在 `io.outputs.properties` 里。

Agent / SKILL phase 有一个特殊形状。它通过 `finish_task` 成功完成时，业务结果通常会包在自己的 phase 名字下面：

```json
{
  "data": {
    "analyze": {
      "summary": "usable",
      "score": 0.8
    }
  }
}
```

输出检查会识别这种“单个 phase 名字包一层业务结果”的形状，然后检查里面的 `summary`、`score` 是否在 `io.outputs` 声明范围内。

## 6. data 合并为什么会冲突

phase 返回的 `data` 不会直接覆盖全局 `data`。它要经过 `data` 的 reducer。

当前 reducer 的规则是：

- 旧数据为空，就接收新数据。
- 新数据为空，就保留旧数据。
- 新数据里的顶层 key 如果旧数据已经有了，就立刻报冲突。
- 只有完全新增的顶层 key 才会被合进去。

### 例子一：新增字段可以合并

运行前全局 `data` 是：

```json
{
  "topic": "solar energy"
}
```

某个 phase 返回：

```json
{
  "data": {
    "summary": "clean energy source"
  }
}
```

合并后是：

```json
{
  "topic": "solar energy",
  "summary": "clean energy source"
}
```

因为 `summary` 是新增顶层 key。

### 例子二：顺序更新已有字段也会冲突

运行前全局 `data` 是：

```json
{
  "draft": "old text"
}
```

某个 phase 返回：

```json
{
  "data": {
    "draft": "new text"
  }
}
```

直觉上这像是“更新草稿”，但当前 reducer 不这么看。它只看到新结果写了已有顶层 key `draft`，于是报冲突。

所以当前系统更适合让 phase 产出新字段，例如：

```json
{
  "data": {
    "revised_draft": "new text"
  }
}
```

而不是反复覆盖 `draft`。

### 例子三：两个并行分支写同一个 key 会冲突

假设两个并行 phase 都从同一个输入开始：

```json
{
  "topic": "solar energy"
}
```

分支 A 返回：

```json
{
  "data": {
    "analysis": { "sentiment": "positive" }
  }
}
```

分支 B 也返回：

```json
{
  "data": {
    "analysis": { "risk": "low" }
  }
}
```

这也会冲突。当前 reducer 不会把两个 `analysis` 深层合并成：

```json
{
  "analysis": {
    "sentiment": "positive",
    "risk": "low"
  }
}
```

它只看顶层 key，发现两个结果都写 `analysis`，就停止。

### 例子四：Agent phase 名字也可能成为冲突 key

Agent 完成后通常写：

```json
{
  "data": {
    "analyze": {
      "summary": "usable"
    }
  }
}
```

这里的顶层 key 是 `analyze`。如果全局 `data` 里已经有 `analyze`，或者另一个分支也写 `analyze`，同样会冲突。

## 7. 四类运行边界分别怎么走

### LOGIC phase

LOGIC phase 是确定性的 Python 动作。

它会拿到一份 `Context`，里面是当前 `data` 的复制。动作可以通过这个上下文读写业务数据，也可以直接返回一个 dict。运行时会比较动作前后的数据，算出变化量，再把变化量作为 `data` delta 返回。

例子：

```text
运行前 data:
  {"topic": "Solar Energy"}

LOGIC 动作把 clean_topic 写进 Context:
  clean_topic = "solar energy"

返回给 LangGraph 的 delta:
  {"data": {"clean_topic": "solar energy"}}
```

当前要注意两点：

- LOGIC 当前通常不经过 `StateMapper` 的 phase-level 输入切片，因为它的 AST 没有 `io` 字段。
- LOGIC 的返回 key 和上下文写 key 仍可能受到根级 output schema 的检查，但这是另一层约束，不等同于 phase-level IO wrapper。

### Agent phase

Agent phase 是 LLM 驱动的节点。

它不会像 LOGIC 一样拿到 Python `Context`。它主要看到的是 system prompt、已有 messages、业务工具、critic 工具、subagent 工具和 `finish_task`。

运行流程是：

```text
准备 system prompt 和 messages
  -> 模型回复
  -> 如果模型调用工具，就执行工具并把结果追加进 messages
  -> 如果模型调用 finish_task，就解析 Markdown 并校验输出
  -> finish_task 成功时，把业务结果写到 data[phase_id]
```

例子：phase 名叫 `review`，模型调用 `finish_task` 后得到：

```json
{
  "ok": true,
  "data": {
    "verdict": "pass",
    "reason": "schema is complete"
  }
}
```

运行时写回的业务 `data` 形状是：

```json
{
  "review": {
    "verdict": "pass",
    "reason": "schema is complete"
  }
}
```

完整的 `finish_task` 工具结果还会进入 `flow.finish_task_result`。

一个容易误解的点是：当前 Agent loop 不会自动把 `state.data` 渲染成一段用户消息塞给模型。phase input 切片会进入 Agent 的运行状态，但模型能不能“看见”这些业务数据，取决于 prompt、工具和后续设计有没有把它暴露出来。

### SUBGRAPH phase

SUBGRAPH phase 会启动另一个完整 skill graph。

它会用当前 phase-local `data` 作为子图初始 `data`，用空 messages 启动子图，并沿用当前 run_id。子图跑完后，父节点会比较“子图运行前的数据”和“子图运行后的数据”，只把差异作为自己的输出 delta 返回。

例子：

```text
父 phase-local data:
  {"chapter": "text"}

子图运行后 data:
  {"chapter": "text", "events": ["A meets B"]}

SUBGRAPH 返回给父图的 delta:
  {"data": {"events": ["A meets B"]}}
```

如果 SUBGRAPH phase 外面有 `StateMapper`，子图初始 `data` 会先被父 phase 的 `io.inputs` 限制；如果没有这层 wrapper，子图就可能拿到更大的父图黑板。

### subagent tool

subagent 是 Agent 里可以调用的子 agent，看起来像一个工具，名字通常是 `call_subagent_xxx`。

它的入参不是随便传的。编译阶段会读取目标 child skill 的根级 `io.inputs`，生成一个入参模型。运行时，父 Agent 调用 subagent tool 时，必须传 `inputs` 数组，每个元素都要符合这个模型。

例子：父 Agent 调用 subagent：

```json
{
  "inputs": [
    { "scene_text": "A enters the room." },
    { "scene_text": "B leaves quietly." }
  ]
}
```

校验通过后，每个数组元素会启动一次 child graph。child graph 的初始 `data` 当前由“父 phase-local data + 显式传入的 input”组成，messages 从空开始。多个 child run 会并发执行，但有并发上限。

subagent 的结果不会自动写回父图 `data`。它只是作为 tool result 返回给父 Agent。父 Agent 后面要不要把这些结果写进自己的 `finish_task`，由父 Agent 决定。

subagent 还有一个嵌套深度限制：当前只允许一层 subagent。subagent 里面再调用 subagent 会被阻止。

## 8. ReaderSandboxState 是什么

`ReaderSandboxState` 是给 builtin reference reader 准备的一种隔离状态。

它生成的是一份很小的黑板，只包含当前 skill、phase、超时控制、空 messages 和空 run_id。它的目的不是继承父图业务数据，而是让 reference reader 这类装配期能力有一个干净的临时运行环境。

当前源码里，这个类表达的是隔离状态的形状；它不是普通 runtime phase，也不是会自动读取父图 `data` 的节点。

## 9. 当前最容易误解的点

### `io.inputs` 不是字段映射表

它不会做重命名，也不会把 `a.b.c` 映射成 `x`。当前只按顶层 property 名字过滤。

### `io.outputs` 不是完整 JSON Schema 执行器

`StateMapper` 当前只用它检查输出字段名。字段类型、required、嵌套结构等完整校验，不在这层完成。

### 根级 `io.inputs` 不等于运行入口漏斗

当前用户传入 `run_skill()` 的参数会直接进入初始 `data`。根级输入 schema 会被编译和复用，但不是入口处的强制过滤器。

### Agent 的 `data[phase_id]` 是有意的形状

Agent 通过 `finish_task` 完成任务时，业务结果会挂在自己的 phase 名字下面。这和 LOGIC 常见的顶层 delta 不同。

### subagent 不会自动改父黑板

subagent child graph 的结果只是工具返回值。父 Agent 必须在自己的最终结果里显式采用这些信息，它们才会进入父 phase 的业务输出。

### `data` 合并不是 update

写已有顶层 key 会报冲突。不要把当前 `data` reducer 理解成普通 dict update。

## 10. 错误通常停在哪里

| 场景 | 系统反应 |
|---|---|
| phase 写了未声明输出字段 | `StateMapper` 在结果回到全局状态前拦住，抛运行期 fatal。 |
| 新结果写了已有顶层 `data` key | reducer 抛 state conflict fatal。 |
| `finish_task` Markdown 解析或 schema 校验失败 | `finish_task` 返回 `ok: false` 的工具结果，不写业务 `data`。 |
| subagent 入参不符合目标 schema | subagent tool 返回校验失败结果，让父 Agent 有机会重试。 |
| subagent 校验重试超过上限 | 转成 fatal。 |
| subagent 嵌套超过深度限制 | 转成 fatal。 |
| 带 wrapper 的 phase 内部抛普通异常 | wrapper 会统一包装成运行期 state mapping 失败。 |

## 11. 总图

当前真实运行模型可以压缩成这条链：

```text
run_skill 输入
  -> 初始 BlackboardState.data
  -> LangGraph 按依赖执行 phase
  -> 有 io 的 phase 先被 StateMapper 切输入
  -> phase 运行
  -> 有 io 的 phase 再被 StateMapper 查输出
  -> data reducer 合并业务 delta
  -> 最终 data 作为 context 返回
```

更短地说：

> `BlackboardState` 是全局黑板；`StateMapper` 是 phase 边界门禁；`PhaseWrapper` 负责把门禁套到节点外面；reducer 决定业务结果能不能合并；SUBGRAPH 和 subagent 是启动 child graph 的两种方式，但 subagent 结果默认只是工具返回值，不会直接改父图黑板。
