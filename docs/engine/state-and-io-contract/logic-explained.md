# state-and-io-contract 运行逻辑 (PR γ2 当前实现)

署名：Codex / a1
日期：2026-05-25
定位：把当前源码里的 V0.3.0 三区 state、phase input/output funnel、child 隔离和 reference reader 沙盒逐字段翻译清楚。本文只描述已落地行为。

## 1. BlackboardData 三区

源码：`packages/graph-agent/src/graph_agent/runtime/state.py`

`BlackboardState.data` 现在不是 flat 业务 dict，而是 `BlackboardData` 三个区：

- `inputs`: canonical inputs。只保存运行入口的初始入参；执行期不能被 phase 返回值重写。
- `phase_outputs`: phase 产出归档，形状是 `dict[phase_id, dict]`。每个 phase 的业务输出写到自己的 namespace。
- `scratch`: 临时草稿区。当前 wrapper 给 phase-local view 清空 scratch，避免草稿跨 phase 或 child 边界泄漏。

`blackboard_data_merge(left, right)` 是 LangGraph 合并 `data` 的 reducer。它先用 `normalize_blackboard_data()` 把旧 flat dict 或三区 dict 规范化，再按区合并：

- `inputs`: 如果右侧写了 inputs，且左侧已有不同 inputs，抛 `[F-v3-runtime-state-mapping-failed] data.inputs is read-only after initialization`。原因是 canonical inputs 是入口事实，phase 不允许改写。
- `phase_outputs`: 逐 phase_id 合并；如果同一个 `phase_outputs[phase_id]` 被写第二次，抛 `[F-v3-state-conflict] phase_outputs[...] written more than once`。原因是 phase output 必须来源唯一。
- `scratch`: 同 key 二次写入抛 `[F-v3-state-conflict] scratch key=... written more than once`。原因是 scratch 没有声明式 schema，必须保守防并发覆盖。

`shallow_dict_merge` 现在只是 `blackboard_data_merge` 的兼容别名，不再是旧 flat 顶层浅合并语义。

## 2. Phase 输入如何构造

源码：`packages/graph-agent/src/graph_agent/runtime/state_mapper.py`

`StateMapper.build_phase_input(state)` 生成一次性的 phase-local state。它不是持久黑板本体。

字段级行为：

- 先读取并规范化 `state["data"]`。
- `phase_outputs = deepcopy(data["phase_outputs"])`，把同一张 graph 内已经完成的上游 phase output 嵌套区透传给下游。
- `_phase_local_inputs(data["inputs"], phase_outputs)` 生成 phase-local 输入视图：先复制 canonical `inputs`，再按 `phase_outputs` 的插入序遍历各 phase output，把业务字段用 `setdefault` 合进去。
- `filter_runtime_inputs(..., input_schema)` 再按当前 phase 的 `io.inputs.properties` 做 funnel。没有 properties 时放行当前 phase-local 输入视图。
- `scratch` 固定清空 `{}`。
- `messages` 固定清空 `[]`。
- `flow` 深拷贝。
- `run_id` 透传。

这里有一个容易误读的点：canonical `data.inputs` 仍然只读、只代表初始入参；phase-local `data.inputs` 是当前 phase 的解析视图，可以包含上游 phase output 的业务字段。设计文档里的 “inputs 只读” 指 canonical 区，不是这个一次性局部视图。

同名字段的确定性规则也在代码里：`_phase_local_inputs` 用 `setdefault`，所以 raw inputs 优先于上游产出；多个上游 phase 产出同名字段时，按 `phase_outputs` 插入序先到先得。

## 3. Phase 输出如何写回

源码：`packages/graph-agent/src/graph_agent/runtime/state_mapper.py`

`StateMapper.wrap_phase_output(output)` 只处理 node 返回里的 `output["data"]`。

字段级行为：

- 如果 `data` 不存在或不是 dict，原样返回 output。
- 如果返回值已经是三区结构，即包含 `inputs` / `phase_outputs` / `scratch` 任一 key，则先规范化。
- 如果三区返回里带 `inputs`，抛 `[F-v3-runtime-state-mapping-failed] data.inputs is read-only`。这是写路径强制只读。
- 普通业务 dict 返回时，先看 `output_schema.properties`。如果声明了输出字段，返回 key 不在 properties 里就抛 `[F-v3-runtime-state-mapping-failed] phase wrote undeclared keys: ...`。
- 通过后统一包装成：

```python
{
    "data": {
        "inputs": {},
        "phase_outputs": {phase_id: dict(data)},
        "scratch": {},
    }
}
```

所以 γ2 后不再支持 `data={phase_name: final_write}` 这种 flat/nested 兼容写回。phase 产出只能归档到 `data.phase_outputs[phase_id]`。

## 4. PhaseWrapper 覆盖的四类节点和 double-wrap guard

源码：`packages/graph-agent/src/graph_agent/runtime/state_mapper.py`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py`

`PhaseWrapper(mapper, node_kind).wrap(node)` 是统一的输入/输出漏斗。`graph_assembler` 通过 `_wrap_phase_runtime_node(...)` 接入三类物理 phase：

- `node_kind="logic"`: `LOGIC.md`
- `node_kind="agent"` / `"skill"`: `SKILL.md`
- `node_kind="subgraph"`: `SUBGRAPH.md`

第 4 类是 builtin reference reader。它不在 `phases/` 目录中，但 `_build_reference_reader_node()` 也用 `PhaseWrapper(..., node_kind="reference_reader")` 包起来。

double-wrap guard 的机制是装配期标记：

- wrapper 返回的函数会带 `__graph_agent_phase_wrapped__ = True`
- 同时记录 `__graph_agent_phase_node_kind__ = node_kind`
- 如果再把已包装函数传给 `PhaseWrapper.wrap()`，抛 `[F-v3-runtime-state-mapping-failed] double-wrap rejected: ... node is already wrapped`

这个 guard 的原因是每层 graph 只能有一层输入/输出漏斗。重复包裹会让 child graph 顶层再被 parent wrapper 解释一次，破坏隔离边界。

## 5. ReferenceReaderRuntime 与 ReaderSandboxState

源码：

- `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`

`ReferenceReaderRuntime.initial_state()` 只做一件事：用 `ReaderSandboxState(...).to_blackboard()` 构造独立沙盒。

沙盒字段：

- `data.inputs.skill_id`: 当前 skill id，用于定位。
- `data.inputs.phase_id`: 当前 Agent phase id。
- `data.phase_outputs`: `{}`。
- `data.scratch`: `{}`。
- `flow.timeout_s`: 默认 `60`。
- `messages`: `[]`。
- `run_id`: `None`。

`graph_assembler.read_reference()` 在工具被 LLM 调用时创建 `ReferenceReaderRuntime(skill_id=compiled.manifest.name, phase_id=..., root=..., timeout_s=60)`，然后把 `reference_id` 和 `path` 加进 sandbox inputs，再调用 `reference_reader` wrapper。真正读文件仍通过 `_read_skill_root_file()`，越权路径或不可读路径抛 `[F-v3-resource-reference-path-invalid]`。

reader 失败的统一错误前缀是 `[F-v3-reference-reader-failed]`，例如缺少 reference path 时由 `_build_reference_reader_node()` 抛出。当前源码已删除未调用的 `fallback_payload` 死方法；WARN fallback 的完整策略不在这个 runtime class 里伪装存在。

## 6. Child funnel 隔离

源码：`packages/graph-agent/src/graph_agent/core/graph_assembler.py`

SUBGRAPH 和 subagent child 入口都显式创建新的 child blackboard，而不是传父黑板：

- SUBGRAPH: `{"data": {"inputs": child_input, "phase_outputs": {}, "scratch": {}}, "messages": [], ...}`
- subagent: `{"data": {"inputs": dict(input_data), "phase_outputs": {}, "scratch": {}}, "messages": [], ...}`

这说明同一 graph 内横向 phase 可以读上游 `phase_outputs`，但纵向 child 边界不能穿透。parent 的 `phase_outputs`、`scratch`、`messages` 都不会进入 child。

SUBGRAPH child 结束后，父节点读取 child 的 `phase_outputs`，用 `_deterministic_child_phase_outputs()` 按 phase_id 排序聚合业务字段。如果多个 child phase 输出同名 key，抛 `[F-v3-runtime-state-mapping-failed] duplicate child output key ...`。父 SUBGRAPH phase 再由外层 `PhaseWrapper` 包装到 `data.phase_outputs[parent_phase_id]`。

subagent child 同样只从 child `phase_outputs` 取结果；如果 child 没有 phase output，不再回退 flat diff。

## 7. finish_task 写回 cutover

源码：`packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py`

Round 11/12 的旧语义是 finish_task 成功后写：

```python
data = {phase_name: final_write}
```

γ2 改成三区结构：

```python
data = {
    "inputs": {},
    "phase_outputs": {phase_name: final_write},
    "scratch": {},
}
```

原因是 Agent finish_task 和 LOGIC/SUBGRAPH 都必须走同一个 phase output 归档语义。这样 reducer 能按 `phase_outputs[phase_id]` 做冲突检测，Studio/trace 也能稳定知道某个业务字段来自哪个 phase。

finish_task schema gate 仍由 `validate_finish_task_with_schema_gate` 负责。strict schema 失败时返回 `[F-v3-agent-output-schema-invalid]` 或 `[F-v3-agent-output-schema-missing]`，并通过 ToolMessage 让模型修正；不写 `phase_outputs`。
