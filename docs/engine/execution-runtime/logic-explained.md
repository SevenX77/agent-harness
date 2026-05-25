# execution-runtime 运行逻辑 (PR β 当前实现)

署名：Codex / a1
日期：2026-05-25
定位：把当前执行运行时代码翻译成自然语言。本文只描述当前 src 已经真实发生的行为，不提前描述后续目标态。

## 1. 入口与当前 live middleware 装配

公开入口仍是 `run_skill()`。它负责驱动图运行，并把成功或已知 GraphAgent 错误包装成 `WorkflowResult`。

PR β 已新增 `build_middleware_chain`，按 `MVP0_MIDDLEWARE_ORDER_CONTRACT` 可实例化 6 层顺序：

```text
ProtocolValidation → CognitiveFlow → ExecutionControl → Tracing → ToolError → LoopDetection
```

但当前 live 路径还没有把这 6 层完整接进 `graph_assembler` 主循环。`graph_assembler` 现在只调用 `build_middleware_chain_cognitive_flow(phase_name=phase_id)`，也就是只装一层 `CognitiveFlowMiddleware` helper。其余 5 层在 factory 中已经能构造，其中 `Tracing`、`ToolError`、`LoopDetection` 目前是可实例化的 no-op skeleton；真正接入主循环留给后续 wire-in。

## 2. finish_task 在 graph_assembler 中如何移交给 CognitiveFlow

Agent phase 仍是 LLM 工具循环。模型每轮输出 tool call 后，`graph_assembler` 先按 tool name 找到具体工具并调用。工具结果会先被追加成 `ToolMessage`，然后统一交给 `CognitiveFlowMiddleware.handle_finish_task_tool_result` 判断。

`handle_finish_task_tool_result` 的输入字段含义如下：

- `tool_name`：本次工具名。不是 `finish_task` 时直接返回 `None`，表示 CognitiveFlow 不处理。
- `tool_result`：工具执行结果。若不是 dict，会按空 dict 处理。
- `output_schema`：当前 phase 的输出 schema。当前只在 terminal phase 从 `io.outputs` 传入；非 terminal phase 传 `None`。
- `flow`：当前执行流状态。方法会复制一份，避免原地修改调用者传入对象。
- `messages`：当前消息列表。schema 或 validator reject 时，会向这里追加 LLM 可见的错误 `ToolMessage`。
- `critic_metrics`：critic 统计。方法会把每个 metric 的 `invocations`、`passed`、`rejected` 写进 `flow["critic_metrics"]`。

返回值有三类：

- `None`：不是 `finish_task`，外层继续普通工具流程。
- `{"flow": ..., "messages": ...}`：`finish_task` 没有成功，或 schema/validator reject，需要把错误反馈给模型继续修正。
- `{"flow": ..., "messages": ..., "data": {phase_name: final_write}}`：`finish_task` 被接受，`data` 下只写当前 phase 名对应的最终业务输出。

## 3. Schema gate 的当前真实规则

`validate_finish_task_with_schema_gate` 是一个可单测的严格 schema gate。它接收 `business_data_md` 或已解析好的 `output`，再用 `output_schema` 走 `SchemaEngine.validate`。

字段级返回值 `FinishTaskSchemaGateResult`：

- `accepted`：布尔值。`True` 表示 schema 校验通过；`False` 表示需要驳回给模型。
- `error_code`：失败时的错误码。当前使用 `[F-v3-agent-output-schema-missing]` 或 `[F-v3-agent-output-schema-invalid]`。
- `tool_message`：失败时生成的 `ToolMessage(status="error")`，内容包含错误码、phase 和具体错误。
- `final_write`：通过时准备用于写回 `data` 的 dict；失败时为 `None`。
- `output`：通过时的解析后输出；失败时为 `None`。
- `errors`：失败原因列表，例如 JSON 不是对象、schema 无法解析、字段类型不匹配。

触发条件要区分“helper 直接调用”和“live graph_assembler 路径”：

- 直接调用 `validate_finish_task_with_schema_gate(output_schema=None)` 时，会返回带 `[F-v3-agent-output-schema-missing]` 的 reject。
- live `handle_finish_task_tool_result` 会先调用 `_has_strict_output_schema`。`output_schema is None`、`SchemaObject.fields` 为空、或 JSON schema 没有非空 `properties` 时，都视为非 strict schema，直接接受并写回。这是当前为 V2.1/非终结阶段保留的兼容放行。
- 只有存在 strict output schema 时，live 路径才调用 schema gate。若 `validation.ok == False`，返回带 `[F-v3-agent-output-schema-invalid]` 的 reject；若 schema 解析或转换异常，也会被捕获并转成同一个错误码的 reject。这里不是向外抛异常，而是返回 LLM 可见的错误消息。

## 4. Validator runtime 契约与当前接线状态

`invoke_validator_with_contract` 已落地 validator runtime 的统一调用契约：

```python
def validate(output: dict, state_slice: dict, **kwargs) -> None | dict:
```

字段级返回值 `ValidatorRuntimeResult`：

- `accepted`：布尔值。`True` 表示业务验证通过或没有 validator；`False` 表示需要把反馈交给模型重试。
- `error_code`：失败时为 `[F-v3-agent-validator-failed]`；通过时为 `None`。
- `feedback`：失败时的文本反馈。validator 返回 dict 时会被 JSON 序列化；validator 抛异常时会写入异常类型和消息。
- `tool_message`：失败时生成的 `ToolMessage(status="error")`，内容包含错误码、phase 和反馈文本。

当前 live 路径尚未把 `AgentNodeAST.validator=True` 解析成具体 validator 实例。`handle_finish_task_tool_result` 内部调用 `invoke_validator_with_contract` 时传的是 `validator=None`。因此 PR β 当前完成的是“validator runtime 契约接口和失败反馈形态”，不是“AST bool 到业务 validator 实例的完整注入”。这部分留给后续 PR。

## 5. ask_clarification 与普通工具透传

`intercept_ask_clarification` 统一处理 attended 和 unattended 两条路径。

字段级返回值 `ClarificationResult`：

- `answer`：返回给模型的回答文本。
- `source`：回答来源。当前可能是 `human_interrupt`、`unattended_auto_answer` 或 `needs_human_input`。

attended 模式下，方法把 `question` 和 state 合成 payload，调用 `interrupt_fn(payload)`。如果在 LangGraph runnable context 内运行，返回值会作为人工回答，`source="human_interrupt"`。如果在 context 外调用并触发特定 RuntimeError，则降级为 `source="needs_human_input"`，answer 使用 state 中的 message 或原始 question。

unattended 模式下，不允许人工介入。方法返回中文系统提示，要求模型基于现有上下文做最保守推测，并在最终 `diagnostics_md` 中记录想问的问题、推测和依据，`source="unattended_auto_answer"`。

`dispatch_tool_call` 只负责普通工具透传。非 `finish_task` / `ask_clarification` 工具会直接调用传入的 `handler(tool_name, args)` 并返回 handler 结果。只有 `finish_task` 或 `ask_clarification` 这两个认知流工具会返回 `{"handled": False, "tool_name": ..., "args": ...}`，表示该 helper 不在这里处理它们。
