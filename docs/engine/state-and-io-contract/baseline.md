# state-and-io-contract (engine) — Baseline (PR γ2 当下代码实现逻辑)

> **Status**: Synced by a1 (Codex), 2026-05-25
> **Scope**: 当前源码事实：BlackboardState 三区、StateMapper、PhaseWrapper、child graph 隔离、reference reader 沙盒、finish_task 写回。
> **配套**: 字段级运行解释见 [logic-explained.md](./logic-explained.md)。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

Studio 如果要展示 phase 输入输出，应读取 γ2 后的 `data.inputs`、`data.phase_outputs`、`data.scratch`，不能再按旧 flat `state["data"][key]` 解释。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 React 逻辑。

React 不持有 `BlackboardState`，但 trace/结果面板需要知道：业务输出现在按 `phase_outputs[phase_id]` 归档。

## 后端功能

### 当前状态模型总览

`BlackboardState` 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py`。

字段：

- `data`: `BlackboardData`，带 `blackboard_data_merge` reducer。
- `flow`: 控制状态 dict。
- `messages`: LLM 对话消息，带 LangGraph `add_messages` reducer。
- `run_id`: 本次运行 id。

`BlackboardData` 是三区：

- `inputs`: canonical 初始入参，只读。
- `phase_outputs`: `dict[str, dict]`，每个 phase 的输出 namespace。
- `scratch`: 草稿区。

`shallow_dict_merge` 当前只是 `blackboard_data_merge` 的兼容别名。

### blackboard_data_merge

当前 `data` reducer 先调用 `normalize_blackboard_data()`。如果收到旧 flat dict，会把它规范化成 `{"inputs": raw, "phase_outputs": {}, "scratch": {}}`；如果已经包含 `inputs` / `phase_outputs` / `scratch`，则按三区 deep copy。

合并规则：

1. right 没有内容时返回 left 规范化结果。
2. right 写 `inputs`，且 left 已有不同 inputs，抛 `[F-v3-runtime-state-mapping-failed] data.inputs is read-only after initialization`。
3. right 写 `phase_outputs[phase_id]`，而 left 已有同 phase_id，抛 `[F-v3-state-conflict] phase_outputs[...] written more than once`。
4. right 写 `scratch[key]`，而 left 已有同 key，抛 `[F-v3-state-conflict] scratch key=... written more than once`。

这替代了旧 baseline 里的 flat 顶层 key 冲突模型。

### StateMapper 读写面

`StateMapper.build_phase_input()` 当前构造 phase-local state：

- canonical inputs 与上游 `phase_outputs` 通过 `_phase_local_inputs` 合成局部 `inputs`。
- raw inputs 优先：`setdefault` 不覆盖已有 input。
- 上游同名输出按 `phase_outputs` 插入序先到先得。
- 再用 `filter_runtime_inputs` 按 `input_schema.properties` 做 phase input funnel。
- `phase_outputs` 嵌套区 deep copy 透传。
- `scratch` 清空。
- `messages` 清空。
- `flow` deep copy。

注意：canonical `data.inputs` 和 phase-local `data.inputs` 不是同一个语义。前者是持久只读入口；后者是当前 phase 的一次性读取视图，可以含上游产出。

`StateMapper.wrap_phase_output()` 当前写回：

- 普通业务 dict -> `data.phase_outputs[phase_id]`。
- 返回三区结构但含 `inputs` -> `[F-v3-runtime-state-mapping-failed] data.inputs is read-only`。
- 有 `output_schema.properties` 时，未声明输出 key -> `[F-v3-runtime-state-mapping-failed] phase wrote undeclared keys: ...`。

### PhaseWrapper

`PhaseWrapper` 是所有 runtime node 的统一漏斗。当前覆盖：

- LOGIC node。
- Agent / Skill node。
- SUBGRAPH node。
- builtin reference reader node。

wrapper 给返回函数写入 `__graph_agent_phase_wrapped__` 和 `__graph_agent_phase_node_kind__`。如果再次包装同一个函数，会抛 `[F-v3-runtime-state-mapping-failed] double-wrap rejected...`。

### LOGIC / Agent / SUBGRAPH 当前状态行为

LOGIC node：

- 从 `phase_inputs_from_state(state)` 取 phase-local inputs。
- `Context` 在这个局部 dict 上读写。
- action 写出的 delta 返回给 `wrap_phase_output`，最终落 `phase_outputs[phase_id]`。

Agent / Skill node：

- ReAct messages 不继承上一 phase 的 messages，因为 wrapper 的 phase-local input 清空 messages。
- finish_task 成功后由 `CognitiveFlowMiddleware` 写三区结构：`phase_outputs[phase_name] = final_write`。

SUBGRAPH node：

- child graph 初始 state 是 fresh blackboard：`inputs=child_input`、`phase_outputs={}`、`scratch={}`、`messages=[]`。
- parent `phase_outputs`、`scratch`、`messages` 不进入 child。
- child outputs 只从 child `phase_outputs` 聚合；重复业务 key fatal。
- 聚合结果再由 parent phase wrapper 写入 `phase_outputs[parent_phase_id]`。

### Subagent child 当前状态行为

subagent child graph 初始 state：

- `data.inputs = dict(input_data)`，只来自工具显式入参。
- `data.phase_outputs = {}`。
- `data.scratch = {}`。
- `messages = []`。
- `run_id` 透传 parent run_id。

child result 只从 child `phase_outputs` 聚合。child 没有 phase_outputs 时返回空 data，不再用 `_dict_delta(input_data, result_data)` 兼容 flat 旧语义。

### Builtin reference reader 当前状态行为

`ReferenceReaderRuntime` 位于 `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py`。

`initial_state()` 通过 `ReaderSandboxState` 返回：

- `data.inputs.skill_id`
- `data.inputs.phase_id`
- `data.phase_outputs={}`
- `data.scratch={}`
- `flow.timeout_s=60`
- `messages=[]`
- `run_id=None`

`graph_assembler` 中 `read_reference` 工具调用会创建该 runtime，并把 `reference_id` / `path` 加入 sandbox inputs，再交给 `node_kind="reference_reader"` 的 `PhaseWrapper`。路径非法或不可读抛 `[F-v3-resource-reference-path-invalid]`；reader path 缺失抛 `[F-v3-reference-reader-failed]`。

### finish_task 当前写回

`CognitiveFlowMiddleware.handle_finish_task_tool_result()` 成功时返回：

```python
{
    "data": {
        "inputs": {},
        "phase_outputs": {phase_name: final_write},
        "scratch": {},
    },
    "flow": ...,
    "messages": ...,
}
```

这替代旧文档里的 `data={phase_name: final_write}`。schema gate 失败时仍通过 `[F-v3-agent-output-schema-invalid]` / `[F-v3-agent-output-schema-missing]` 给 LLM 反馈，不写业务输出。

## API

当前直接 API：

- `BlackboardData`
- `BlackboardState`
- `blackboard_data_merge`
- `normalize_blackboard_data`
- `StateMapper`
- `PhaseWrapper`
- `ReaderSandboxState`

`filter_runtime_inputs(raw_inputs, schema)` 只按 `schema.properties` 过滤字段；没有 properties 时复制输入。它不是完整 JSON Schema validator。

## Data Model / State

当前最准确的心智模型：

1. 持久黑板分三区。
2. 同一 graph 内，下游 phase 通过 phase-local input view 读取上游 phase output。
3. phase 写回必须归档到自己的 `phase_outputs[phase_id]`。
4. child graph / subagent / reference reader 都从 fresh blackboard 开始，不继承 parent scratch/messages/phase_outputs。

## Cross-feature Interaction

### 与 skill-compilation 的关系

compilation 负责解析 phase AST、`io.inputs` / `io.outputs`、SUBGRAPH target skill、Agent references。state-and-io-contract 只消费这些编译结果做运行时切片和写回。

### 与 execution-runtime 的关系

execution-runtime 执行 node；StateMapper 和 PhaseWrapper 决定 node 能看到什么、能写回什么。runtime 不应绕过 wrapper 直接 patch flat `data`。

### 与 tracing-and-observability 的关系

trace 应按三区记录：

- canonical `inputs`
- phase-local input view
- `phase_outputs[phase_id]`
- child canonical input
- reference reader sandbox input

旧 flat `data[key]` 视角已经不能准确解释 γ2 后的结果。
