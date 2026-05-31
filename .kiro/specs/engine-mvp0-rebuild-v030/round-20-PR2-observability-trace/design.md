# PR-2 Design: 主运行路径观测能力重建与 Trace 落盘

## 1. 契约继承与变动表 (SOP-06)

| 影响面 | 变更摘要 | 兼容性分类 | 迁移路径 |
| :--- | :--- | :--- | :--- |
| `PhaseStartEvent` | 继承现有事件定义。上下文（context）约定为对齐 `LLMPhaseNode` 的现有契约：**传入完整的业务数据状态 (`state.get("data", {})`)**。 | [COMPATIBLE] | 内部事件，与现存的 Harness/LLMPhaseNode 平行引擎保持行为一致。 |
| `PhaseEndEvent` | 继承现有事件定义。上下文（context）同上，传入最终完整的业务数据状态。 | [COMPATIBLE] | 内部事件，调用方兼容。 |
| `LLMCallEvent` | 继承。在 `_skill_node` 内截获 `response.response_metadata.token_usage`，缺失时默认 `0`。 | [COMPATIBLE] | 自动接入现有体系。 |
| `ToolCallEvent` | 继承。记录 `tool_name`, `call_args` 和 `result`。返回值为 dict/list 时统一序列化为 JSON 字符串。 | [COMPATIBLE] | 自动接入现有体系。 |
| `WorkflowResult.trace_path` | 修复：之前返回一个未写入的 `trace.json` 伪造路径，现在返回 `TracingCallback.save()` 的真实输出文件路径。 | [BREAKING] (SOP-06 A类) | A类 charter 修复，无需用户显式授权。业务应用现应依赖返回值中的真实路径来访问 trace。 |

## 2. 关键设计决策

### 2.1 承认平行引擎并统一 Context 形态
V0.3.0 的 `graph_assembler` 实际上与原有的 `Harness -> PhaseExecutor -> LLMPhaseNode` 构成**平行运行引擎**（例如 `parallel_map` 子运行可能依然经过旧路径）。在旧路径中，`on_phase_start/end` 发送的 `context` 是完整的业务数据 (`state["data"].model_dump()`)。
**设计：** 为了让 Studio 拿到统一形态的输入输出视图，`_skill_node` 派发的 `PhaseStartEvent` 和 `PhaseEndEvent` 的 `context` 必须对齐既有契约，传递完整的数据快照，而不是输入子集或局部增量。

### 2.2 `_skill_node` 级事件发射 (Event Emission)
我们将把原来在 `core.harness` 中的 `_safe_emit_event` 抽取为一个公共 helper，例如 `graph_agent.callbacks.emit._safe_emit_event`，以消除依赖耦合。

在 `_skill_node` 内进行事件发射：
- **Phase 启动:** 进入 `_skill_node` 时，发出 `PhaseStartEvent(..., context=dict(state.get("data", {})))`。
- **大模型调用:** 在 `model.invoke` 后发出 `LLMCallEvent`。对于 mock llm 或未能提供 token 的场景，**即使 token 缺失也必须发射事件**，将 `input_tokens` 和 `output_tokens` 降级为 `0`（同时注意归一化 prompt_tokens/completion_tokens 字段名变体）。
- **工具调用:** 所有工具成功执行后（包括普通业务工具、critic、subagent 以及 **`finish_task` 提前返回的工具调用**），发出 `ToolCallEvent`。考虑到事件契约中 `result` 是字符串类型，**如果结果是 dict 或 list，必须用 JSON 序列化为字符串**再发射。
- **Phase 结束:** 在 `_skill_node` 的**所有退出路径**（包含通过 `finish_task` 工具的提前返回路径，以及最后的正常返回路径）均需发出 `PhaseEndEvent`，并携带该阶段最终完整的 `data` 状态。

### 2.3 严防假绿：TracingCallback 提前挂载与物理落盘
原设计存在的致命假绿风险：如果仅仅在执行结束后调用 `.save(trace_dir)`，中间过程拦截的 Pydantic 事件将因为没有 `trace_dir` 而无法实时写入 `tracing.jsonl` 流文件。
**设计：**
1. **调用前绑定:** 在 `runner._run_v030_skill_dict` 执行 `graph.invoke` **之前**，计算好有效的 trace 目录，并确保 `TracingCallback(trace_dir=...)` 被正确初始化或对传入的空实例调用 `.set_trace_dir()` 绑定目标。
2. **执行后保存:** 执行完毕后调用 `.save(trace_dir)` 写入 summary。
3. 返回真实落盘文件路径到 `WorkflowResult.trace_path`。

## 3. 测试修缮与 Tests-First 策略 (诚实红灯)
1. **显式 V0.3.0 测试:** 构造测试用例时，必须显式准备一个 **V0.3.0 目录型 GRAPH.md root** 的 Skill 夹具，防止被错误路由到旧版 Harness 从而导致假绿。
2. **挂载拦截器 (Spy Callback):** 传入自定义 Callback，断言能够收到 `PhaseStart`, `LLMCall`, `ToolCall` (包含 `finish_task`) 和 `PhaseEnd`。
3. **断言真实落盘与内容:** 验证 `trace_path` 不为空且存在，同时验证 `tracing.jsonl` 中存在正确的 Pydantic 类型事件日志。
4. 在红灯呈现后，实施相应的重构使其转绿。