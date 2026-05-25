---
spec: engine-mvp0-rebuild-v030/round-13-PR-gamma2-state-io-isolation
phase: PR γ2 (State/IO Isolation)
owner: a2 主笔 / a1 audit
工程量: 35-45h
---

# PR γ2: State/IO Isolation Research

## §0 继承字段表 (Round 9/10/11/12 不动)
- **ModelResolverProtocol**: 签名及职责不动。
- **Agent AST**: `exit_contract` 移除不动，业务 `validator` 开关语意不动，中间件顺序不动。
- **CognitiveFlowMiddleware**: 接管 `finish_task` / `ask_clarification` 职责不动。
- **SkillResolverProtocol**: 寻址闭环，入口必需 `skill_resolver` 不动。

## §1 现有代码占地考古与实证

当前 Engine 的 State 机制仍处于 V2.1 旧时代的大杂烩阶段，未对齐主 Spec (R6/R8)。

### 1.1 `state.py` 现状
- **位置**: `packages/graph-agent/src/graph_agent/runtime/state.py`
- **问题**: `BlackboardState` 的 `data` 字段 (`L38`) 仍然是 `Annotated[dict[str, Any], shallow_dict_merge]`，即顶层扁平字典的浅合并。并没有根据 V0.3.0 R6 的要求切分为 `inputs`, `phase_outputs`, `scratch` 三个严格分区。导致所有插件、Agent 和工具都可以无限制地读写顶层键。

### 1.2 `state_mapper.py` 现状
- **位置**: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`
- **问题**: 虽然存在 `StateMapper` 和 `PhaseWrapper`，但在 `build_phase_input` (`L43-L50`) 中，仅仅是对当前状态做了平铺过滤 (`filter_runtime_inputs`) 并直接作为 `data` 返回。没有构建出预期的隔离环境。
- **沙盒存根**: `L95` 已有 `ReaderSandboxState` 的 stub，但对应的 `core/builtin_subagents/reference_reader.py` 并**不存在**，仍需新建运行时实体。

### 1.3 SUBGRAPH 运行时的数据泄漏
- **位置**: `packages/graph-agent/src/graph_agent/core/graph_assembler.py` (L196 `_build_subgraph_node`)
- **问题**: 在子图被 invoke 时 (`L216-L219`)，代码直接做了 `before_data = dict(state.get("data", {}))`，并在 invoke 时原封不动传给了子图 `"data": before_data`。这导致父 Agent 积累的所有私密推演和无关变量被毫无保留地暴露给了子图，违反了 R8 的隔离要求。

### 1.4 subagent 运行时的数据泄漏
- **位置**: `packages/graph-agent/src/graph_agent/core/graph_assembler.py` (L573 `_invoke_subagent_once_t23`)
- **问题**: 执行单次 subagent 时，直接执行了 `child_data = {**before_data, **input_data}` (`L580`)。这意味着除了本次调用的显式 input 以外，父级的全部 `data` 都会被暴力塞入 `child_data` 中，是极其严重的上下文污染点。

## §2 目标引用
- 必须实现主 V0.3.0 spec 的 **R6** 要求：State shape 三区化。
- 必须实现主 V0.3.0 spec 的 **R8** 要求：子图不可继承 parent data。