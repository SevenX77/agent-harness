# PR E 组 (tracing-and-observability) 调研报告

本文档基于对现有代码库的实证分析（Grep & Read），梳理了 `tracing-and-observability` 相关的实际现状与缺口，为接下来的架构设计提供事实依据。

## 1. 代码库现状核实 (Grep 实证)

### 1.1 Trace Event 的定义与序列化机制
- **实证结果**：在 `packages/graph-agent/src/graph_agent/callbacks/events.py` 中，目标事件 `AmbiguityLoggedEvent` (line 168), `BuiltinSubagentEnterEvent` (line 181), `BuiltinSubagentExitEvent` (line 191), `BuiltinSubagentFallbackEvent` (line 201) **均已完整定义为 Pydantic 数据类**。
- **关键发现**：它们并没有使用独立的 `Enum` 类进行类别定义，而是直接在 Pydantic field 中使用了 `Literal["ambiguity_logged"]` 等鉴别器标签（Discriminator）。这意味着**不会存在现有 serializer 拒绝新 enum 值的风险**，只要事件类纳入了 `CallbackEvent` 联合类型，就能被默认序列化机制直接支持。

### 1.2 `log_ambiguity` 的接线现状
- **实证结果**：`cognitive/ambiguity.py` 文件中确实存在 `_emit_ambiguity_logged(ctx, record)` 的调用。
- **关键发现**：目前该函数执行时，仅能在控制台看到 `logger.warning("ambiguity_logged callback failed: %s", exc)` 的日志打印。这表明它并没有成功获取到活跃的 LangChain callback 处理器或全局事件总线。处于“已定义但未有效 emit (dead wire)”的状态。

### 1.3 Builtin Reference Reader 的接线现状
- **实证结果**：PR C 刚刚合入的 `core/graph_assembler.py` (`_build_reference_reader_markdown` 方法) 和 `core/builtin_subagents/reference_reader.py` 中，**完全没有任何 trace event 的 emit 操作**。
- **关键发现**：目前异常和 fallback 仅仅通过 `logger.warning("[F-v3-reference-reader-failed] %s", exc)` 打印字符串。

## 2. 核心风险点剖析

### 2.1 装配期 (Assembly Time) 的 `run_id` 问题
- **分析**：Reference Reader 发生在 `graph.invoke()` 之前，这意味着此时并没有 LangGraph 的 `RunnableConfig`，也不会有本次调用的全局 `run_id`。
- **结论**：查阅 `events.py` 发现，所有 `BuiltinSubagent*Event` 的 `run_id` 字段均声明为 `str | None = None`。在装配期触发事件时，显式将 `run_id` 留空（`None`）是完全合法且符合规范预期的，`phase_id` (如 "main") 则能够正常传递，用于前端 Canvas 节点定位。

### 2.2 `AMBIGUITY_LOGGED` 与 `TOOL_CALL_END` 的重叠问题
- **分析**：`log_ambiguity` 是一个标准 Tool，必须触发 LangChain 标准的 `tool_call_start` / `tool_call_end` 才能维护状态机的完整性。
- **结论**：这两个事件在语义上不冲突。`TOOL_CALL` 提供的是执行耗时、工具启停边界；而 `AMBIGUITY_LOGGED` 是一种高阶业务反馈。应保留 Tool 的基本事件，额外并列触发 `AMBIGUITY_LOGGED`，并可共用相同的 `tool_call_id` 用于链路追踪。

### 2.3 Fallback Payload 大小与敏感度问题
- **分析**：如果在 trace 中夹带了长达数千 token 的降级参考资料，会导致 tracing 链路负担过重及 OOM 风险。
- **结论**：`events.py` 中定义的 `BuiltinSubagentFallbackEvent` payload 仅包含 `fallback_reason` (枚举)、`fallback_strategy` (短字符串)、`excerpt_token_limit` (数字) 和 `warning` (短字符串)。只要严格按照此 Pydantic 模型实例化，自然就能切断大文本的泄露。大文本应只流入 `knowledge_base_markdown` 交给 Prompt。