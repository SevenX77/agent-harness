# state-and-io-contract 运行逻辑 (PR β 当前实现)

署名：Codex / a1
日期：2026-05-25
定位：解释当前代码里状态切片、输出写回、schema gate 和 validator 契约怎样配合。本文只描述已落地行为。

## 1. StateMapper 如何切 phase 输入

`StateMapper` 是 phase wrapper 使用的状态切片器。它有两个字段：

- `input_schema`：当前 phase 声明的输入 schema，允许为 `None`。
- `output_schema`：当前 phase 声明的输出 schema，允许为 `None`。

`build_phase_input(state)` 会生成一个新的 phase-local state：

- `data`：从 `state["data"]` 里按 `input_schema.properties` 过滤字段。若没有 input schema 或 properties 为空，则复制全部 `state["data"]`。
- `flow`：深拷贝原 `state["flow"]`。
- `messages`：复制原 `state["messages"]` 列表。
- `run_id`：透传原 `state["run_id"]`。

所以它不是直接暴露全局 blackboard，而是先按 `io.inputs` 做字段过滤；但当 schema 未声明字段时，当前实现会兼容放行全部输入。

## 2. StateMapper 如何包住 phase 输出

`wrap_phase_output(output)` 只检查 `output["data"]`。如果 `data` 不存在或不是 dict，直接返回原 output。

当 `output_schema.properties` 不存在或为空时，当前实现直接放行。这是未声明输出字段时的兼容路径。

当存在输出字段声明时，检查规则是：

- 如果 `data` 只有一个顶层 key，且这个 key 对应的值是 dict，并且这个 nested dict 的字段全部属于 `io.outputs`，则放行。这支持 `data={phase_name: final_write}` 这种 phase 命名空间写回。
- 否则检查 `data` 的顶层 key 是否都在 `io.outputs` 允许字段里。
- 若发现未声明 key，抛 `[F-v3-runtime-state-mapping-failed] phase wrote undeclared keys: ...`。

`PhaseWrapper.wrap(node)` 会先用 `build_phase_input` 给 node 传局部 state，再用 `wrap_phase_output` 检查 node 返回值。若内部抛出非 GraphAgent fatal 异常，会统一包成 `[F-v3-runtime-state-mapping-failed] ...`。

## 3. finish_task 输出如何进入 data

Agent live 路径里，`finish_task` 工具执行后会交给 `CognitiveFlowMiddleware.handle_finish_task_tool_result`。

这个方法会先把原 `flow` 复制成 `next_flow`，再写入：

- `flow["finish_task_result"]`：保存原始 finish_task 工具结果。
- `flow["critic_metrics"]`：保存每个 critic 的 `invocations`、`passed`、`rejected`。

当 finish_task 工具结果不是 ok 时，方法只返回新的 `flow` 和 `messages`，不会写 `data`。

当结果 ok 且没有 strict output schema 时，方法直接接受工具返回的 `data`，返回：

```text
data = {phase_name: final_write}
```

当存在 strict output schema 时，方法会先走 schema gate；通过后再写同样的 `data={phase_name: final_write}`。这与 `StateMapper.wrap_phase_output` 的 nested dict 放行规则配套。

## 4. Schema gate 如何保护 io.outputs

`validate_finish_task_with_schema_gate` 负责把 finish_task 输出与 `io.outputs` 对齐。

输入有两种形态：

- `business_data_md`：字符串形态。helper 会先按 JSON object 解析；解析不出 dict 时返回 reject。
- `output`：已经解析好的 dict。live graph_assembler 路径传的是这个字段。

返回值 `FinishTaskSchemaGateResult` 的字段含义：

- `accepted`：是否通过 schema。
- `error_code`：失败时的 `[F-v3-agent-output-schema-missing]` 或 `[F-v3-agent-output-schema-invalid]`。
- `tool_message`：失败时给 LLM 看的 `finish_task` 错误消息。
- `final_write`：通过后准备写回 blackboard 的 dict。
- `output`：通过后的解析输出。
- `errors`：schema 失败的具体原因。

非终结兼容路径必须单独说明：live `handle_finish_task_tool_result` 先判断 `_has_strict_output_schema`。如果 schema 是 `None`、`SchemaObject.fields` 为空、或 JSON schema 的 `properties` 为空，当前实现会跳过 strict gate，直接接受写回。这是为了兼容 V2.1 或非终结阶段尚未提供 `io.outputs` 的情况。

只有 strict schema 存在时才会真正调用 gate。不匹配时返回带 `[F-v3-agent-output-schema-invalid]` 的 reject，不写 `final_write`，并把 `ToolMessage(status="error")` 追加回消息流，让模型重新修正。

## 5. Validator 契约与状态切片

`invoke_validator_with_contract` 的目标是固定业务 validator 的运行时签名：

```python
def validate(output: dict, state_slice: dict, **kwargs) -> None | dict:
```

字段级返回值 `ValidatorRuntimeResult`：

- `accepted`：`True` 表示 validator 通过或不存在；`False` 表示失败。
- `error_code`：失败时为 `[F-v3-agent-validator-failed]`。
- `feedback`：失败详情。返回 dict 会被序列化为 JSON；抛异常会记录异常类型和异常消息。
- `tool_message`：失败时给 LLM 的 `finish_task` 错误消息。

失败路径有两种，不只是异常：

- validator 返回 `None`：通过。
- validator 返回 dict：视为业务失败，转成 `[F-v3-agent-validator-failed]` 的 LLM 可见反馈。
- validator 抛异常：捕获异常，同样转成 `[F-v3-agent-validator-failed]` 的 LLM 可见反馈。

当前 live 路径尚未把 AST 上的 `validator: bool` 解析成具体 validator 实例，因此 `handle_finish_task_tool_result` 现在传入的是 `validator=None`。也就是说，本文描述的是 validator 契约和 helper 行为已经可用；完整业务 validator 注入仍是后续接线工作。
