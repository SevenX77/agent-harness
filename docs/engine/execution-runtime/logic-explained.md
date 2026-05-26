# execution-runtime 运行逻辑 (PR C 当前实现)

署名：Codex / a1
日期：2026-05-26
定位：把当前执行运行时代码翻译成自然语言。本文只描述当前 src 已经真实发生的行为，不提前描述后续目标态。

## 1. 入口与当前 live middleware 装配

公开入口仍是 `run_skill()`。它负责驱动图运行，并把成功或已知 GraphAgent 错误包装成 `WorkflowResult`。

目录型 V0.3.0 `GRAPH.md` root 会走 `_run_v030_skill_dict()`，不是旧 harness 缓存路径。这个分支现在会在 `graph.invoke()` 前准备 callbacks 和 trace 输出目录，再把 callbacks 传给 `assemble_graph()`，见 `packages/graph-agent/src/graph_agent/core/runner.py:488-526`。这点很重要：如果 `TracingCallback` 等到执行后才绑定目录，过程中产生的 typed events 就进不了 `tracing.jsonl`。

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

## 2.1 V0.3.0 Agent phase 的观测事件

当前 V0.3.0 Agent phase 的 live 执行体是 `graph_assembler._build_skill_node()` 内部的 `_skill_node`。它在同一个 ReAct 循环里执行模型、工具和 `finish_task`，并在这些边界发观测事件。

字段级行为：

- phase 进入时发 `PhaseStartEvent`。`context` 固定是完整 blackboard data：`{"inputs": ..., "phase_outputs": ..., "scratch": ...}`，由 `_observable_data_context()` 生成，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:381-384` 和 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:494-500`。这与旧 harness 的 `LLMPhaseNode` / `CodePhaseNode` 用 `state["data"].model_dump()` 发 start/end 的形态对齐，见 `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:129-130`、`packages/graph-agent/src/graph_agent/core/phase_nodes/code_phase_node.py:39`。
- 每次 `model.invoke(...)` 返回后发 `LLMCallEvent`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:403-417`。token 统计由 `_extract_token_usage()` 读取并归一；缺失、布尔值、不可转整数时降级为 `0`，字段名兼容 `input_tokens/output_tokens`、`prompt_tokens/completion_tokens`、`total_input_tokens/total_output_tokens`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:525-548`。
- 每个工具成功返回后发 `ToolCallEvent`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:422-447`。普通业务工具、critic/framework tool、subagent tool 和 `finish_task` 都走这条发射。`args` 只接受 dict；非 dict 时给空 dict。`result` 是字符串字段，dict/list 用 JSON 序列化，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:557-562`。
- phase 退出时发 `PhaseEndEvent`，并且只发一次。`_emit_phase_end()` 用 `phase_end_emitted` 防重，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:366-379`。覆盖 `finish_task` 早返回、无 tool call / max turns 正常返回、以及异常路径；异常路径在 `finally` 发事件后仍继续抛异常，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:456-479`。

`PhaseEndEvent.context` 也是完整 blackboard data。`finish_task` 成功时，response data 里的 `{phase_name: final_write}` 会被 `_phase_end_context()` 翻译成 `{"inputs": {}, "phase_outputs": {phase_name: final_write}, "scratch": {}}`；若 response data 已经是完整结构，则保留完整结构，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:503-522`。

## 2.2 V0.3.0 trace 如何真实落盘

`_run_v030_skill_dict()` 现在不再返回伪 `trace.json`。它的 trace 流程是：

1. 先计算输出目录：显式 `trace_dir` 优先；没有时，如果 runtime inputs 有 `output_dir`，使用 `Path(output_dir) / "traces"`，见 `packages/graph-agent/src/graph_agent/core/runner.py:506-509`。
2. 调 `_prepare_v030_callbacks(callbacks, trace_output)`。没有 callbacks 时创建 `LoggingCallback()`；有 trace 目录但没有 tracer 时追加 `TracingCallback(trace_dir=trace_output)`；已有 tracer 但未绑定 typed JSONL 路径时调用 `set_trace_dir(trace_output)`，见 `packages/graph-agent/src/graph_agent/core/runner.py:469-485`。
3. 把 `active_callbacks` 传给 model resolver 和 `assemble_graph()`，所以装配期 builtin reader 事件和运行期 `_skill_node` 事件都能进入同一批 callbacks，见 `packages/graph-agent/src/graph_agent/core/runner.py:511-526`。
4. `graph.invoke()` 完成后，遍历 `TracingCallback` 并调用 `.save(trace_output)`。返回的真实 summary JSON 路径写进 dict 的 `trace_path`，见 `packages/graph-agent/src/graph_agent/core/runner.py:537-552`。
5. `.save()` 失败时抛 `TraceWriteError("trace save failed: ...")`，并带 `context={"trace_path": str(trace_output)}`，见 `packages/graph-agent/src/graph_agent/core/runner.py:541-547`。

因此现在有两个文件概念：

- `tracing.jsonl`：执行期间由 `TracingCallback.on_event()` 逐行追加 typed Pydantic event。
- `{run_id}_summary.json`：执行结束后由 `TracingCallback.save()` 写出的 summary；`WorkflowResult.trace_path` 指向这个真实存在的 summary 文件。

这和旧行为不同：旧 V0.3.0 分支只是拼出 `Path(trace_dir) / "trace.json"` 字符串，不能证明文件存在，也没有把执行期事件写进 typed stream。

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

## 6. PR C 后的 exit_contract 退役与 system prompt 尾置

`runtime/exit_contract.py` 已删除。当前 V0.3.0 Agent 不再靠每轮 HumanMessage / SystemMessage 注入 exit contract，也不再做 inject / strip。输出契约现在固定写在 `cognitive/prompt.py` 的 `apply_v030_cognitive_template` 末尾：

```text
<exit_contract>
{V030_AGENT_EXIT_CONTRACT_TEXT}
<output_schema>
{schema_md}
</output_schema>
</exit_contract>
```

字段级行为：

- `V030_AGENT_EXIT_CONTRACT_TEXT`：固定中文系统规则，要求必须调用 `finish_task`，并说明 `business_data_md` 要遵循 `output_schema` 列业务字段、`diagnostics_md` 写自检诊断。它不是 Agent 文件里的可配置字段。
- `output_schema`：由 `graph_assembler` 从当前 phase 或 root `io.outputs` 取出，传给 `apply_v030_cognitive_template(output_schema=...)`；模板中用 `json.dumps(..., ensure_ascii=False, indent=2)` 生成 `schema_md`。没有 schema 时写 `{}`。
- `<exit_contract>` 的位置：固定在整个 system prompt 最末尾。这样做是利用 LLM 的近因偏置，把“最终必须怎样输出”放在最靠近模型生成的位置。
- `messages`：不再被塞入临时 exit contract 消息。消息历史只保留真实对话和工具消息，避免每轮重复注入造成上下文膨胀和旧契约残留。

相关失败码：

- `[F-v3-cognitive-output-schema-render-failed]`：规范层定义为 schema inline 失败的 FATAL。当前代码路径直接 JSON 序列化 dict；没有独立动态注入器。

## 7. V0.3.0 cognitive template 的 8 个固定容器

`apply_v030_cognitive_template` 是当前 Agent phase 的最终 system prompt 生成器。它消费编译后的 `AgentNodeAST` 字段和装配期资源处理结果，不重新解析 Markdown。

| 容器 | 真实占位 / 参数 | 字段来源 | 为空时默认 | 用途 | 失败码 |
|---|---|---|---|---|---|
| `<role>` | `role` | Agent body `<role>` | 编译期必填 | 告诉模型身份 | `[F-v3-agent-role-missing]` |
| `<goal>` | `goal` | Agent body `<goal>` | 编译期必填 | 告诉模型目标 | `[F-v3-agent-goal-missing]` |
| `<thinking_style>` | `steps_md` | `steps` 参数；每项格式为 `- [id] name: content` | `无显式步骤` | 固定思考规则 + 把 steps 平铺进“建议步骤” | `[F-v3-agent-step-invalid]` |
| `<knowledge_base>` | `knowledge_base_markdown` / `knowledge_base`、`reference_registry_listing` | 装配期 reference reader markdown + reference 注册清单 | `无预读取参考资料`、`无注册 Reference` | 给模型预读资料摘要，并列出可用 R-id | `[F-v3-reference-reader-failed]` WARN；path 非法为 `[F-v3-resource-reference-path-invalid]` FATAL |
| `<examples>` | `inline_examples`、`example_registry_listing`、兼容参数 `document_examples` | inline examples content + document examples id/summary | `无内联示范`、`无扩展案例` | 给短案例正文和长案例目录 | `[F-v3-resource-example-invalid]` |
| `<ambiguity_feedback>` | 固定文本 | 模板内置 | 固定存在 | 要求不清晰时调用 `log_ambiguity` 后继续保守执行 | 运行期由对应工具/trace 处理 |
| `<protocol_citation>` | `protocols_md` | `protocols` 参数；每项格式为 `- [protocol:id] content` | `无显式协议` | 要求判断写协议依据 | `[F-v3-agent-protocol-invalid]` |
| `<critical_reminders>` | 固定文本 | 模板内置 | 固定存在 | finish 前检查工具结果、输出 `diagnostics_md` + `business_data_md` | schema gate 失败为 `[F-v3-agent-output-schema-invalid]` |

额外容器：

- `<llm_role_prefix>`：当 `role_prefix` 非空时插入在 `<role>` 与 `<goal>` 之间，来自 `resolve_role_prefix_from_llm_role(phase_ast.llm_role)`。解析失败会 warning 并返回空字符串，不阻断装配。
- `<exit_contract>`：不是 8 个认知容器之一，但固定尾置，内嵌 `output_schema`。

`graph_assembler._agent_system_prompt` 传入的真实参数名是：`knowledge_base_markdown`、`reference_registry_listing`、`inline_examples`、`example_registry_listing`、`role_prefix`。旧版 alignment 里曾用过的 reader-subagent markdown 占位符不是当前代码里的占位符名。

## 8. C4 reference reader：装配期一次预读与 fallback 边界

`_build_skill_node` 在构造 Agent node 前调用 `_build_reference_reader_markdown`。这发生在 graph 装配期，不是每轮 Agent ReAct 循环。结果作为 `knowledge_base_markdown` 填入 `<knowledge_base>`。

字段级行为：

- `phase_ast.references`：空列表时直接返回空字符串，不创建 reader。
- `root`：由当前 `SKILL.md` 路径反推 skill root，作为资料读取根目录。
- `references`：`[item.model_dump() for item in phase_ast.references]`，每项至少包含 `id`、`path`、`summary`。
- `ReferenceReaderRuntime.skill_id`：`compiled.manifest.name`，用于定位当前 skill。
- `ReferenceReaderRuntime.phase_id`：当前 Agent phase id。
- `ReferenceReaderRuntime.max_output_tokens`：固定 `3000`，单份 fallback / reader 读取时按空白 token 截断。
- `ReferenceReaderRuntime.language`：固定 `"zh"`。
- `ReferenceReaderRuntime.timeout_s`：固定 `60`；`run()` 内用 `ThreadPoolExecutor(max_workers=1)` 和 `future.result(timeout=self.timeout_s)` 实现，超时抛 `[F-v3-reference-reader-failed] timeout`。
- `markdown`：reader 返回 dict 时读取 `result["markdown"]`；必须是非空字符串，否则进入 fallback。

失败策略：

- reader 超时、普通异常、或输出非法：记录 warning `[F-v3-reference-reader-failed] ...`，再调用 `_fallback_reference_reader_markdown`。
- fallback：先写 `[F-v3-reference-reader-failed] {reason}`，再逐个 `read_resource_file(...)` 读取 reference 原文，每份用 `_truncate_tokens(body, 3000)` 截断后写入 knowledge base。
- path 非法：`GraphAgentFatalError` 中包含 `[F-v3-resource-reference-path-invalid]` 时直接 re-raise，装配失败；审计修复后不再吞成 fallback 文本。

loader 也会在编译期跑 `_validate_agent_reference_paths`：绝对路径或 resolve 后不在 skill root 下，一律抛 `[F-v3-resource-reference-path-invalid]`。现在没有“逃逸后如果目标是真实文件就放行”的分支，所以“逃逸但目标真实存在”也会被 FATAL 阻断。

## 9. C5 `read_reference` / `read_example` runtime tools

这两个 builtin tool 在 Agent tool 集里由 `graph_assembler` 注入，读取范围只来自当前 Agent phase 的注册表。

`read_reference` 字段级契约：

- 入参 `reference_id`：必须是非空 string。否则抛 `[F-v3-tool-argument-invalid] reference_id must be a string`。
- 入参 `query`：当前实现接收但 `del query`，不参与读取。
- 入参 `mode`：当前实现接收但 `del mode`，不参与读取。
- `references` registry：key 是声明的 reference id；找不到 id 时在任何文件 IO 前短路抛 `[F-v3-resource-reference-not-found]`，不会尝试同名外部文件。
- `relative_path`：取 `spec.path` 后交给 `read_resource_file`。
- 路径校验：空 path、绝对路径、resolve 后不在 `root` 下、或不是可读文件，都抛 `[F-v3-resource-reference-path-invalid]`。越权检查使用 `candidate.relative_to(root_resolved)`。
- 返回值：合法时返回文件 UTF-8 文本。

`read_example` 字段级契约：

- 入参 `example_id`：必须是非空 string。否则抛 `[F-v3-tool-argument-invalid] example_id must be a string`。
- 入参 `query`：当前实现接收但 `del query`。
- `examples` registry：找不到 id 时在文件 IO 前短路抛 `[F-v3-resource-example-not-found]`。
- document example path：复用 `read_resource_file`，路径错误码为 `[F-v3-resource-example-path-invalid]`。
- 返回值：合法 document example 返回文件 UTF-8 文本；inline example 由 prompt 的 `<examples>` 直接提供，不走文件读取。

## 10. C7 LOGIC ActionRegistry 与输出字段硬门

当前 LOGIC phase 通过 `_build_logic_node` 顺序执行 `phase_ast.actions`。每个 action 都从 `compiled.actions.resolve(phase_id, action_name)` 取 callable。

Action name 沙盒：

- `_validate_action_name(name)` 拦截：非 string、空字符串、包含 `/`、包含 `\`、包含 `.`、或 `Path(name).is_absolute()`。
- 被拦截时抛 `[F-v3-logic-action-name-invalid] invalid action name ...`。
- `..` 不需要单独分支，因为已经被 “包含 `.`” 覆盖。

输出字段校验：

- `output_schema_keys`：从当前 LOGIC phase 的 `io.outputs.properties` 取 key 集。没有 schema / 没有 properties 时返回 `None`，表示不做字段白名单。
- `ctx` 就地突变路径：action 执行后，代码用 `_dict_delta(before | updates, data)` 捕捉 `Context(data, ...)` 中新写入或变化的字段，并立刻调用 `_validate_logic_update_keys(...)`。未声明字段抛 `[F-v3-logic-output-field-undeclared]`。
- action return 路径：action 必须返回 dict；非 dict 直接抛 `[F-v3-logic-action-return-invalid] action returned {type}, expected dict`。
- dict 返回路径：返回 dict 后也调用 `_validate_logic_update_keys(...)`；任何未声明字段同样抛 `[F-v3-logic-output-field-undeclared]`。
- 合法更新：ctx delta 和 return dict 都合并进 `updates`；phase node 返回 `{"data": updates}`，由 wrapper/StateMapper 进入 phase output 回写。

这里不截断错误，也不把未声明字段降级成 warning。静态 AST 扫描在 loader 中也会把可识别的 return literal / `context.update(...)` 未声明字段归到同一个 `[F-v3-logic-output-field-undeclared]`。

## 11. C6/D4 child flow 与 child graph 隔离

subagent 和 SUBGRAPH 两条 child 调用现在共享 `_child_flow(parent_flow)` 的隔离规则：

```python
flow = deepcopy(parent_flow) if isinstance(parent_flow, dict) else {}
flow["subagent_depth"] = current_subagent_depth(flow) + 1
```

字段级行为：

- `parent_flow`：只有 dict 会被 deepcopy；非 dict 按 `{}` 处理。
- `subagent_depth`：基于 deepcopy 后的 flow 计算，再加 1。这样 child 修改嵌套 flow 不会污染 parent。
- `child.data`：subagent child graph 以 `{"inputs": dict(input_data), "phase_outputs": {}, "scratch": {}}` 启动；SUBGRAPH 以当前 phase input 切片启动，不继承父图全量 data。
- `child.messages`：固定 `[]`，子 Agent 不继承父 Agent 的 ReAct 历史。
- `run_id`：subagent 单次调用把 parent `run_id` 放入 child state；RunnableConfig 仍可带 trace/run metadata，但执行控制状态不依赖 metadata。
- child output：subagent 用 `_deterministic_child_phase_outputs` 把 child `phase_outputs` 按 phase id 排序展平，重复 key 抛 `[F-v3-runtime-state-mapping-failed]`；SUBGRAPH 只按 declared output mapping 回写。

这解决的是“父子黑板引用别名”和“深度只在 metadata 里不可见”两类问题。父 flow 给 child 是副本，不是共享引用。

## 12. PR C 审计修复后的硬边界

两处 C4 must-fix 已进入 live 行为：

- `loader.py::_validate_agent_reference_paths`：reference path resolve 后逃逸 skill root 时，无论目标文件是否真实存在，都抛 `[F-v3-resource-reference-path-invalid]`。这堵住了“逃逸到真实文件被放行”的任意文件读取后门。
- `graph_assembler.py::_build_reference_reader_markdown`：装配期 reader 抛 `[F-v3-resource-reference-path-invalid]` 时直接 re-raise。它是 FATAL，不是 `[F-v3-reference-reader-failed]` fallback。

OBS5 清理也已同步：`actions.py::_validate_action_name` 不再保留 `name == ".."` 死分支；包含点号的 action name 已统一被 `"." in name` 拦截。
