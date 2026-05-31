# state-and-io-contract (engine) — MVP0 Alignment (V0.3.0 graph_skill)

> **Status**: Synced by a1 (Codex) for PR γ2, 2026-05-25
> **Scope**: 当前已落地的 三区 BlackboardData、StateMapper、PhaseWrapper、child graph 隔离、builtin reference reader 沙盒。
> **配套**: 详细字段级翻译见 [logic-explained.md](./logic-explained.md)。

## V0.3.0 当前收敛结果

| 旧语义 | γ2 当前实现 | 错误码 / 保护 |
|---|---|---|
| `state["data"]` 是 flat 业务 dict | `data.inputs` / `data.phase_outputs` / `data.scratch` 三区 | `[F-v3-state-conflict]`, `[F-v3-runtime-state-mapping-failed]` |
| phase 直接读全量 data | `build_phase_input` 构造 phase-local view：canonical inputs + 上游 phase_outputs flatten 后再按 `io.inputs` 过滤 | 未声明输出写回用 `[F-v3-runtime-state-mapping-failed]` |
| phase output 写顶层 key 或 `data={phase_name: ...}` | `wrap_phase_output` 统一写 `data.phase_outputs[phase_id]` | read-only inputs 写入抛 `[F-v3-runtime-state-mapping-failed]` |
| wrapper 覆盖不完整 | PhaseWrapper 覆盖 Agent / LOGIC / SUBGRAPH / builtin reference reader | double-wrap 抛 `[F-v3-runtime-state-mapping-failed]` |
| child graph 可能继承 parent data/messages | SUBGRAPH / subagent child 入口硬置 `phase_outputs={}`、`scratch={}`、`messages=[]` | parent leak prevention |
| reference reader 只是状态 stub | `ReferenceReaderRuntime` + `ReaderSandboxState` 激活，`flow.timeout_s=60` | `[F-v3-reference-reader-failed]`, `[F-v3-resource-reference-path-invalid]` |
| finish_task flat 写回 | `cognitive_flow` 写 `phase_outputs[phase_name]` | schema gate 仍用 `[F-v3-agent-output-schema-invalid]` 等 |

## BlackboardData 与 reducer

`BlackboardData` 的持久区：

- `inputs`: canonical 初始入参。执行期只读。
- `phase_outputs`: `dict[phase_id, dict]`，归档每个 phase 的结构化产出。
- `scratch`: 草稿区，当前 phase-local 和 child 沙盒不会继承父 scratch。

`blackboard_data_merge` 是当前 `data` reducer：

- right 写不同 `inputs` 时 fatal：`[F-v3-runtime-state-mapping-failed] data.inputs is read-only after initialization`
- 重复写同一 `phase_outputs[phase_id]` 时 fatal：`[F-v3-state-conflict]`
- 重复写同一 scratch key 时 fatal：`[F-v3-state-conflict]`

## Canonical inputs vs phase-local view

这里必须区分两个 “inputs”：

- canonical `data.inputs`: 持久黑板里的入口事实，只保存初始入参，执行期只读。
- phase-local `data.inputs`: `build_phase_input` 产出的一次性局部视图，用来给当前 phase 解析模板、LOGIC context 和工具输入。它可以包含上游 `phase_outputs` flatten 后的业务字段。

`_phase_local_inputs` 的确定性约定：

- raw inputs 优先于上游产出，因为代码用 `setdefault`，不会覆盖已有输入。
- 多个上游 phase 输出同名字段时，按 `phase_outputs` 插入序先到先得。

这让 text-segmentation 这类 “segment phase 写 `segments_summary`，review phase 读取 `{segments_summary}`” 的同图横向数据流可用，同时不改变 canonical inputs 的只读语义。

## StateMapper

`build_phase_input` 当前行为：

1. 规范化 `state.data`。
2. `deepcopy(data["phase_outputs"])`，把上游产出嵌套区透传给当前 phase。
3. `_phase_local_inputs(data["inputs"], phase_outputs)` 把上游业务字段合入局部 inputs。
4. `filter_runtime_inputs(..., input_schema)` 按当前 phase `io.inputs.properties` 做读取漏斗。
5. `scratch={}`、`messages=[]`，阻断草稿和 ReAct 对话跨 phase 泄漏。
6. `flow` 深拷贝，`run_id` 透传。

`wrap_phase_output` 当前行为：

- 普通 dict 业务输出写入 `phase_outputs[phase_id]`。
- 输出带 `inputs` 时 fatal，因为 canonical inputs read-only。
- 有 `output_schema.properties` 时，未声明 key fatal：`[F-v3-runtime-state-mapping-failed] phase wrote undeclared keys: ...`

## PhaseWrapper 四类节点

`graph_assembler` 中当前接入：

- LOGIC：`node_kind="logic"`
- Agent/Skill：`node_kind="agent"` / `"skill"`
- SUBGRAPH：`node_kind="subgraph"`
- builtin reference reader：`node_kind="reference_reader"`

wrapper 给返回函数打 `__graph_agent_phase_wrapped__` 和 `__graph_agent_phase_node_kind__`。重复包装会抛 `[F-v3-runtime-state-mapping-failed] double-wrap rejected...`，保证每层 graph 只有一层漏斗。

## Child graph 与 subagent 隔离

SUBGRAPH child state 和 subagent child state 都显式从 fresh blackboard 开始：

- `data.inputs`: 仅 explicit phase/tool input。
- `data.phase_outputs`: `{}`。
- `data.scratch`: `{}`。
- `messages`: `[]`。

同图横向 phase output 会进入下游 phase-local view；纵向 child graph 不继承 parent `phase_outputs`。这是 γ2 当前实现的核心边界。

Child result 只取 child `phase_outputs`。SUBGRAPH 用确定性聚合后交给 parent phase wrapper；subagent 作为 tool result 返回给 parent Agent。没有 phase_outputs 时不再走 flat diff fallback。

## Reference reader 沙盒

`ReferenceReaderRuntime.initial_state()` 通过 `ReaderSandboxState` 建 fresh blackboard：

- `data.inputs.skill_id`
- `data.inputs.phase_id`
- `data.phase_outputs={}`
- `data.scratch={}`
- `flow.timeout_s=60`
- `messages=[]`
- `run_id=None`

`read_reference` 工具调用时再加入 `reference_id` 和 `path`。路径读取由 `_read_skill_root_file` 校验，越权或不存在抛 `[F-v3-resource-reference-path-invalid]`；reader 输入缺 path 抛 `[F-v3-reference-reader-failed]`。

## finish_task 写回

`CognitiveFlowMiddleware.handle_finish_task_tool_result` 成功后写：

```python
data = {
    "inputs": {},
    "phase_outputs": {phase_name: final_write},
    "scratch": {},
}
```

这替代了 Round 11/12 的 `data={phase_name: final_write}`。原因是 finish_task、LOGIC、SUBGRAPH 都要落到同一套 `phase_outputs[phase_id]` 归档和冲突检测语义。

## 与当前源码的差异

本文件已同步 PR γ2 当前实现，不再保留 “当前源码仍是 flat data” 的旧差异表。剩余未完全覆盖的目标态主要在更上游的 root runtime input schema 严格校验、完整 reference reader WARN fallback trace 等后续工作；不影响本文记录的三区 state/IO 合同。
