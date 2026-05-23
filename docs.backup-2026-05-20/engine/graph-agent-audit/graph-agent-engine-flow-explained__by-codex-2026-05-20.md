# graph-agent 引擎运行流程人话版

署名：Codex
日期：2026-05-20
范围：`/home/sevenx/coding/agent-harness/packages/graph-agent`
定位：解释当前 V2.1 engine 真实怎么跑，不是理想设计稿

## 0. 阅读路径

这份文档比较长，可以按目标跳读：

- 完全没接触 V2.1：读“1. 先给结论” -> “2. 术语先讲清楚” -> “3. 整体运行流程” -> “26. 最后的总图”。
- 想知道 context / data 怎么流：直接看“9. 重点一：context / data 到底怎么流”。
- 想用 subagent：直接看“15. 重点二：agent phase 里的 subagent 怎么调用”。
- 写新 skill 前：看“23. 当前最容易误解的 8 件事” + “25. 当前设计上的实际建议”。

## 1. 先给结论

当前 `graph-agent` 的主线已经不是旧版“单个 `SKILL.md` + 每个节点写 `context_mapping`”。

当前 V2.1 的真实模型是：

```text
一个 skill 目录
  -> 编译成一张图
  -> 图里每个 phase 是一个节点
  -> 所有节点共享一个业务数据黑板 data
  -> 节点读 data，产出变化 delta
  -> 引擎把 delta 合回 data
  -> 最后把 data 作为运行结果返回
```

一句话：

> 这个 engine 现在更像“按 GRAPH.md 图纸跑一条流水线”。每个节点都能看见同一个数据黑板，节点只把自己新增或改变的字段交回去。

## 2. 术语先讲清楚

### skill

一个可运行任务包。

V2.1 里它必须是一个目录，不是单个文件。

最小结构大概是：

```text
my_skill/
├── GRAPH.md
├── io/
│   ├── inputs.json
│   └── outputs.json
└── phases/
    ├── prepare/
    │   └── LOGIC.md
    └── analyze/
        └── SKILL.md
```

### GRAPH.md

整张流程图。

它告诉引擎：

- 输入 schema 在哪里。
- 输出 schema 在哪里。
- 有哪些 phase。
- 哪些 phase 先跑，哪些 phase 后跑。
- phase 文件夹在哪里。

### phase

流程里的一个节点。

V2.1 里有三种 phase：

- `LOGIC`：普通 Python 逻辑，不问大模型。
- `SKILL`：大模型 agent 节点，会调用工具，最后调用 `finish_task`。
- `SUBGRAPH`：调用另一个完整 skill 子图。

### data

业务数据黑板。

比如：

```json
{
  "text": "hello",
  "clean_text": "hello",
  "analysis": {
    "sentiment": "positive"
  }
}
```

所有 phase 主要读写的就是它。

### flow

框架自己的控制数据。

比如：

- 当前 `finish_task` 结果。
- subagent 重试次数。
- subagent 嵌套深度。
- critic 工具统计。

业务代码通常不应该依赖它。

当前常见 sub-key：

| key | 人话解释 |
|---|---|
| `finish_task_result` | 当前 SKILL phase 最近一次 `finish_task` 的返回值。 |
| `subagent_depth` | subagent 嵌套深度。当前有 bug：它写进 config metadata，但没真正写进 child flow。 |
| `subagent_validation_retries` | 每个 subagent tool 的入参校验重试次数。 |
| `critic_metrics` | critic / reviewer / auditor 这类工具的调用统计。 |
| `metrics` / `trace_path` | legacy harness 时代常见的指标和 trace 信息，V2.1 主线不一定填。 |

### messages

大模型对话历史。

只有 `SKILL` phase 主要使用它。

### delta

一个 phase 跑完后交回来的“变化量”。

例如跑前：

```json
{"text": " Hello "}
```

跑后：

```json
{"text": " Hello ", "clean_text": "Hello"}
```

那么 delta 是：

```json
{"clean_text": "Hello"}
```

### reducer

合并器。

LangGraph 需要知道多个节点返回的结果怎么合回 state。

当前 `data` 的 reducer 是 `shallow_dict_merge`。它现在有一个问题：只要新 delta 写了已有 key，就会报冲突。这个设计本来是为了挡并行分支冲突，但也误伤了顺序更新。

当前几个主要字段的合并行为：

| 字段 | 合并方式 | 人话解释 |
|---|---|---|
| `data` | `shallow_dict_merge` | 合并顶层业务字段；当前顺序更新已有 key 也会冲突。 |
| `messages` | LangGraph `add_messages` | 追加合并对话消息。 |
| `flow` | 没有显式 reducer | 通常是后返回的值覆盖前值；并行场景下要谨慎。 |

### schema

数据结构说明书。

`io/inputs.json` 描述输入长什么样。

`io/outputs.json` 描述最终输出长什么样。

当前注意点：

- `inputs.json` 主要用于编译期检查和 subagent 入参模型。
- `outputs.json` 会用于终点 `SKILL` phase 的 `finish_task` 输出校验。
- 当前 V2.1 `run_skill(**inputs)` 不会严格按 `inputs.json` 自动校验 runtime 输入。
- 当前 `run_skill(**inputs)` 也不会按 `inputs.json` 过滤 runtime 参数。你传什么 keyword 参数，基本都会原样进入 `data`。
- schema 约束目前主要在三处生效：编译期 schema 合法性检查、subagent tool 入参校验、终点 SKILL phase 的 `finish_task` 输出校验。

### finish_task

大模型告诉引擎“这个 phase 完成了，这是最终结果”的工具。

在 `SKILL` phase 里，大模型不是直接改 `data`。它需要调用 `finish_task`，引擎再把结果写回 `data`。

### subagent

`SKILL` phase 里可以调用的子 agent。

它看起来像一个工具：

```text
call_subagent_xxx
```

但背后实际会启动另一个完整 skill 子图。

## 3. 整体运行流程

完整链路可以分成 5 大步：

```text
1. 用户调用 run_skill()
2. 引擎编译 skill 目录
3. 引擎把 skill 装配成 LangGraph
4. LangGraph 按拓扑执行 phase
5. 返回最终 data
```

下面一层层拆。

## 4. 第 1 步：用户调用 run_skill()

用户代码大概是：

```python
run_skill(skill_root, text="hello")
```

当前 V2.1 主线会把它变成初始 state：

```json
{
  "data": {
    "text": "hello"
  },
  "flow": {},
  "messages": [],
  "run_id": "本次运行 ID"
}
```

人话：

> 你传给 `run_skill()` 的关键字参数，基本会直接放进业务黑板 `data` 里。

注意：

当前不是这样：

```text
inputs.json
  -> 自动变成 phase1.input
  -> phase1.output 自动映射给 phase2.input
```

而是这样：

```text
run_skill 参数
  -> data 黑板
  -> 所有 phase 都能读 data
  -> phase 返回 delta
  -> delta 合回 data 黑板
```

## 5. 第 2 步：编译 skill 目录

编译就是“读文件 + 检查格式 + 建立内部对象”。

引擎会读：

```text
GRAPH.md
io/inputs.json
io/outputs.json
phases/*/LOGIC.md
phases/*/SKILL.md
phases/*/SUBGRAPH.md
actions/*.py
tools/*.py
subskills/*/GRAPH.md
```

编译阶段主要做这些事：

1. 确认根目录有 `GRAPH.md`。
2. 确认 `GRAPH.md` 里声明的 phase 都存在。
3. 确认 phase 依赖没有环。
4. 确认 `io/*.json` 是合法 JSON Schema。
5. 确认每个 phase 只能是三种之一：`LOGIC` / `SKILL` / `SUBGRAPH`。
6. 加载 LOGIC 的 Python action。
7. 加载 SKILL 的 tools。
8. 扫描 actions/tools 有没有危险文件写入等操作。
9. 编译 subagent 信息。
10. 可选写编译缓存。

人话：

> 编译阶段不是真正跑任务，而是确认这份任务说明书能不能被 engine 看懂。

纯净性扫描当前具体禁止的是本地写入和文件系统变更：

- `open(..., "w")`、`open(..., "a")`、`open(..., "x")`、`open(..., "+")` 这类可能写文件的模式。
- `Path.write_text()`、`Path.write_bytes()`、`Path.mkdir()`、`Path.unlink()`、`Path.rename()` 等 Path 变更 API。
- `os.remove()`、`os.rename()`、`os.makedirs()`、`os.mkdir()`、`os.rmdir()`、`os.unlink()`、`os.chmod()` 等文件系统变更。
- `shutil.copy*()`、`shutil.move()`、`shutil.rmtree()`。
- `tempfile.NamedTemporaryFile()`、`TemporaryDirectory()`、`mkstemp()`、`mkdtemp()` 等临时文件/目录创建。
- Tool 文件额外禁止 import `graph_agent.cognitive.context_facade`，避免 tool 直接拿 LOGIC action 的 `Context`。

读文件的 `open(..., "r")` / `open(..., "rb")` / `open(..., "rt")` 当前允许。当前扫描器没有看到对网络请求或 `subprocess` 的通用禁止规则。

## 6. 第 3 步：装配成 LangGraph

编译完会得到一个内部对象，可以理解成“结构化后的 skill”。

装配阶段把它变成 LangGraph 的图：

```text
GRAPH.md 里的 phase
  -> LangGraph node

GRAPH.md 里的 depends_on
  -> LangGraph edge
```

比如：

```text
prepare -> analyze -> assemble
```

会变成：

```text
START
  -> prepare node
  -> analyze node
  -> assemble node
  -> END
```

如果两个 phase 依赖同一个前置 phase，LangGraph 可能并行跑它们。

这就是为什么 reducer 很重要：并行节点都返回 delta 时，引擎要知道怎么合并。

## 7. 第 4 步：执行图

图启动时，state 是：

```json
{
  "data": {"text": "hello"},
  "flow": {},
  "messages": [],
  "run_id": "xxx"
}
```

LangGraph 按 `depends_on` 顺序执行每个 phase。

每个 phase 读同一个 state，但返回值通常只包含自己改了什么。

## 8. 第 5 步：返回结果

图跑完后，`run_skill()` 从最终 state 里取：

```python
result["data"]
```

作为最终 context 返回。

所以最终结果大概是：

```json
{
  "text": "hello",
  "clean_text": "hello",
  "analyze": {
    "summary": "..."
  }
}
```

## 9. 重点一：context / data 到底怎么流

你关心的是：

```text
input schema 定义
  -> context stage dict
  -> phase 1 input
  -> context stage dict
  -> phase 2 input
```

按当前 V2.1 真实实现，应该改成这样理解：

```text
io/inputs.json
  -> 描述输入字段，不是运行时自动映射器

run_skill(**inputs)
  -> 初始 data 黑板

phase 1
  -> 直接读整个 data
  -> 返回 phase 1 delta

reducer
  -> 把 phase 1 delta 合回 data

phase 2
  -> 直接读更新后的整个 data
  -> 返回 phase 2 delta

reducer
  -> 把 phase 2 delta 合回 data
```

### 一个具体例子

假设输入是：

```json
{
  "text": " Hello world "
}
```

初始 data：

```json
{
  "text": " Hello world "
}
```

### phase 1：prepare

`prepare` 是 LOGIC phase。

它读：

```text
data["text"]
```

它写：

```json
{
  "clean_text": "Hello world"
}
```

合并后 data：

```json
{
  "text": " Hello world ",
  "clean_text": "Hello world"
}
```

### phase 2：analyze

`analyze` 是 SKILL phase。

当前它不会自动收到一个叫 `phase_input` 的对象。

它的 prompt 也不会自动把 `data["clean_text"]` 塞进去。

它能做的事取决于当前 SKILL 文档和工具设计：

- 如果 prompt 写死了说明，它按说明行动。
- 如果有 tools，它可以调用 tools。
- 如果要产出最终结果，它调用 `finish_task`。

当它调用 `finish_task` 成功后，引擎写：

```json
{
  "analyze": {
    "summary": "Hello world 的摘要"
  }
}
```

合并后 data：

```json
{
  "text": " Hello world ",
  "clean_text": "Hello world",
  "analyze": {
    "summary": "Hello world 的摘要"
  }
}
```

### phase 3：assemble

`assemble` 如果是 LOGIC phase，可以这样读：

```text
data["clean_text"]
data["analyze"]["summary"]
```

它返回：

```json
{
  "final_report": "..."
}
```

最终 data：

```json
{
  "text": " Hello world ",
  "clean_text": "Hello world",
  "analyze": {
    "summary": "Hello world 的摘要"
  },
  "final_report": "..."
}
```

## 10. 当前没有旧版 context_mapping

旧版你可能期待的是：

```yaml
context_mapping:
  input_text: text
  previous_result: analyze.summary
```

然后引擎自动把上游字段投喂给下游节点。

当前 V2.1 主线不是这么做。

当前更像：

```text
所有 phase 都看同一个 data
谁需要什么，自己按 key 去拿
谁产出什么，自己返回对应 key
```

所以设计 phase 时要注意：

- LOGIC phase 产出顶层 key。
- SKILL phase 默认产出 `data[phase_id]`。
- SUBGRAPH phase 会把子图产生的 delta 合回父图。
- subagent 结果不会自动合回父图 data。

## 11. LOGIC phase 的完整流程

LOGIC 是最直观的。

流程：

1. 引擎拿当前 `state.data`。
2. 复制一份给 action。
3. 包成 `Context`。
4. action 用 `ctx.get()` 读数据。
5. action 用 `ctx.set()` / `ctx.update()` 或 `return dict` 写结果。
6. 引擎比较 action 前后的 data，算 delta。
7. 返回 `{"data": delta}`。
8. LangGraph 把 delta 合回全局 data。

人话：

> LOGIC phase 就是“拿黑板上的数据算一下，再把新字段写回黑板”。

当前推荐写法：

```text
读：ctx.get("字段名")
写：return {"新字段": 值}
```

尽量不要覆盖已有 key，因为当前 reducer 有顺序覆盖 bug。

LOGIC action 还有编译期写键检查：

- `return {"key": value}` 里的 key 必须出现在 `io/outputs.json` 的 `properties` 里。
- `ctx.update(key=value)` / `context.update(key=value)` 的 key 必须出现在 `io/inputs.json` + `io/outputs.json` 的 `properties` 合集里。
- `ctx.set("key", value)` 这种动态字符串写法当前不容易被静态扫描完整识别，但运行时仍可能被后续 schema / reducer 问题挡住。

违反静态写键规则会报：

```text
[F-v21-actions-keys]
```

## 12. SKILL phase 的完整流程

SKILL phase 是大模型节点。

流程：

1. 引擎读取 `SKILL.md`。
2. 拿出 `system_prompt`。
3. 拿出 `exit_contract`。
4. 收集业务 tools。
5. 收集 subagent 动态工具。
6. 自动加上 `finish_task` 工具。
7. 把 tools 绑定给 chat model。
8. 进入最多 8 轮 ReAct 循环。
9. 每轮把 `exit_contract` 追加到 prompt 后面。
10. 调模型。
11. 如果模型调用普通 tool，就执行普通 tool。
12. 如果模型调用 subagent tool，就启动子 skill。
13. 如果模型调用 `finish_task`，就解析结果。
14. `finish_task` 成功后，把结果写到 `data[phase_id]`。
15. phase 结束。

人话：

> SKILL phase 不是直接修改 data。它要通过 `finish_task` 把结果交给引擎，引擎再写入 `data[当前 phase id]`。

### SKILL phase 怎么拿上游数据

这是当前实现里容易踩坑的地方。

LOGIC phase 可以直接 `ctx.get()`。

但 SKILL phase 现在没有一个等价的 `ctx` 注入给 LLM。

当前代码里，SKILL prompt 主要来自：

```text
system_prompt
exit_contract
messages 历史
tools
```

它没有自动做：

```text
把 state.data 渲染进 user prompt
```

所以如果某个 SKILL phase 需要上游数据，当前需要通过下面方式之一设计：

1. 在 prompt 或工具里明确提供读取数据的能力。
2. 前面 LOGIC phase 把数据整理成工具可访问的形式。
3. 后续修 runtime，把 `state.data` 以受控方式注入 SKILL prompt。

这也是当前 V2.1 runtime 还没完全收口的地方。

## 13. finish_task 的完整流程

`finish_task` 是 `SKILL` phase 结束的关键。

它接收的是 Markdown 字符串。

流程：

1. LLM 调用 `finish_task(markdown=...)`。
2. 引擎把 Markdown 解析成 JSON-like dict。
3. 如果当前 phase 是终点 phase，会拿 `io/outputs.json` 校验结果。
4. 如果解析或校验失败，会返回结构化错误给 LLM。
5. 如果配置了 md_patch，会尝试让 LLM 修 Markdown，最多 3 次。
6. 如果最终成功，返回：

```json
{
  "ok": true,
  "data": {...}
}
```

7. SKILL node 收到成功结果后写：

```json
{
  "当前 phase id": {...}
}
```

例如 phase id 是 `review`，那么写入：

```json
{
  "review": {
    "passed": true,
    "comments": []
  }
}
```

人话：

> `finish_task` 是 LLM phase 的“交卷按钮”。交卷成功后，引擎把卷子内容放到 `data[phase_id]`。

重点：

- `io/outputs.json` 校验只在终点 SKILL phase 上生效。
- 非终点 SKILL phase 的 `finish_task` 只要 Markdown 能解析成功，就不会按整个 skill 的 `outputs.json` 校验字段。
- 这意味着中间 SKILL phase 的输出结构，主要靠 prompt 约束和下游读取约定维持。

## 14. SUBGRAPH phase 的完整流程

SUBGRAPH 是“图里的节点调用另一个完整 skill”。

流程：

1. 当前 phase 是 `SUBGRAPH.md`。
2. `SUBGRAPH.md` 里声明子 skill 路径。
3. 引擎编译子 skill。
4. 引擎把子 skill 也装配成 LangGraph。
5. 运行到这个 phase 时，复制父图当前 `data`。
6. 用这份 data 启动子图。
7. 子图内部自己跑完。
8. 引擎比较子图运行前后的 data。
9. 算出子图产生的 delta。
10. 把 delta 合回父图 data。

人话：

> SUBGRAPH 像“把一整条小流水线插进当前流水线”。它的结果会直接回到父图黑板。

注意：

因为当前 reducer 有顺序覆盖问题，子图如果修改父图已有 key，也会触发冲突。

## 15. 重点二：agent phase 里的 subagent 怎么调用

先说结论：

> subagent 不是只写 `subskills/xxx/SKILL.md`。当前 V2.1 要求 `subskills/xxx` 是一个完整 skill root，必须有 `GRAPH.md`、`io/*.json`、`phases/.../SKILL.md`。

正确结构大概是：

```text
parent_skill/
├── GRAPH.md
├── io/
├── phases/
│   └── main/
│       ├── SKILL.md
│       └── subskills/
│           └── echo_expert/
│               ├── GRAPH.md
│               ├── io/
│               │   ├── inputs.json
│               │   └── outputs.json
│               └── phases/
│                   └── echo/
│                       └── SKILL.md
```

父 `SKILL.md` 里声明：

```yaml
phase_config:
  subagents:
    - name: echo_expert
      path: subskills/echo_expert
      description: Echoes text from a child expert skill.
```

这个声明的意思是：

> 在当前 agent phase 里，给 LLM 增加一个工具，叫 `call_subagent_echo_expert`。LLM 调这个工具时，引擎去跑 `subskills/echo_expert` 这个完整子 skill。

## 16. subagent 编译期发生什么

编译父 skill 时，引擎看到：

```yaml
subagents:
  - name: echo_expert
    path: subskills/echo_expert
```

然后做这些事：

1. 检查 path 是相对路径。
2. 检查 path 不能跑出当前 skill root。
3. 检查 path 是目录。
4. 检查目录里有 `GRAPH.md`。
5. 编译这个子 skill。
6. 读取子 skill 的 `io/inputs.json`。
7. 用 `io/inputs.json` 生成一个 Pydantic 模型。
8. 生成一个动态工具：

```text
call_subagent_echo_expert
```

9. 把这个工具注入父 SKILL phase 的 tools 列表。

人话：

> 文档里只写了 subagent 声明。真正的工具函数不是你手写的，是 engine 编译时动态造出来的。

## 17. subagent 工具参数长什么样

subagent 工具统一收：

```json
{
  "inputs": [
    {
      "text": "hello"
    }
  ]
}
```

`inputs` 是数组，因为一次工具调用可以批量跑多个子任务。

如果子 skill 的 `io/inputs.json` 是：

```json
{
  "type": "object",
  "properties": {
    "text": {"type": "string"}
  },
  "required": ["text"]
}
```

那么每个 input item 都必须有：

```json
{"text": "..."}
```

如果 LLM 传错了，引擎不会立刻跑子图，而是返回 validation error 给 LLM，让它重试。

最多重试 10 次。

## 18. subagent 运行期发生什么

父 SKILL phase 跑起来后：

1. 父 LLM 看到工具 `call_subagent_echo_expert`。
2. 父 LLM 决定调用它。
3. LLM 传入：

```json
{
  "inputs": [
    {"text": "A"},
    {"text": "B"}
  ]
}
```

4. 引擎校验每个 input。
5. 校验通过后，对 `inputs` 里的每一项启动一次子 skill。
6. 最多并发 3 个。
7. 每次子 skill 的初始 data 是：

```text
父图当前 data + 本次 input
```

也就是：

```json
{
  "...父图已有字段": "...",
  "text": "A"
}
```

8. 子 skill 自己按它的 `GRAPH.md` 跑完。
9. 引擎计算子 skill 相对于父图 data 的变化。
10. 这些变化作为工具结果返回给父 LLM。
11. 父 LLM 看到工具结果后，继续思考。
12. 父 LLM 最后调用 `finish_task`。
13. 父 phase 的结果才写进父图 `data[父 phase id]`。

关键点：

> subagent 的结果不会自动写进父图 data。它先作为工具返回值进入父 agent 的对话，父 agent 再决定怎么总结到自己的 `finish_task` 里。

这和 SUBGRAPH 不一样。

## 19. SUBGRAPH 和 subagent 的区别

| 项目 | SUBGRAPH phase | SKILL phase 里的 subagent |
|---|---|---|
| 谁触发 | 图执行到这个 phase 自动触发 | 父 LLM 决定是否调用工具 |
| 子任务形态 | 完整 skill 子图 | 完整 skill 子图 |
| 输入来源 | 父图当前 `data` | 父图当前 `data` + LLM 传的 input |
| 结果去哪 | 直接合回父图 `data` | 先作为 tool result 给父 LLM |
| 谁决定最终写什么 | 子图本身 | 父 LLM 的 `finish_task` |

人话：

- SUBGRAPH 是流程编排。
- subagent 是 agent 自己临时叫外援。

## 20. 普通 tool 和 subagent tool 的区别

普通 tool：

```text
LLM 调工具
  -> Python 函数执行
  -> 返回结果给 LLM
```

subagent tool：

```text
LLM 调工具
  -> 引擎启动一个完整子 skill
  -> 子 skill 跑完整张图
  -> 返回子图结果给 LLM
```

所以 subagent tool 看起来是工具，实际上是小型 engine 嵌套调用。

## 21. cache 在流程里的位置

编译 skill 时可以走 cache。

cache 目标是：

> 避免每次都重新解析 `GRAPH.md`、phase markdown、schema。

但当前有一个重要 bug：

> cache hit 后会丢 `subagents_by_phase` 和 `phase_tokens`。

所以 subagent skill 可能第一次编译有 `call_subagent_xxx`，第二次命中 cache 后工具不见。

这属于后续必须优先修的问题。

## 22. callbacks / trace 在流程里的位置

旧 harness 里 callbacks、trace、heartbeat 比较完整。

但当前 V2.1 主线直接：

```text
compile_skill
  -> assemble_graph
  -> graph.invoke
```

没有完整接回旧 harness 的 callbacks。

所以现在不能假设：

```text
每个 phase start/end 都一定有 callback
每次 LLM/tool 调用都一定有 trace
```

这是当前 runtime 缺口。

## 23. 当前最容易误解的 8 件事

### 1. 不是单文件 SKILL.md

V2.1 入口要传 skill root 目录。

### 2. 不是旧版 context_mapping

当前主线没有显式 per-phase `context_mapping`。

### 3. inputs.json 不是 runtime input mapper

它是 schema，不是自动把输入分发给每个 phase 的映射表。

### 4. LOGIC 可以直接读写 data

LOGIC 通过 `Context` 读写。

### 5. SKILL 不会自动拿到一个 ctx

SKILL 当前主要靠 prompt、tools、subagent、finish_task。

### 6. SKILL 的结果默认写到 data[phase_id]

不是把输出字段自动展开到顶层。

### 7. SUBGRAPH 会把子图 delta 合回父图

它是流程级调用。

### 8. subagent 结果不会自动合回父图

它是工具级调用，先返回给父 LLM。

## 24. 用一条完整链路串起来

假设有一个 skill：

```text
prepare(LOGIC)
  -> analyze(SKILL, 可调用 subagent)
  -> assemble(LOGIC)
```

用户调用：

```text
run_skill(root, text=" Hello ")
```

### 初始

```json
data = {
  "text": " Hello "
}
```

### prepare

LOGIC 读：

```text
text
```

LOGIC 写：

```json
{
  "clean_text": "Hello"
}
```

合并后：

```json
data = {
  "text": " Hello ",
  "clean_text": "Hello"
}
```

### analyze

SKILL phase 启动。

LLM 看到：

- system prompt
- exit contract
- tools
- subagent tools
- finish_task

如果它调用 subagent：

```json
call_subagent_expert({
  "inputs": [
    {"text": "Hello"}
  ]
})
```

引擎启动子 skill。

子 skill 初始 data：

```json
{
  "text": "Hello",
  "clean_text": "Hello"
}
```

子 skill 返回工具结果给父 LLM。

父 LLM 最后调用：

```text
finish_task(markdown="...")
```

引擎写：

```json
{
  "analyze": {
    "result": "..."
  }
}
```

合并后：

```json
data = {
  "text": " Hello ",
  "clean_text": "Hello",
  "analyze": {
    "result": "..."
  }
}
```

### assemble

LOGIC 读：

```text
clean_text
analyze.result
```

写：

```json
{
  "final_report": "..."
}
```

最终：

```json
data = {
  "text": " Hello ",
  "clean_text": "Hello",
  "analyze": {
    "result": "..."
  },
  "final_report": "..."
}
```

## 25. 当前设计上的实际建议

如果你要写或迁移 V2.1 skill，建议按下面方式设计数据：

### 1. LOGIC phase 写清楚的顶层 key

例如：

```text
clean_text
segments
entities
```

### 2. SKILL phase 接受默认分桶

SKILL phase 的输出默认进：

```text
data[phase_id]
```

所以 phase id 要起得像数据名。

例如：

```text
phase id = analysis
data["analysis"] = {...}
```

### 3. 不要依赖旧 context_mapping

当前主线不支持这个心智模型。

### 4. 谨慎覆盖已有 key

当前 reducer 有 bug，顺序覆盖已有 key 会报冲突。

在修复前，尽量新增 key，不要改已有 key。

### 5. subagent 必须是完整 skill root

不要只放一个 `SKILL.md`。

必须有：

```text
GRAPH.md
io/inputs.json
io/outputs.json
phases/.../SKILL.md
```

### 6. subagent 的输入 schema 要认真写

父 LLM 调 subagent tool 时，参数校验完全依赖子 skill 的 `io/inputs.json`。

### 7. 明确区分 SUBGRAPH 和 subagent

需要固定流程编排，用 SUBGRAPH。

需要让 LLM 自主决定是否叫外援，用 subagent。

## 26. 最后的总图

```text
run_skill(root, **inputs)
  |
  v
初始 state
  data = inputs
  flow = {}
  messages = []
  |
  v
compile_skill(root)
  读 GRAPH.md / io / phases / actions / tools / subagents
  |
  v
assemble_graph(compiled)
  phase -> node
  depends_on -> edge
  |
  v
LangGraph 执行
  |
  +--> LOGIC
  |      读 data -> action -> delta -> 合回 data
  |
  +--> SKILL
  |      prompt + tools + subagents + finish_task
  |      finish_task 成功 -> data[phase_id] = result
  |
  +--> SUBGRAPH
         父 data -> 子图 -> 子图 delta -> 合回父 data
  |
  v
最终 result.context = state.data
```

## 27. 一句话收尾

当前 engine 的核心不是“每个节点都有一套独立 input/output mapping”，而是“整张图共享一块业务黑板 `data`”。LOGIC 和 SUBGRAPH 直接通过 delta 改黑板；SKILL 通过 `finish_task` 把结果放到 `data[phase_id]`；subagent 是 SKILL 里的动态工具，背后启动完整子 skill，但结果先回到父 LLM，不自动写父图黑板。
