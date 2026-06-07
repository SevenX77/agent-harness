---
doc: uncovered-areas
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 15 块 / 未迁 4 块 / 2026-06-04 -->

~~# Uncovered Areas — MVP1 冲突核对记录~~ → ✅[已迁入](../../00-architecture-overview.md#6-跨切纪律防-drift)

本文登记决策记录 §15 指出的未覆盖项，并逐一对照新设计确认是否冲突。结论只用于 MVP1/V4 设计收口；不改代码，不改 gateway。

~~## 覆盖范围~~ → ✅[已迁入](../../00-architecture-overview.md#6-跨切纪律防-drift)

覆盖范围：本文登记 predict、subagent lifecycle、checkpointer × middleware 三块，并补充 D-test-3 的 gateway 编排实证项。

| 未覆盖项 | 当前证据 | 初步结论 |
|---|---|---|
| predict | `packages/graph-agent/src/graph_agent/core/runner.py:163-283`、`packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:29-140` | 与 create_agent 迁移有交互，必须保留 predict_context 和 mock binding。 |
| subagent lifecycle / SkillResolverProtocol DI | `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:33-93`、`packages/graph-agent/src/graph_agent/core/loader.py:528-545`、`packages/graph-agent/src/graph_agent/core/loader.py:595-615` | 与 SubagentDispatchMiddleware 迁移兼容，但 DI 不能被 middleware 隐式全局化。 |
| checkpointer × middleware | `packages/graph-agent/src/graph_agent/core/checkpointer.py:38-160`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:150-151`、`packages/graph-agent/src/graph_agent/core/phase_executor.py:82-100` | 与 create_agent 内层 checkpointer 有潜在冲突，需要实测。 |
| create_agent × GatewayChatModel | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:581-603`、`.venv/lib/python3.12/site-packages/langchain/agents/factory.py:658-673` | D-test-3 需证明 gateway 编排、usage、thinking blocks 不因 engine 迁移丢失。 |

~~## 1. predict~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#2-数据流--机制)

~~### 当前现状~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/baseline.md#后端功能)

1. `predict_skill`(用途：Predict 模式执行 skill，使用 mock/golden/heuristic 输出)编译 skill 后准备 `SDKPredictContext`、`PredictTracingCallback`，再调用 `assemble_graph(..., predict_context=predict_context)`，见 `packages/graph-agent/src/graph_agent/core/runner.py:163-283`。

2. `predict_skill` 在缺省 model_resolver 时构造 mock gateway registry，再用 `ModelResolver`，见 `packages/graph-agent/src/graph_agent/core/runner.py:201-242`。

3. `_resolve_phase_chat_model` 会检查 resolver.resolve 签名是否支持 `predict_context`，支持时把它传入，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:592-603`。

4. `PredictGatewayChatModel`(用途：Predict 模式下短路 provider 调用的 GatewayChatModel 子类)覆写 `_generate`，返回 mock payload，不调真实 provider，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:29-71`。

5. `PredictGatewayChatModel.bind_tools` 会返回新的 PredictGatewayChatModel，确保绑定工具后仍保持 predict interception，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:107-140`。

6. `PredictTracingCallback`(用途：Predict trace writer)把 root metadata 标成 `is_predict`，并把 LLM usage 置零，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76-164`。

~~### 与 MVP1 设计是否冲突~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#2-数据流--机制)

有交互但不冲突。create_agent 迁移后，model 仍由 `_resolve_phase_chat_model` 提供；只要 `create_agent(model=PredictGatewayChatModel, tools=...)` 后 `bind_tools` 保持 predict subclass，mock 输出仍可工作。

<!-- ⚠️ 未迁入（仅摘要迁入，缺 predict_context 透传测试与 structured-output mock payload 约束；usage 归零只在正式 models 测试点中部分承载） → 应归入:02-mechanism/06-seam/01-models + 05-run-inner/06-golden-eval -->
### 必须保留的约束

1. create_agent 迁移测试要覆盖 predict path，证明 `predict_context` 仍传到 resolver。
2. TracingMiddleware 不得把 Predict usage 从 0 改成真实 token，`PredictTracingCallback.on_llm_call` 当前强制归零，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:146-164`。
3. 如果 structured-output 实验开启，PredictGatewayChatModel 的 mock payload 也必须能模拟 finish_task/tool-call 形态，否则 predict 不能验证 exit gate。

~~## 2. subagent lifecycle / SkillResolverProtocol DI~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#3-接口契约)

~~### 当前现状~~ → ✅[已迁入](../../02-mechanism/02-resolver/mvp1-alignment.md#2-数据流--机制)

1. `SkillResolverProtocol`(用途：把稳定 skill id 解析到本地 skill root)只要求实现 `resolve_skill(skill_id)`，见 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:33-37`。

2. `require_skill_resolver` 在缺少 resolver 时抛 `[F-v3-resolver-missing]`，见 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:80-93`。

3. loader 校验 SUBGRAPH io contract 时通过 resolver 解析 child skill，并递归 compile，见 `packages/graph-agent/src/graph_agent/core/loader.py:528-545`。

4. loader 编译 AgentNode subagents 时同样要求 resolver，解析 `target_skill` 后递归 compile，见 `packages/graph-agent/src/graph_agent/core/loader.py:595-615`。

5. `assemble_graph` 入口要求 `skill_resolver`，并先 `require_skill_resolver`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:95-104`。

6. subagent runtime map 也显式接收 `skill_resolver` 并传给 child `assemble_graph`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1120-1155`。

~~### 与 MVP1 设计是否冲突~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#3-接口契约)

不冲突，但有 DI 边界要求。SubagentDispatchMiddleware 不能自己从全局找 resolver，也不能在 tool call 时重新解析 skill id；它应消费 `_build_skill_node` 已经准备好的 runtime map。

~~### 必须保留的约束~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#3-接口契约)

1. middleware constructor 只接已编译 runtime map，不绕过 `SkillResolverProtocol`。
2. 子图 lifecycle 继续使用 `_child_flow` 增加 `subagent_depth`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1183-1189`。
3. `subagent_validation_retries` 和 `subagent_depth` 继续在 `FrameworkState` 中，见 `packages/graph-agent/src/graph_agent/core/state.py:183-194`。

<!-- ⚠️ 未迁入（正式 checkpoint/messages 已反转收口为内层也挂共享 base，但源块里的 middleware 可持久化边界与对象不得入 checkpoint 约束未成段承载） → 应归入:02-mechanism/04-run-outer/03-checkpoint + 05-run-inner/08-messages-state -->
## 3. checkpointer × middleware

~~### 当前现状~~ → ✅[已迁入](../../02-mechanism/04-run-outer/03-checkpoint/baseline.md#后端功能)

1. `checkpointer_context`(用途：按 backend 创建 LangGraph checkpointer)支持 memory/sqlite/postgres，见 `packages/graph-agent/src/graph_agent/core/checkpointer.py:38-82`。

2. `resolve_checkpointer`(用途：从参数或环境变量解析 checkpointer)读取 `STUDIO_CHECKPOINTER` 或 `GRAPH_AGENT_CHECKPOINTER_DB`，见 `packages/graph-agent/src/graph_agent/core/checkpointer.py:123-160`。

3. `_run_v030_skill_dict` 调 `resolve_checkpointer("auto")`，再传给 `assemble_graph`，见 `packages/graph-agent/src/graph_agent/core/runner.py:637-674`。

4. `assemble_graph` 最外层 `StateGraph` 当前用 `builder.compile(checkpointer=checkpointer)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:150-151`。

5. `PhaseExecutor.__getstate__` 明确禁止被 pickle，并警告 checkpointer 不应持久化带 `_phase_executor` 的 config，见 `packages/graph-agent/src/graph_agent/core/phase_executor.py:82-100`。这条主要约束旧 GraphBuilder/PhaseExecutor 路线，但说明 checkpointer 与 runtime 对象混存是高风险点。

6. `GraphBuilder.build` 也支持 `graph.compile(checkpointer=self._checkpointer)`，见 `packages/graph-agent/src/graph_agent/core/graph_builder.py:69-99`。

<!-- ⚠️ 未迁入（该块被新 state-checkpoint 决策反转，但正式文档未保留“create_agent 内层 checkpointer 与 middleware state 序列化需实测”的风险说明） → 应归入:02-mechanism/04-run-outer/03-checkpoint -->
### 与 MVP1 设计是否冲突

有潜在冲突。create_agent 自己也能接 `checkpointer`，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:658-673`。如果外层 skill graph 和内层 phase agent 共用同一个 checkpointer，thread_id、state schema、middleware state、ToolMessage 序列化都需要实测。

<!-- ⚠️ 未迁入（仅摘要迁入，缺 middleware 内 callback/runtime/compiled graph 不得进入可持久化 state 的硬约束） → 应归入:02-mechanism/04-run-outer/03-checkpoint + 05-run-inner/08-messages-state -->
### 必须保留的约束

1. 外层 skill graph 的 checkpointer 继续存在，不能因内层 create_agent 迁移丢失 resume 能力。
2. 内层 create_agent 的 checkpointer 是否启用必须用 D-test 实测；默认可以先不传，避免 nested graph state 污染外层 checkpoint。
3. 如果传入内层 checkpointer，thread_id 必须带 phase suffix，类似旧 `LLMPhaseNode._agent_config` 使用 `{outer_tid}:{phase.name}`，见 `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:616-629`。
4. middleware 内保存的 callback、runtime、compiled graph 等对象不得进入可持久化 state；只写可序列化标记和 messages。

~~## 4. create_agent × GatewayChatModel(D-test-3)~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#6-测试关键点)

~~### 当前现状~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/baseline.md#后端功能)

1. engine 当前通过 `_resolve_phase_chat_model` 从 `model_resolver.resolve(...)` 获取 phase model，并把 `predict_context` 透传给支持该参数的 resolver，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:581-603`。

2. MVP1 目标是 `create_agent(model=GatewayChatModel, tools=..., middleware=...)`，本地 `create_agent` 的 `model` 参数支持传入 `BaseChatModel` 实例，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:658-673`。

~~### 与 MVP1 设计是否冲突~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#3-接口契约)

不冲突，但需要实证。gateway A' 要继续吸收 provider 差异；engine 不应绕过 `GatewayChatModel` 直接按 provider 分支处理 usage、thinking blocks 或 tool-call metadata。

~~### 必须保留的约束~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#6-测试关键点)

1. D-test-3 必须走 engine 的 `_resolve_phase_chat_model` 入口，而不是裸 SDK 或裸 provider client。
2. 测试要断言 usage metadata 没丢，因为现有 hand-written loop 会提取 usage 并发 `LLMCallEvent`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:515-524`。
3. 测试要覆盖 thinking blocks / provider 扩展 metadata 的保留策略；该职责属于 gateway A'，engine 只验证迁移到 `create_agent` 后没有丢失。

~~## 总结~~ → ✅[已迁入](../../00-architecture-overview.md#6-跨切纪律防-drift)

- predict：需要纳入 create_agent 迁移测试；不阻塞设计。
- subagent lifecycle：与 middleware 迁移兼容，但 DI 必须保持显式。
- checkpointer × middleware：需要 D-test；是实现阶段风险最高的未覆盖项。
- create_agent × GatewayChatModel：需要 D-test-3；它对应决策记录 §13 的第三个实证项，也承接 §14 的 gateway A' 对齐约束。
