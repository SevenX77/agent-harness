# tracing-and-observability V0.3.0 代码逻辑翻译

本文解释 V0.3.0 完成态下 `tracing-and-observability` 子模块具体做什么、为什么这样做、每个事件字段如何校验。它不是 baseline 的现状盘点, 也不是 mvp0-alignment 的改造路线; 它把 `callbacks/events.py` 的 Pydantic event union、callback 投递链路、typed trace 写盘、ambiguity feedback 和 builtin subagent 事件翻译成自然语言。

核心源码锚点:

- `_EventBase` 和 33 个 Pydantic event 子类定义在 `packages/graph-agent/src/graph_agent/callbacks/events.py:42`, `packages/graph-agent/src/graph_agent/callbacks/events.py:55`。
- 每个事件子类用 `event_type: Literal["..."] = "..."` 作为 discriminator tag, 最后通过 `CallbackEvent = Annotated[..., Field(discriminator="event_type")]` 组成 discriminated union: `packages/graph-agent/src/graph_agent/callbacks/events.py:448`。
- `Callback.on_event()` 是兼容层: 新 typed event 会回分发到旧 `on_phase_start()` / `on_tool_call()` 等 hook, 但 typed-only event 需要 callback 覆盖 `on_event()`: `packages/graph-agent/src/graph_agent/callbacks/base.py:139`。
- `TracingCallback.on_event()` 是 typed stream sink, 直接把 Pydantic event 写到固定文件 `tracing.jsonl`: `packages/graph-agent/src/graph_agent/callbacks/tracing.py:101`, `packages/graph-agent/src/graph_agent/callbacks/tracing.py:113`。
- `log_ambiguity()` 成功记录业务歧义后发 `AmbiguityLoggedEvent`: `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:26`, `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:75`。
- Harness 的 `_safe_emit_event()` 负责 fan-out 到所有 callback, 并吞掉 callback 自身异常: `packages/graph-agent/src/graph_agent/core/harness.py:219`。

## 这个模块的边界

Tracing 只记录已经发生的 runtime / assembly 事实。它不决定 phase 是否能执行, 不校验 graph schema, 不替 StateMapper 生成 phase input, 不替 tool schema 校验参数, 也不选择模型。它负责三件事:

| 事项 | 归属 |
|---|---|
| 事件 payload 的强类型结构 | tracing-and-observability |
| 业务执行和 phase 生命周期 | execution-runtime |
| `phase_input` / `phase_output` 的合法切片 | state-and-io-contract |
| `target_skill` / child skill 可达性 | skill-resolution |
| Studio 时间线、反馈面板、节点染色 | Studio 消费端 |

难点 1: **标签扣**。这里的事件协议不是一个集中枚举表, 而是每个 Pydantic class 自带一个 `Literal` 标签。标签扣错, Pydantic union 就无法把 JSON line 还原成正确 class。

## 事件协议: _EventBase + Literal discriminator

`events.py` 的设计是: 公共字段放在 `_EventBase`, 每个事件是一个独立 Pydantic model, 每个 model 固定自己的 `event_type`, 最后由 `CallbackEvent` discriminated union 统一反序列化: `packages/graph-agent/src/graph_agent/callbacks/events.py:42`, `packages/graph-agent/src/graph_agent/callbacks/events.py:448`。

文件头还说明了一个实现约束: 这里故意不启用 postponed annotations, 因为 Pydantic 需要在 class 定义时拿到 `Literal` tag 表达式: `packages/graph-agent/src/graph_agent/callbacks/events.py:24`。

### _EventBase 字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `model_config.extra` | 禁止事件带未声明字段 | 未声明字段会让 Studio 误以为协议已经支持某个 payload | `ConfigDict(extra="forbid")`; 多余字段 Pydantic validation 失败 | `[F-v3-runtime-phase-failed]` / writer 侧 validation error |
| `schema_version` | 标识 typed event schema 版本 | 事件流需要跨版本可读 | `Literal["1.0"]`, 默认 `SCHEMA_VERSION` | `[F-v3-runtime-phase-failed]` |
| `timestamp` | 事件发生时间 | Timeline 排序和审计依赖时间戳 | 默认 `_utc_now_iso()` 生成 UTC ISO 字符串 | `[F-v3-runtime-phase-failed]` |
| `sub_run_id` | parallel child run 分组 id | 并行 child run 混在一条 trace 里时需要折叠 | `str | None`, 默认 `None` | 无 |
| `group_key` | parallel_map sibling 共享分组 key | Studio 需要把同一 fan-out 的 siblings 折叠展示 | `str | None`, 默认 `None` | 无 |

### union 字段

| 字段 / 对象 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `event_type` | Pydantic discriminator 字段 | 没有它就无法从 JSON line 还原具体事件类 | 每个子类声明一个固定 `Literal["..."]` 默认值 | `[F-v3-runtime-phase-failed]` |
| `CallbackEvent` | 所有事件子类的 typed union | callback sink 需要接收单一类型入口 | `Annotated[Union, Field(discriminator="event_type")]` | `[F-v3-runtime-phase-failed]` |
| `__all__` | 明确公开事件类 | 避免消费者 import 私有对象 | 导出 `SCHEMA_VERSION`, `CallbackEvent`, 所有事件类 | 无 |

## 33 个事件类总览

当前源码里 `CallbackEvent` union 包含 33 个 `_EventBase` 子类。任务背景提到的 22 个是旧计数; 本文按当前 `events.py` 真实 class 列表解释。

| Event class | `event_type` Literal | 核心字段 |
|---|---|---|
| `PhaseStartEvent` | `"phase_start"` | `phase_name`, `context` |
| `PredictChainStartEvent` | `"predict_chain_start"` | `metadata` |
| `PhaseEndEvent` | `"phase_end"` | `phase_name`, `context`, `metrics` |
| `LLMCallEvent` | `"llm_call"` | `phase_name`, `input_tokens`, `output_tokens`, `messages`, `response_data` |
| `ToolCallEvent` | `"tool_call"` | `phase_name`, `tool_name`, `args`, `result`, `duration_ms` |
| `ValidationFailEvent` | `"validation_fail"` | `phase_name`, `errors`, `retry_count` |
| `RetryEvent` | `"retry"` | `phase_name`, `target_phase`, `feedback` |
| `FinishTaskEvent` | `"finish_task"` | `phase_name`, `reasoning`, `evidence` |
| `NudgeEvent` | `"nudge"` | `phase_name`, `nudge_count`, `nudge_type` |
| `WorkingMemoryUpdateEvent` | `"working_memory_update"` | `phase_name`, `content_length`, `content` |
| `DeadEndPrunedEvent` | `"dead_end_pruned"` | `phase_name`, `summary` |
| `CompactionEvent` | `"compaction"` | `phase_name`, `removed_pairs`, `removed_summary`, `content_ref` |
| `AmbiguityReportEvent` | `"ambiguity_report"` | `phase_name`, `ambiguity_type`, `question`, `decision` |
| `AmbiguityLoggedEvent` | `"ambiguity_logged"` | `phase_name`, `ambiguity_type`, `question`, `decision`, `reason`, `related_refs`, `related_protocols` |
| `BuiltinSubagentEnterEvent` | `"builtin_subagent_enter"` | `run_id`, `phase_name`, `builtin_name`, `payload` |
| `BuiltinSubagentExitEvent` | `"builtin_subagent_exit"` | `run_id`, `phase_name`, `builtin_name`, `payload` |
| `BuiltinSubagentFallbackEvent` | `"builtin_subagent_fallback"` | `run_id`, `phase_name`, `builtin_name`, `fallback_reason`, `fallback_strategy`, `excerpt_token_limit`, `warning` |
| `PromptCapturedEvent` | `"prompt_captured"` | `phase_name`, `llm_role`, `resolved_model`, `template_source`, `variables`, `resolved_prompt`, `loop_index` |
| `LLMFallbackEvent` | `"llm_fallback"` | `phase_name`, `from_provider`, `to_provider`, `reason` |
| `RunStartedEvent` | `"run_started"` | `run_id`, `thread_id`, `is_resume`, `initial_context` |
| `RunEndedEvent` | `"run_ended"` | `run_id`, `thread_id`, `status`, `final_context`, `wall_time_seconds` |
| `ValidationPassEvent` | `"validation_pass"` | `phase_name`, `retry_count` |
| `RetryExhaustedEvent` | `"retry_exhausted"` | `phase_name`, `max_retries`, `final_errors` |
| `ModelResolvedEvent` | `"model_resolved"` | `phase_name`, `tier`, `role_name`, `resolved_model`, `thinking_enabled`, `model_override`, `call_chain` |
| `ArtifactSavedEvent` | `"artifact_saved"` | `phase_name`, `name`, `path`, `size_bytes` |
| `ParallelMapGroupStartedEvent` | `"parallel_map_group_started"` | `group_key`, `skill_path`, `item_count`, `max_concurrent`, `item_as` |
| `ParallelMapGroupEndedEvent` | `"parallel_map_group_ended"` | `group_key`, `succeeded`, `failed`, `wall_time_seconds` |
| `AgentLoopIterationEvent` | `"agent_loop_iteration"` | `phase_name`, `iteration` |
| `InterruptedEvent` | `"interrupted"` | `phase_name`, `thread_id`, `question`, `clarification_type`, `options` |
| `ResumedEvent` | `"resumed"` | `thread_id`, `human_input`, `resumed_from_phase` |
| `HeartbeatEvent` | `"heartbeat"` | `current_phase`, `elapsed_seconds`, `memory_usage_mb` |
| `ThreadCleanedUpEvent` | `"thread_cleaned_up"` | `thread_id`, `checkpoint_count_at_cleanup` |
| `InternalErrorEvent` | `"internal_error"` | `entry_point`, `error_type`, `error_message`, `traceback` |

## 核心生命周期事件字段

这些事件描述 run、phase、LLM、tool、validation 和 finish_task 主路径。旧 hook 和 typed event 同时存在: legacy hook 方便旧 callback, typed event 进入 `tracing.jsonl`。

| 字段 / 事件 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `RunStartedEvent.run_id` | 标识一次 run | 所有后续事件需要归属 | 必填 string | `[F-v3-runtime-phase-failed]` |
| `RunStartedEvent.thread_id` | 标识 checkpoint / HITL 线程 | resume 和 cleanup 依赖 thread | 必填 string | `[F-v3-runtime-phase-failed]` |
| `RunStartedEvent.is_resume` | 区分首次运行和恢复运行 | Studio timeline 需要知道 run 是否续接 | boolean, 默认 `False` | 无 |
| `RunStartedEvent.initial_context` | 保存初始可 JSON 化上下文 | debug 需要知道运行入口 state | dict, 默认 `{}` | `[F-v3-runtime-state-mapping-failed]` |
| `RunEndedEvent.status` | 记录结束状态 | completed / crashed / interrupted 影响 UI 队列 | Literal `completed|crashed|interrupted`, 默认 `completed` | `[F-v3-runtime-phase-failed]` |
| `RunEndedEvent.final_context` | 保存结束上下文 | 输出面板和失败诊断要读最终 state | dict, 默认 `{}` | `[F-v3-runtime-state-mapping-failed]` |
| `RunEndedEvent.wall_time_seconds` | run 总耗时 | 性能分析和 timeout 判断依赖它 | 必填 float | 无 |
| `PhaseStartEvent.phase_name` | 标识 phase 开始 | Canvas 节点状态从这里变为 running | 必填 string | `[F-v3-runtime-phase-failed]` |
| `PhaseStartEvent.context` | phase 开始时上下文快照 | Edge Inspection 需要输入侧证据 | dict, 默认 `{}`; 应来自 StateMapper 切片 | `[F-v3-runtime-state-mapping-failed]` |
| `PhaseEndEvent.context` | phase 结束时上下文快照 | 输出侧要和输入侧对齐 | dict, 默认 `{}`; 应是已校验输出/上下文 | `[F-v3-runtime-state-mapping-failed]` |
| `PhaseEndEvent.metrics` | phase 运行指标 | duration、token、tool 数等汇总需要落地 | dict, 默认 `{}` | 无 |
| `LLMCallEvent.input_tokens` | LLM 输入 token 数 | 成本和压缩策略依赖 token 统计 | int, 必填 | 无 |
| `LLMCallEvent.output_tokens` | LLM 输出 token 数 | 同上 | int, 必填 | 无 |
| `LLMCallEvent.messages` | LLM 请求摘要 | Prompt debug 需要复现模型输入 | `list[dict] | None`; 可截断 | `[F-v3-runtime-phase-failed]` |
| `LLMCallEvent.response_data` | LLM 响应摘要 | 需要看到模型输出和 tool_calls | `dict | None`; 可截断 | `[F-v3-runtime-phase-failed]` |
| `ToolCallEvent.tool_name` | 工具真实名称 | Q13 要求 per-tool 定位, 不能只有泛化 tool end | 必填 string | `[F-v3-tool-argument-invalid]` |
| `ToolCallEvent.args` | 工具入参 | Studio 需要展示实际执行参数 | dict, 默认 `{}`; 应是 validated args | `[F-v3-tool-argument-invalid]` |
| `ToolCallEvent.result` | 工具返回摘要 | 用户要知道工具产出 | 必填 string; 大结果应截断 | `[F-v3-runtime-phase-failed]` |
| `ToolCallEvent.duration_ms` | 工具耗时 | 找慢工具和超时原因 | `float | None` | 无 |
| `ValidationFailEvent.errors` | validator 失败原因 | retry/nudge 需要可读反馈 | list[str], 默认 `[]` | domain-specific |
| `ValidationFailEvent.retry_count` | 当前重试次数 | 判断是否耗尽 retry | int, 必填 | `[F-v3-runtime-phase-failed]` |
| `ValidationPassEvent.retry_count` | 通过前消耗的重试数 | 成功也需要知道是否靠 retry 修复 | int, 必填 | 无 |
| `RetryEvent.target_phase` | retry 路由目标 | Studio 需要画回退边 | 必填 string | `[F-v3-runtime-phase-failed]` |
| `RetryEvent.feedback` | retry 反馈 | 下次 phase 输入和 trace 需要一致 | list[str], 默认 `[]` | domain-specific |
| `RetryExhaustedEvent.max_retries` | 最大重试次数 | 解释为什么进入降级或失败 | int, 必填 | `[F-v3-runtime-phase-failed]` |
| `RetryExhaustedEvent.final_errors` | 最终错误列表 | 失败摘要不能只写 retry exhausted | list[str], 默认 `[]` | domain-specific |
| `FinishTaskEvent.reasoning` | Agent 结束理由 | 解释为什么可结束 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `FinishTaskEvent.evidence` | 结束证据列表 | 审计输出依据 | list[str], 默认 `[]` | 无 |

## Cognitive / memory / prompt 事件字段

这些事件解释 Agent 内部循环为什么这样走: prompt 是什么、模型如何解析、何时更新 working memory、何时压缩历史、何时 nudge。

| 字段 / 事件 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `PromptCapturedEvent.phase_name` | 定位哪次 phase prompt | prompt debug 必须回到节点 | 必填 string | `[F-v3-cognitive-slot-render-failed]` |
| `PromptCapturedEvent.llm_role` | 记录 LLM role | 模型路由解释需要 role | `str | None` | `[F-v3-agent-llm-role-unknown]` |
| `PromptCapturedEvent.resolved_model` | 记录实际模型 | role 不是最终 provider/model | `str | None` | resolver/model domain |
| `PromptCapturedEvent.template_source` | prompt 模板来源 | Debug 要知道是哪个模板渲染 | `str | None` | `[F-v3-cognitive-slot-render-failed]` |
| `PromptCapturedEvent.variables` | 模板变量 | slot 渲染错误要定位变量 | dict, 默认 `{}` | `[F-v3-cognitive-slot-render-failed]` |
| `PromptCapturedEvent.resolved_prompt` | 最终消息列表 | 这是发给模型的真实输入 | list[dict], 默认 `[]`; 应截断敏感/超长内容 | `[F-v3-runtime-phase-failed]` |
| `PromptCapturedEvent.loop_index` | 当前 phase 内第几次 LLM 调用 | ReAct 多轮要能分组 | int, 默认 `1`, `ge=1` | `[F-v3-runtime-phase-failed]` |
| `ModelResolvedEvent.tier` | phase tier | 解释模型选择入口 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `ModelResolvedEvent.role_name` | 解析后的 role 或 override role | 区分普通 tier 和 model override | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `ModelResolvedEvent.resolved_model` | 实际模型 code | Studio 需要展示 provider/model | `str | None` | resolver/model domain |
| `ModelResolvedEvent.thinking_enabled` | 是否启用 thinking | 推理模型行为和成本不同 | `bool | None` | 无 |
| `ModelResolvedEvent.model_override` | phase 是否覆盖模型 | override 是重要诊断信号 | `str | None` | resolver/model domain |
| `ModelResolvedEvent.call_chain` | resolver 尝试链 | fallback 或 peer group 需要解释 | list[str], 默认 `[]` | resolver/model domain |
| `LLMFallbackEvent.from_provider` | fallback 来源 provider | 需要知道谁失败 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `LLMFallbackEvent.to_provider` | fallback 目标 provider | 需要知道实际由谁接管 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `LLMFallbackEvent.reason` | fallback 原因 | 没有原因无法判断 provider 健康 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `NudgeEvent.nudge_count` | 第几次 nudge | 防止无限 nudge | int, 必填 | `[F-v3-runtime-phase-failed]` |
| `NudgeEvent.nudge_type` | nudge 类型 | 区分 standard / planning 等提示 | string, 默认 `"standard"` | 无 |
| `WorkingMemoryUpdateEvent.content_length` | working memory 长度 | 不读全文也能判断规模 | int, 必填 | 无 |
| `WorkingMemoryUpdateEvent.content` | working memory 全文 | Studio replay 需要准确内容 | `str | None` | `[F-v3-runtime-phase-failed]` |
| `DeadEndPrunedEvent.summary` | 被剪枝路径摘要 | 解释为什么某条思路被放弃 | string, 必填 | 无 |
| `CompactionEvent.removed_pairs` | 压缩删除的消息对数 | 解释上下文为什么变短 | int, 必填 | 无 |
| `CompactionEvent.removed_summary` | 压缩摘要 | 不打开 sidecar 也能看懂 | `str | None` | 无 |
| `CompactionEvent.content_ref` | sidecar JSON 引用 | 完整被删消息不应塞进主事件 | `str | None`, 相对路径 | `[F-v3-runtime-phase-failed]` |
| `AgentLoopIterationEvent.iteration` | Agent loop 第几轮 | 多轮 LLM/tool 事件需要 anchor | int, 必填, 语义 1-based | 无 |

## Ambiguity feedback 事件字段

`log_ambiguity()` 是非阻塞业务反馈工具: 缺 context 时返回 ignored; 有 context 时把 record 写入 `ctx["_ambiguity_reports"]`, 再调用 `_emit_ambiguity_logged()`: `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:26`, `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:63`。

`_emit_ambiguity_logged()` 从 context 取 `_callbacks`, 构造 `AmbiguityLoggedEvent`, 从 question + reason 中用 regex 提取 `@reference:*` 和 `@protocol:*`, 再对每个 callback 调 `on_event(payload)`: `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:75`, `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:83`。

| 字段 / 事件 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `log_ambiguity.question` | 记录不确定点 | Studio ambiguity 面板需要原问题 | string, 必填 | `[F-v3-tool-argument-invalid]` |
| `log_ambiguity.ambiguity_type` | 业务分类 | 反馈处理和报表按分类聚合 | Literal `missing_info|ambiguous_requirement|approach_choice|risk_confirmation|suggestion` | `[F-v3-tool-argument-invalid]` |
| `log_ambiguity.decision` | 本次运行采用的决策 | 反馈闭环要知道 Agent 如何继续 | string, 必填 | `[F-v3-tool-argument-invalid]` |
| `log_ambiguity.reason` | 决策理由 | 只记录 decision 不足以复盘 | string, 默认 `""` | 无 |
| `ctx` | 注入 runtime context | 没有 context 就没有 callback 和当前 phase | `dict | None`; `None` 时返回 ignored | 无 |
| `ctx["_ambiguity_reports"]` | 本 run 内累计报告 | 后续 phase 或输出可读取 | list; 非 list 时重建 | 无 |
| `AmbiguityLoggedEvent.phase_name` | Canvas 定位 | feedback 必须能回到 Agent phase | `str | None`, 来自 `_current_phase` | 无 |
| `AmbiguityLoggedEvent.ambiguity_type` | typed event 分类 | 前端不应解析 tool result 字符串 | string, 必填 | `[F-v3-tool-argument-invalid]` |
| `AmbiguityLoggedEvent.question` | typed event 原问题 | 面板展示主文本 | string, 必填 | `[F-v3-tool-argument-invalid]` |
| `AmbiguityLoggedEvent.decision` | typed event 决策 | 面板展示保守处理 | string, 必填 | `[F-v3-tool-argument-invalid]` |
| `AmbiguityLoggedEvent.reason` | typed event 理由 | 面板和审核需要解释 | string, 默认 `""` | 无 |
| `AmbiguityLoggedEvent.related_refs` | 从文本提取的 reference ids | 帮用户跳到资料 | list[str], 默认 `[]`; regex `@reference:([A-Za-z0-9_-]+)` | `[F-v3-resource-reference-not-found]` |
| `AmbiguityLoggedEvent.related_protocols` | 从文本提取的 protocol ids | 帮用户跳到规则 | list[str], 默认 `[]`; regex `@protocol:([A-Za-z0-9_-]+)` | `[F-v3-mention-target-not-found]` |

难点 2: **双通道**。`log_ambiguity` 既返回普通 tool result, 又发业务专属 typed event。普通 tool result 让 Agent 继续运行, typed event 让 Studio 不用从字符串里猜业务语义。

## Builtin subagent 事件字段

V0.3.0 把 builtin reference reader 和用户 subagent 分开观测。事件类已经存在于 `events.py`: `BuiltinSubagentEnterEvent`, `BuiltinSubagentExitEvent`, `BuiltinSubagentFallbackEvent`: `packages/graph-agent/src/graph_agent/callbacks/events.py:178`, `packages/graph-agent/src/graph_agent/callbacks/events.py:188`, `packages/graph-agent/src/graph_agent/callbacks/events.py:198`。当前 grep 只发现类定义和 union/export, 没发现实际 emit 点; 完成态要求 reader 调用前、成功后、fallback 时分别发这些事件。

| 字段 / 事件 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `BuiltinSubagentEnterEvent.run_id` | 归属一次 run | 装配期 reader 也要关联 run | `str | None`, 默认 `None` | 无 |
| `BuiltinSubagentEnterEvent.phase_name` | 关联目标 Agent phase | reader 是为某个 Agent phase 装配 knowledge_base | string, 必填 | `[F-v3-reference-reader-input-invalid]` |
| `BuiltinSubagentEnterEvent.builtin_name` | 标识 builtin 组件 | 防止和用户 subagent 混淆 | string, 必填; 完成态当前应为 `reference_reader` | `[F-v3-reference-reader-input-invalid]` |
| `BuiltinSubagentEnterEvent.payload` | reader 输入摘要 | 记录 reference ids、trigger_stage 等 | dict, 默认 `{}` | `[F-v3-reference-reader-input-invalid]` |
| `BuiltinSubagentExitEvent.payload` | reader 成功输出摘要 | 记录 used_reference_ids、warnings、duration 等 | dict, 默认 `{}`; 不应塞完整大文档 | `[F-v3-reference-reader-output-invalid]` |
| `BuiltinSubagentFallbackEvent.fallback_reason` | 降级原因 | WARN 需要可机器聚合 | Literal `remote_timeout|remote_error|config_missing|invalid_output|local_io_error` | `[F-v3-reference-reader-failed]` |
| `BuiltinSubagentFallbackEvent.fallback_strategy` | 降级方式 | 用户需要知道系统如何继续 | string, 必填; 如 raw excerpt fallback | `[F-v3-reference-reader-failed]` |
| `BuiltinSubagentFallbackEvent.excerpt_token_limit` | fallback 摘录上限 | 控制 trace/prompt 体积 | `int | None` | 无 |
| `BuiltinSubagentFallbackEvent.warning` | 人类可读警告 | TracePanel 展示具体原因 | string, 默认 `""` | `[F-v3-reference-reader-failed]` |

## Run / HITL / artifact / parallel 事件字段

这些事件不是 V0.3.0 三个新增点的核心, 但它们已在同一个 union 中, 读事件流时必须知道字段语义。

| 字段 / 事件 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `ArtifactSavedEvent.name` | artifact 展示名 | Studio artifact panel 需要稳定名称 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `ArtifactSavedEvent.path` | artifact 文件位置 | UI 要能打开或引用文件 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `ArtifactSavedEvent.size_bytes` | artifact 大小 | 展示和保留策略需要大小 | int, 必填 | 无 |
| `ParallelMapGroupStartedEvent.group_key` | fan-out 分组 key | child events 要折叠在同组 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `ParallelMapGroupStartedEvent.skill_path` | 被 fan-out 的 child skill | 解释并行调用对象 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `ParallelMapGroupStartedEvent.item_count` | fan-out item 数 | 进度和结果计数 | int, 必填 | 无 |
| `ParallelMapGroupStartedEvent.max_concurrent` | 并发上限 | 性能诊断和限流 | int, 必填 | 无 |
| `ParallelMapGroupStartedEvent.item_as` | child 参数名 | 复盘 child input mapping | string, 必填 | 无 |
| `ParallelMapGroupEndedEvent.succeeded` | 成功 item 数 | 并行批处理结果 | int, 必填 | 无 |
| `ParallelMapGroupEndedEvent.failed` | 失败 item 数 | 同上 | int, 必填 | domain-specific |
| `ParallelMapGroupEndedEvent.wall_time_seconds` | 并行组耗时 | 性能分析 | float, 必填 | 无 |
| `InterruptedEvent.thread_id` | 被中断线程 | HITL resume 需要 thread | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `InterruptedEvent.question` | 向人类提出的问题 | UI 需要展示待回答内容 | `str | None` | 无 |
| `InterruptedEvent.clarification_type` | 澄清类型 | 前端选择不同输入控件 | `str | None` | 无 |
| `InterruptedEvent.options` | 候选选项 | 多选/单选 UI 需要选项 | list[str], 默认 `[]` | 无 |
| `ResumedEvent.human_input` | 解除中断的人类输入 | replay 必须可复现 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `ResumedEvent.resumed_from_phase` | 从哪个 phase 恢复 | timeline 需要续接位置 | `str | None` | 无 |
| `HeartbeatEvent.current_phase` | 当前运行 phase | 长时间静默时 UI 仍知道卡在哪 | `str | None` | 无 |
| `HeartbeatEvent.elapsed_seconds` | 已运行秒数 | 长任务健康检查 | float, 必填 | 无 |
| `HeartbeatEvent.memory_usage_mb` | 内存占用 | 诊断 memory pressure | `float | None` | 无 |
| `ThreadCleanedUpEvent.thread_id` | 被清理线程 | checkpoint 生命周期审计 | string, 必填 | 无 |
| `ThreadCleanedUpEvent.checkpoint_count_at_cleanup` | 清理时 checkpoint 数 | 解释 cleanup 影响 | `int | None` | 无 |
| `InternalErrorEvent.entry_point` | crash 入口 | 区分 run/resume/subgraph | Literal `run|resume|subgraph` | `[F-v3-runtime-phase-failed]` |
| `InternalErrorEvent.error_type` | Python 异常类名 | 快速聚类 engine crash | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `InternalErrorEvent.error_message` | 异常文本 | 人类定位问题 | string, 必填 | `[F-v3-runtime-phase-failed]` |
| `InternalErrorEvent.traceback` | traceback | 工程师排查根因 | string, 必填 | `[F-v3-runtime-phase-failed]` |

## emit 和订阅链路

事件有两条兼容路径: 旧 hook 路径和 typed `on_event()` 路径。旧 hook 由 `Callback.on_event()` 反向分发, `TracingCallback` 则直接写 typed JSONL, 避免同一个事件被双写。

| 链路节点 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| emitter | 构造具体 Pydantic event | 事件必须在真实执行点发出, 不能由外围猜测 | 传入字段通过 Pydantic model validation | event-specific |
| `_safe_emit_event(callbacks, event)` | fan-out 到所有 callback | 一个坏 callback 不能打断 run | 遍历 callbacks, 调 `cb.on_event(event)`, 异常只 log | 无 |
| `Callback.on_event()` | typed event 到 legacy hook 的兼容层 | 旧 callback 只实现 `on_tool_call` 等 hook | 对已知 legacy 事件 `isinstance` 分发; typed-only event 只 debug | 无 |
| `TracingCallback.on_event()` | typed event stream sink | Studio 需要原始 Pydantic event JSONL | 调 `_write_typed_event(event)` | `[F-v3-runtime-phase-failed]` |
| `TracingCallback._write_typed_event()` | 写 `tracing.jsonl` | 固定文件名是 Studio-facing source | 有 trace dir 时追加 `event.model_dump_json()` 一行 | write failure WARN / runtime wrapper |
| legacy `_write_event()` | 写旧 shape JSONL | 兼容旧工具 | 写 `{timestamp, run_id, event_type, phase, data}` | write failure WARN / runtime wrapper |

实际 emit 例子:

- Harness run entry 发 `RunStartedEvent`: `packages/graph-agent/src/graph_agent/core/harness.py:604`。
- Harness heartbeat 线程定期发 `HeartbeatEvent`: `packages/graph-agent/src/graph_agent/core/harness.py:172`。
- Harness run success / interrupted / crashed 发 `RunEndedEvent` 和 `InternalErrorEvent`: `packages/graph-agent/src/graph_agent/core/harness.py:731`, `packages/graph-agent/src/graph_agent/core/harness.py:744`。
- LLM phase 解析模型后发 `ModelResolvedEvent`: `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:161`。
- LLM phase working memory 更新和 compaction 发 `WorkingMemoryUpdateEvent` / `CompactionEvent`: `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:498`, `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:534`。
- `log_ambiguity()` 发 `AmbiguityLoggedEvent`: `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:83`。

## Phase Wrapper 中的 emit 时机

V0.3.0 的完成语义要求 phase lifecycle event 贴近 wrapper, 因为 wrapper 才知道 StateMapper 切片前后边界。当前 `state-and-io-contract` 的 `PhaseWrapper` 负责切片和封口, tracing 应在同一层记录 phase input/output。

| 时机 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| phase input 切片后 | 发 phase start / node start 类事件 | 不能记录父图全量黑板 | payload 来自 StateMapper 已授权输入 | `[F-v3-runtime-state-mapping-failed]` |
| node 执行前 | 记录开始时间 | duration 需要起点 | monotonic time | 无 |
| LLM invoke 前 | 发 prompt capture / LLM start | prompt 是实际模型输入 | prompt payload 可 JSON 化且截断 | `[F-v3-cognitive-slot-render-failed]` |
| tool invoke 前 | 发 tool call start 或 legacy tool call 前半段 | 工具参数必须是 validated args | tool schema 校验后再发 | `[F-v3-tool-argument-invalid]` |
| node 输出封口后 | 发 phase end / node end | 输出必须先过 `io.outputs` | payload 来自 StateMapper 封口结果 | `[F-v3-runtime-state-mapping-failed]` |
| exception 捕获处 | 发 internal/runtime error | 错误必须带入口和 traceback | 转成 `InternalErrorEvent` 或 domain-specific event | `[F-v3-runtime-phase-failed]` |

## 错误码全清单

Tracing 自身尽量不制造业务错误码; 它引用 runtime、cognitive、tool、resource、resolver 等 domain 的错误码, 并把 code 带进事件 payload 或错误事件。

| 错误码 | 阶段 | 触发条件 | 修复方向 | 来源 |
|---|---|---|---|---|
| `[F-v3-runtime-phase-failed]` | 运行期 | phase 执行异常、event payload validation 失败或无法归入更细错误 | 查看 `InternalErrorEvent` / traceback / phase payload | `docs/engine/skill-spec/11-error-code-spec.md:160` |
| `[F-v3-runtime-state-mapping-failed]` | 运行期 | trace 要记录的 phase input/output 无法由 StateMapper 生成或封口 | 修 phase IO 和上游输出 | `docs/engine/skill-spec/11-error-code-spec.md:159` |
| `[F-v3-cognitive-slot-render-failed]` | 装配期 | prompt/template slot 不能渲染为可追踪 payload | 检查 Agent body AST 和 template variables | `docs/engine/skill-spec/11-error-code-spec.md:154` |
| `[F-v3-cognitive-output-schema-render-failed]` | 装配期 | output schema 无法嵌入 exit_contract 或 prompt capture | 修正 `io.outputs` | `docs/engine/skill-spec/11-error-code-spec.md:155` |
| `[F-v3-tool-argument-invalid]` | 运行期 | tool trace 的 args 未通过 tool schema 或 ambiguity 参数非法 | 修 tool 调用参数 | `docs/engine/skill-spec/11-error-code-spec.md:158` |
| `[F-v3-reference-reader-input-invalid]` | 装配期 | builtin reader enter payload 输入非法 | 检查 references registry | `docs/engine/skill-spec/11-error-code-spec.md:156` |
| `[F-v3-reference-reader-output-invalid]` | 装配期 | builtin reader exit payload 输出非法 | 修 reader 输出 JSON | `docs/engine/skill-spec/11-error-code-spec.md:157` |
| `[F-v3-reference-reader-failed]` | 装配期 WARN | reader 超时、异常、输出非法后 fallback | 查看 fallback reason, 使用 raw excerpt 继续 | `docs/engine/skill-spec/11-error-code-spec.md:138` |
| `[F-v3-resource-reference-not-found]` | 运行期 | ambiguity 或 tool trace 引用不存在 reference | 修正 reference id | `docs/engine/skill-spec/11-error-code-spec.md:129` |
| `[F-v3-mention-target-not-found]` | 编译期 / 运行期 | ambiguity trace 关联 protocol 不存在 | 修正 `@protocol:*` | `docs/engine/skill-spec/11-error-code-spec.md:114` |
| `[F-v3-skill-not-registered]` | 编译期 / 装配期 | subagent/subgraph trace 关联 target skill resolver miss | 导入或注册 skill | `docs/engine/skill-spec/11-error-code-spec.md:146` |

## V0.3.0 三个改造点如何落地

| 改造点 | 完成态代码语义 |
|---|---|
| C14 | `log_ambiguity()` 成功后除了普通 tool result, 还发 `AmbiguityLoggedEvent(event_type="ambiguity_logged")`; Studio ambiguity 面板消费 typed event, 不从 tool result 字符串解析。 |
| C15 | builtin reference reader 使用 `BuiltinSubagentEnterEvent` / `BuiltinSubagentExitEvent`, `event_type` 分别是 `"builtin_subagent_enter"` / `"builtin_subagent_exit"`; 它们和用户 subagent trace 分开。 |
| 改造点 3 | reader timeout、remote/local error、config missing、invalid output 走 `BuiltinSubagentFallbackEvent(event_type="builtin_subagent_fallback")`, `fallback_reason` 是 Literal 集合, severity 语义是 WARN, runtime 可继续。 |

读代码时建议先看 `callbacks/events.py` 的 `_EventBase` 和 `CallbackEvent` union, 再看 `callbacks/base.py` 的兼容分发, 然后看 `callbacks/tracing.py` 如何写 `tracing.jsonl`, 最后看 `cognitive/ambiguity.py` 和 harness / phase node 中的 `_safe_emit_event()` 调用点。
