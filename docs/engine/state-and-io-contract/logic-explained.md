# state-and-io-contract 运行逻辑人话版

署名：Codex
日期：2026-05-23
范围：`/home/sevenx/coding/agent-harness/packages/graph-agent`
定位：解释当前 V0.3.0 state / IO 边界真实怎么跑，以及 MVP0 目标语义要收敛到哪里

## 0. 阅读路径

这份文档可以按目标跳读：

- 只想知道结论：读“1. 先给结论”。
- 想知道 state 里有什么：读“2. 术语先讲清楚”和“3. BlackboardState 是什么”。
- 想知道输入输出怎么被拦：读“5. StateMapper 做了什么”和“6. PhaseWrapper 在哪里生效”。
- 想知道 LOGIC / Agent / SUBGRAPH / subagent 的差别：读“7. 四类运行边界怎么走”。
- 想知道 V0.3.0 为什么要改：读“10. MVP0 要收敛的 4 件事”。

## 1. 先给结论

当前 `state-and-io-contract` 的核心不是旧式 `context_mapping`。

当前真实模型更接近这样：

```text
整张 LangGraph 有一份 BlackboardState
  -> data 放业务字段
  -> flow 放控制字段
  -> messages 放 LLM 对话
  -> run_id 放本次运行标识

每个带 io 的 phase 运行前
  -> StateMapper 按 io.inputs 从 data 里切一份局部 state

phase 跑完后
  -> StateMapper 按 io.outputs 检查它写回的 data

最后 LangGraph reducer
  -> 把 phase 返回的 data delta 合回全局 data
```

一句话：

> `BlackboardState` 是全图共享黑板，`StateMapper` 是每个 phase 门口的检查员：进去前只发它声明能看的字段，出来后只收它声明能写的字段。

当前源码已经有这个门口检查员，但还不是最终形态。它现在主要按 JSON Schema 的 `properties` 做字段名过滤和输出 key 检查，还没有完整做 required / type / default / coercion 级别的 JSON Schema runtime validation。代码位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:15` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:66`。

## 2. 术语先讲清楚

### BlackboardState

LangGraph 运行时的主 state。

它定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`，字段是 `data`、`flow`、`messages`、`run_id`。

它是 `TypedDict(total=False)`。人话就是：运行时仍然是普通 dict，但类型说明告诉代码读者和类型检查器，这个 dict 主要应该长什么样。

### data

业务数据区。

外部输入、LOGIC action 产生的结果、SUBGRAPH 子图产生的 delta、Agent `finish_task` 的业务结果，最终都会以某种形式进入 `data`。

源码把它写成：

```python
data: Annotated[dict[str, Any], shallow_dict_merge]
```

位置是 `packages/graph-agent/src/graph_agent/runtime/state.py:38`。

关键点是后面的 `shallow_dict_merge`。这说明 `data` 合并不是普通覆盖，而是走自定义 reducer。

### flow

框架控制区。

它适合放 `finish_task_result`、subagent 校验重试次数、critic metrics、subagent depth 这类控制信息，不应该当业务输出读。字段定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:39`。

SKILL node 会复制当前 `flow`，再写入 `finish_task_result` 和 `critic_metrics`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:297` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:360`。

### messages

LLM 对话历史。

它使用 LangGraph 的 `add_messages` reducer，定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:40`。Agent / SKILL phase 会把 system prompt 和已有 messages 组合起来，再把模型回复和 tool message 追加进去，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:299` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:345`。

### run_id

本次运行标识。

`StateMapper` 会把它原样带进 phase-local state，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:45`。subagent child run 会另外生成 child `run_id`，并把 `parent_run_id` 和 `subagent_depth` 写进 RunnableConfig metadata，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:673` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:685`。

### reducer

LangGraph 合并 node 返回值的函数。

当前 `data` 的 reducer 是 `shallow_dict_merge()`，定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:13`。`messages` 的 reducer 是 LangGraph `add_messages`。`flow` 没有自定义 reducer。

### StateMapper

phase 边界上的输入切片和输出检查器。

它定义在 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:33` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:66`。它不执行业务逻辑，只做两件事：

```text
build_phase_input()
  -> phase 运行前，按 input_schema 给它一份局部 BlackboardState

wrap_phase_output()
  -> phase 返回后，按 output_schema 检查 data 里有没有未声明 key
```

### PhaseWrapper

把 `StateMapper` 套到 runtime node 外面的一层壳。

它定义在 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:69` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:87`。装配点在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:162`。

### ReaderSandboxState

builtin reference reader 的装配期隔离黑板。

它定义在 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:90` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:105`。它生成的 blackboard 只含 `skill_id`、`phase_id`、`timeout_s`、空 messages 和空 run id，不继承父 graph 的业务黑板。

## 3. BlackboardState 是什么

`BlackboardState` 第一次真正进入运行图，是在 `assemble_graph()` 里：

```python
builder = StateGraph(BlackboardState)
```

位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:77`。

这行代码决定了整张图里的 node 都围绕同一种 state 运行。后面的 LOGIC、SUBGRAPH、Agent、subagent child graph，虽然执行方式不同，但都在读写这套 state envelope。

### data 怎么用

`data` 是业务字段的主要承载区。

LOGIC node 会拿当前 `state.data` 做一份拷贝，包成 `Context` 交给 action，action 返回 dict 或通过 Context 修改数据后，runtime 算 delta 并返回 `{"data": updates}`。位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:176` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:185`。

SUBGRAPH node 会用父图当前 `data` 启动子图，子图跑完后用 `_dict_delta()` 算变化，再返回 `{"data": data_updates, "flow": ...}`。位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:209` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:226`。

Agent / SKILL node 不直接暴露一个 `Context` 给 LLM。它通过 prompt、tools、subagent tools 和 `finish_task` 工作。`finish_task` 成功后，runtime 写：

```python
data_updates[phase_id] = result.get("data", {})
```

位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:346` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:362`。

人话：

> LOGIC 通常写顶层 delta；SUBGRAPH 写子图相对父图的 delta；Agent 把 `finish_task` 结果放进 `data[phase_id]`。

### flow 怎么用

`flow` 是控制态。

SKILL node 启动时做 `flow = dict(state.get("flow", {}))`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:297` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:298`。当 `finish_task` 被调用时，它把结果写到 `flow["finish_task_result"]`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:346` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:347`。

subagent 工具会把校验重试次数写进 `flow["subagent_validation_retries"]`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:504` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:509`。

注意：

`flow` 没有像 `data` 一样的冲突 reducer。并行场景下如果多个节点都写 flow，当前语义没有 `data` 那样明确的冲突保护。

### messages 怎么用

`messages` 是 Agent phase 的对话历史。

SKILL node 启动时，把 system prompt 放在最前面，再接上旧 messages，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:299` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:302`。每轮模型回复和工具结果都会继续追加，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:316` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:345`。

SUBGRAPH 和 subagent child graph 都从空 messages 开始，位置分别是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:215` 和 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:588`。

这点很重要：

> child graph 不应该继承父 Agent 的聊天历史。它可以拿输入，但不应该把父 Agent 的 prompt history 当成自己的 history。

## 4. data reducer 怎么合并

`shallow_dict_merge(left, right)` 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:32`。

它的规则很简单：

1. 如果 `left` 为空，返回 `right` 的浅拷贝。
2. 如果 `right` 为空，返回 `left` 的浅拷贝。
3. 如果 `right` 里某个 key 已经在 `left` 里，直接抛 `GraphAgentFatalError`。
4. 否则把 `right` 的顶层 key 加进 merged。

冲突错误码在这里：

```python
"[F-v3-state-conflict] key=..."
```

位置是 `packages/graph-agent/src/graph_agent/runtime/state.py:26` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:30`。

人话：

> 当前 reducer 只允许新增顶层 key，不允许写已有顶层 key。

这个设计本来是为了挡并行分支同时写同一个字段。问题是它现在看不到 LangGraph super-step，也不知道这次写入是并行 fan-in 还是顺序 phase 更新。所以只要 delta 写了已有 key，它都会失败。

这就是 MVP0 里 P0-3 要收敛的地方：未来应该区分“同一 super-step 并发冲突”和“前后 step 的合法覆盖”。但在当前源码里，真实行为仍是顶层同名 key 直接 `[F-v3-state-conflict]`。

## 5. StateMapper 做了什么

`StateMapper` 是 state/io contract 的核心。

它有两个配置字段：

```python
input_schema: dict[str, Any] | None = None
output_schema: dict[str, Any] | None = None
```

位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:37` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:38`。

### 第一步：从 schema 里拿 properties

`schema_properties(schema)` 只做一件事：读 JSON Schema 顶层 `properties` 的 key。

如果 `schema` 不是 dict，返回空集合。
如果 `properties` 不是 dict，也返回空集合。
如果 properties 合法，就返回其中所有字符串 key。

代码位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:15` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:21`。

注意：

当前这里不是完整 JSON Schema validator。它不检查 required，不检查 type，不填 default，也不做 coercion。它只是拿字段名集合。

### 第二步：运行前切输入

`filter_runtime_inputs(raw_inputs, schema)` 会用 `schema_properties()` 的结果过滤输入。

如果 schema 没有 properties，它返回 `dict(raw_inputs)`，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:27` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:29`。

如果 schema 有 properties，它只保留同时出现在 schema 和 raw inputs 里的字段，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:30`。

然后 `StateMapper.build_phase_input()` 用它构造 phase-local state：

```python
phase_state = {
    "data": filter_runtime_inputs(...),
    "flow": deepcopy(...),
    "messages": list(...),
    "run_id": ...
}
```

位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:40` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:47`。

人话：

> phase 进去前，不应该默认拿到整张黑板。它声明能看哪些字段，StateMapper 就从 `data` 里切哪些字段给它。

`flow` 用 `deepcopy()`，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:43`。这是为了避免 phase 拿到同一个嵌套 dict 引用后，在 wrapper 之外偷偷污染父状态。

`messages` 用 list copy，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:44`。它保护列表结构，但不深拷贝每个 message 对象。

### 第三步：运行后封输出

`StateMapper.wrap_phase_output(output)` 先看 `output.get("data")`，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:49` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:50`。

如果 `data` 不是 dict，直接放行。
如果 output schema 没有 properties，直接放行。
如果 output schema 有 properties，就检查 `data` 里有没有未声明 key。

未声明 key 的错误在这里：

```python
"[F-v3-runtime-state-mapping-failed] phase wrote undeclared keys: ..."
```

位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:60` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:65`。

还有一个兼容分支：

如果返回的 `data` 只有一个 key，并且这个 key 下面是 dict，并且 nested dict 的 key 都在 output schema 允许集合里，就放行。代码位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:56` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:59`。

这个分支主要服务 Agent / SKILL phase 当前写法。因为 Agent `finish_task` 成功后写的是：

```python
data_updates[phase_id] = result.get("data", {})
```

所以真正要校验的业务字段可能在 `data[phase_id]` 里面，而不是 `data` 顶层。

## 6. PhaseWrapper 在哪里生效

`PhaseWrapper` 的逻辑非常短：

```text
收到全局 state
  -> build_phase_input(state)
  -> 调原始 node
  -> wrap_phase_output(result)
  -> 返回给 LangGraph
```

代码位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:75` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:87`。

如果原始 node 抛的是 `GraphAgentFatalError`，wrapper 原样抛出，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:80` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:81`。这样更具体的错误码不会被吞掉。

如果原始 node 抛的是普通异常，wrapper 会包装成：

```text
[F-v3-runtime-state-mapping-failed]
```

位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:82` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:85`。

真正把 wrapper 套到 node 上的地方在 `_wrap_phase_runtime_node()`：

```python
io = getattr(phase_ast, "io", None)
if io is None:
    return node
return PhaseWrapper(StateMapper(io.inputs, io.outputs)).wrap(node)
```

位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:162`。

注意：

> 只有 AST 上有 `io` 的 phase 才会进入 StateMapper。legacy node 如果没有 `io`，当前 runtime 不会硬猜它的输入输出边界。

## 7. 四类运行边界怎么走

### LOGIC phase

LOGIC phase 是最直接的。

流程是：

```text
PhaseWrapper 先按 io.inputs 切 state.data
  -> _logic_node 拿 phase-local data
  -> 包成 Context 给 Python action
  -> action 修改 Context 或 return dict
  -> runtime 算 updates
  -> 返回 {"data": updates}
  -> PhaseWrapper 按 io.outputs 检查 updates
  -> LangGraph reducer 合回全局 data
```

关键代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:176` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:185`。

LOGIC 还有一层老的输出 key 检查：如果 action 直接 `return dict`，会调用 `_validate_logic_update_keys()`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:182` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:184`。未声明 key 会报 `[F-v3-actions-keys]`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:713` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:718`。

人话：

> LOGIC 是确定性 Python 节点。它可以用 Context 读写局部 data，但最终写回全局前仍要过 output schema。

### Agent / SKILL phase

Agent / SKILL phase 是 LLM 节点。

流程是：

```text
PhaseWrapper 先按 io.inputs 切 state.data
  -> _skill_node 组装 system prompt、messages、tools
  -> 模型进入 ReAct loop
  -> 调普通 tool、critic tool、subagent tool 或 finish_task
  -> finish_task 成功时写 data_updates[phase_id]
  -> 返回 flow、messages、可选 data
  -> PhaseWrapper 检查 data[phase_id] 内部字段
```

关键代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:290` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:367`。

Agent 不会自动得到一个 Python `Context`。它看到的是 prompt、tools、subagent tools、finish_task，以及 messages 历史。当前源码没有把 `state.data` 自动渲染成一段 user prompt。

所以如果 Agent 需要上游字段，必须通过当前 phase 的 prompt / tools / resource 设计让它可见。StateMapper 只负责给 node 局部 state，不负责把业务 data 自动写进自然语言 prompt。

### SUBGRAPH phase

SUBGRAPH phase 是图里的节点调用另一个完整 skill 子图。

当前流程是：

```text
PhaseWrapper 先按 io.inputs 切父 phase state
  -> _subgraph_node 用当前 state.data 作为 child graph data
  -> child graph 从空 messages 开始
  -> child graph 跑完
  -> runtime 对比 before_data 和 result_data
  -> 返回子图产生的 data delta
  -> PhaseWrapper 按父 phase io.outputs 检查
```

关键代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:209` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:226`。

注意：

当前 SUBGRAPH child data 仍来自当前 phase-local `state.data`。如果外层 phase 已经被 StateMapper 切过，它拿到的是切片后的 data；但 child skill 自己的 root `io.inputs` 漏斗还不是这里的明确入口。

MVP0 要收敛的是：SUBGRAPH child 初始 data 应该先由父 phase 显式 input 得到，再按 child skill 的 `GRAPH.md io.inputs` 做漏斗，不应该靠父图全量黑板穿透。

### subagent tool

subagent 是 Agent phase 里动态生成的工具，不是 graph 拓扑里的普通 phase。

当前工具名来自：

```python
f"call_subagent_{subagent.name}"
```

位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:372` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:379`。

调用流程是：

```text
父 Agent 调 call_subagent_xxx
  -> runtime 校验 tool args
  -> 每个 input item 启动一次 child graph
  -> child_data = parent before_data + input_data
  -> child graph 从空 messages 开始
  -> child 结果变成 tool result
  -> tool result 回到父 LLM
  -> 父 LLM 最后决定 finish_task 写什么
```

关键代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:490` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:663`。

当前最关键的一行是：

```python
child_data = {**before_data, **input_data}
```

位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:582` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:584`。

这说明当前 subagent child graph 会看到父 graph 的业务 data，再叠加工具显式 input。MVP0 的 NEW-2 要改的就是这里：child graph 应该只拿显式 input，再按 target skill 的 root input schema 过滤和校验，不应该默认继承父黑板。

subagent 的结果不会直接 patch 父图 `data`。它作为 tool result 返回给父 LLM，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:595` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:599`。父 LLM 后续是否把它写进父 phase 的 `finish_task`，是父 Agent 的决策。

## 8. ReaderSandboxState 为什么单独存在

reference reader 不是普通 runtime phase。

它是装配期 builtin 辅助模块，用来预读 Agent phase 声明的 references。它不应该继承父 graph 的业务数据，也不应该继承父 Agent 的 messages。

`ReaderSandboxState` 字段是：

- `skill_id`
- `phase_id`
- `root`
- `timeout_s`

定义在 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:94` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:97`。

`to_blackboard()` 生成：

```python
{
    "data": {"skill_id": self.skill_id, "phase_id": self.phase_id},
    "flow": {"timeout_s": self.timeout_s},
    "messages": [],
    "run_id": None,
}
```

位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:99` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:105`。

人话：

> reference reader 有自己的临时小黑板。它只知道当前 skill / phase 和超时时间，不知道父图业务上下文。

MVP0 的 NEW-1 要补齐的是：reader 的业务输入还应该包含当前 Agent phase 的 reference registry，reader 失败时应该 WARN fallback，错误码收敛到 `[F-v3-reference-reader-failed]` 这一类边界，而不是污染 runtime graph state。

## 9. 现在代码和目标语义的差距

当前源码已经有 V0.3.0 state/io 的骨架：

- `BlackboardState` 已经把 `data`、`flow`、`messages`、`run_id` 分开。
- `data` 已经有 fail-fast reducer。
- `StateMapper` 已经能按 `io.inputs` properties 切 phase input。
- `StateMapper` 已经能按 `io.outputs` properties 拦未声明 output key。
- `PhaseWrapper` 已经能覆盖带 `io` 的 LOGIC、SUBGRAPH、Agent / SKILL phase。
- `ReaderSandboxState` 已经给 reference reader 准备了独立 blackboard envelope。

但它还不是完整目标态：

1. 输入漏斗目前主要是 properties 级过滤，不是完整 JSON Schema runtime validation。
2. `data` reducer 还不能区分并行冲突和顺序覆盖。
3. SUBGRAPH child input 还没有明确先过 child root `GRAPH.md io.inputs`。
4. subagent child graph 当前还会继承父图业务 data。
5. reference reader sandbox 还只是 envelope，reference registry / WARN fallback 语义需要继续接到装配链路。

## 10. MVP0 要收敛的 4 件事

### C7：Runtime Input Funnel 改到 inline root IO

V0.3.0 不应该再把 `io/inputs.json` 当作 runtime input funnel 的来源。

根输入 schema 应该来自 `GRAPH.md` frontmatter inline `io.inputs`。编译期负责确认它是合法 object schema；runtime 入口只消费编译产物，不重新猜 schema。

目标流程：

```text
run_skill(inputs)
  -> 读取编译产物里的 root io.inputs
  -> 过滤 unknown fields
  -> 校验 required / type
  -> 形成 canonical inputs
  -> 写入初始 BlackboardState.data
```

当前代码里的 `filter_runtime_inputs()` 是这个方向的最小基础，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:24` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:30`。

### C8：Phase Wrapper 覆盖四类边界

当前 `_wrap_phase_runtime_node()` 已经把带 `io` 的 phase 包进 `PhaseWrapper(StateMapper(...))`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:162`。

MVP0 要求这个思路覆盖四类边界：

- Agent / SKILL phase。
- LOGIC phase。
- SUBGRAPH phase。
- builtin reference reader subagent。

前三类来自 graph runtime phase。reference reader 不在 `phases/` 目录里，但它同样需要临时 blackboard、输入输出合约和失败边界。

### NEW-1：Builtin reference reader 独立沙盒

reference reader 应该是装配期沙盒，不是父 Agent 的隐式子对话。

当前 `ReaderSandboxState.to_blackboard()` 已经做到不继承父 data、不继承父 messages，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:99` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:105`。

目标语义还要继续补齐：

```text
Agent references registry
  -> reader sandbox data
  -> reader 产出可注入 cognitive template 的摘要
  -> reader 失败时 WARN
  -> fallback 截取 reference 原文
```

这个流程的失败不应该把父 graph runtime state 搞脏。

### NEW-2：child graph 黑板隔离

当前 subagent child graph 的 `child_data` 是父图 data 加显式 input：

```python
child_data = {**before_data, **input_data}
```

位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:582` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:584`。

目标语义应该改成：

```text
resolve target skill
  -> 读取 target GRAPH.md io.inputs
  -> 只用 explicit input 过 child input funnel
  -> child graph 从 canonical child input 启动
  -> child result 作为 tool result 或 SUBGRAPH phase output 回来
```

人话：

> 子图可以被调用，但不能默认看见父图整块业务黑板。

## 11. 错误应该停在哪里

state/io 的错误边界应该尽量靠近原因。

输入字段不合法，应该停在 input funnel。
phase 写了未声明输出，应该停在 `wrap_phase_output()`。
并行分支写同一个业务 key，应该停在 reducer。
reference reader 失败，应该停在装配期 reader fallback，而不是污染 runtime data。

当前源码里最重要的错误码有这些：

- reducer 顶层 key 冲突：`[F-v3-state-conflict]`，位置是 `packages/graph-agent/src/graph_agent/runtime/state.py:26` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:30`。
- phase 输出未声明字段：`[F-v3-runtime-state-mapping-failed] phase wrote undeclared keys`，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:60` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:65`。
- wrapper 捕获普通异常：`[F-v3-runtime-state-mapping-failed]`，位置是 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:82` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:85`。
- LOGIC action 返回未声明 key：`[F-v3-actions-keys]`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:713` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:718`。
- SKILL phase 没有 chat model：`[F-v3-graph] SKILL phase requires chat_model`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:294` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:295`。

## 12. 用一条完整链路串起来

假设有一张图：

```text
prepare(LOGIC)
  -> analyze(Agent)
  -> call child via subagent
  -> assemble(LOGIC)
```

运行开始时，外部输入进入初始 `BlackboardState.data`。

`prepare` 运行前，如果 AST 上有 `io.inputs`，`PhaseWrapper` 先调用 `StateMapper.build_phase_input()`，只把声明字段放进 phase-local `data`。Python action 运行后返回 updates。`PhaseWrapper` 再调用 `wrap_phase_output()`，确认 updates 没写越界字段。最后 LangGraph 用 `shallow_dict_merge()` 合回全局 `data`。

`analyze` 运行前，同样先被切一份局部 state。LLM 不直接拿 Python `Context`，而是通过 prompt、tools、subagent tools 和 `finish_task` 工作。`finish_task` 成功后，runtime 写 `data[analyze] = result.data` 这种形状。`wrap_phase_output()` 会识别这个单 key nested dict，并检查里面的业务字段是否在 output schema 中。

如果 `analyze` 调 subagent，当前源码会用父图 data 加 LLM 传入的 input 启动 child graph。child graph 从空 messages 开始，结果作为 tool result 回给父 LLM。父 LLM 最后是否把这个结果写入自己的 `finish_task`，由父 Agent 决定。

`assemble` 再按自己的 `io.inputs` 拿前面产物的切片，生成最终输出。只要它写了未声明 key，`StateMapper` 会在返回 LangGraph 前拦住。

最终 `run_skill()` 看到的是合并后的 `state.data`。

## 13. 当前最容易误解的 6 件事

### 1. `io.inputs` 不是旧版 context_mapping

它不是把上游字段重命名后自动塞给下游的 mapping 表。当前源码里它主要通过 `schema_properties()` 变成允许读取的字段集合。

### 2. `StateMapper` 不做业务计算

它只切输入、检查输出。真正的 LOGIC action、LLM ReAct loop、SUBGRAPH 调用都在 `graph_assembler.py`。

### 3. Agent 结果默认有 phase_id 命名空间

Agent `finish_task` 成功后写 `data_updates[phase_id]`，不是把所有结果字段直接摊到 `data` 顶层。

### 4. SUBGRAPH 和 subagent 不是一回事

SUBGRAPH 是 graph 拓扑里的 phase。subagent 是 Agent phase 里的工具调用。SUBGRAPH 的结果直接作为 phase 输出回 graph；subagent 的结果先作为 tool result 回父 LLM。

### 5. 当前 child graph 读隔离还没完全完成

SUBGRAPH 至少会受到父 phase `io.inputs` 切片影响；subagent 当前仍会把父图 data 合进 child data。NEW-2 就是为了解这个问题。

### 6. 当前 reducer 很保守

它不是 deep merge，也不是 last-write-wins。顶层同名 key 直接报 `[F-v3-state-conflict]`。

## 14. 最后的总图

```text
run_skill(inputs)
  v
BlackboardState
  data      -> 业务字段, 用 shallow_dict_merge 合并
  flow      -> 控制字段
  messages  -> LLM 对话, 用 add_messages 合并
  run_id    -> 运行标识
  v
assemble_graph()
  StateGraph(BlackboardState)
  v
每个带 io 的 phase
  -> PhaseWrapper
     -> build_phase_input()
        data = 按 io.inputs properties 切片
        flow = deepcopy
        messages = list copy
     -> 原始 node
        LOGIC    = Context + updates
        Agent    = tools + finish_task -> data[phase_id]
        SUBGRAPH = child graph -> data delta
     -> wrap_phase_output()
        data key 必须在 io.outputs properties 内
        未声明 key -> [F-v3-runtime-state-mapping-failed]
  v
LangGraph reducer
  data 同名顶层 key -> [F-v3-state-conflict]
  v
最终 state.data
```

## 15. 一句话收尾

`state-and-io-contract` 的核心工作，是把“所有节点共享一块业务黑板”的自由模型，收敛成“每个 phase 只读声明输入、只写声明输出、child graph 不偷看父黑板、reference reader 有独立沙盒”的可审计模型。当前源码已经有 `BlackboardState`、`StateMapper`、`PhaseWrapper` 和 `ReaderSandboxState` 这些骨架；MVP0 要继续补齐的是完整 input funnel、smart reducer、child graph 隔离和 reference reader fallback。
