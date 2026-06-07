---
ws_id: WS-E1-step1-create-agent-core-start
modules:
  - 02-mechanism/05-run-inner/01-agent-loop
  - 02-mechanism/03-assemble
  - 02-mechanism/05-run-inner/02-middleware
  - 02-mechanism/05-run-inner/03-cognitive
  - 02-mechanism/04-run-outer/03-checkpoint
  - 02-mechanism/05-run-inner/08-messages-state
  - 02-mechanism/06-seam/01-models
depends_on: []
blocks:
  - WS-E1-step2-subagent-rewire
  - WS-E2
  - WS-E5
  - WS-E8
owns_files:
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/src/graph_agent/middleware/factory.py
  - packages/graph-agent/src/graph_agent/middleware/__init__.py
  - packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py
  - packages/graph-agent/src/graph_agent/cognitive/finish_task.py
  - packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py
  - packages/graph-agent/tests/middleware/test_cognitive_flow.py
  - packages/graph-agent/tests/cognitive/test_v21_finish_task.py
  - packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py
spec_ssot:
  - docs/engine/mvp1/02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md §2/§3/§5/§6
  - docs/engine/mvp1/02-mechanism/03-assemble/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/06-seam/01-models/mvp1-alignment.md
status: drafted
created: 2026-06-06
owner: Graph-Agent Engine MVP1
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
review_flow: PM 写需求书 -> Codex 写 RED 测试 -> PM 契约门 -> Codex 写 task.md + Gemini prompt -> Gemini 实现 GREEN -> Codex 审 -> Codex 回写 baseline -> PM 终审
---

# WS-E1 步骤 1 create_agent 核心起步 - 需求书

> 本需求书只覆盖 `IMPL_PLAN.md` 中 WS-E1 的步骤 1：把 AGENT phase 的手写 ReAct loop 起步迁到 LangChain `create_agent`，并同时接好这一步必须成立的运行边界。下一步是 Codex 按 §6 写失败测试；未见 RED、未过 PM 契约门，不得开始实现或写 Gemini 实施任务书。

## 1. 目标(intent + why)

把 engine live `assemble_graph` 的 AGENT phase 从 `graph_assembler.py` 内手写的 model/tool 循环，切到一次 `create_agent` 构造 + 一次 invoke 的内层 agent 图。这个步骤是 WS-E1 后续 subagent 重接、LOGIC runtime、iterate、以及 WS-E2/E5/E8 的前置基座；如果只把调用换成 `create_agent`，但没有接住 `WorkflowState`、6 槽 middleware、finish_task schema、phase 迭代上限和内层 checkpoint config，就会出现测试能绿但真实 state/finish/HITL 断掉的假迁移。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标唯一真理：frontmatter `spec_ssot` 所列 alignment；本文件只写步骤 1 的测试契约和文件锁，不复制设计正文。
- 实施计划：`docs/engine/mvp1/_impl/IMPL_PLAN.md` §四步骤 1、§六 Wave 1。
- 整体 WS 旧草稿参考：`docs/engine/mvp1/_impl/WS-E1-create-agent-core.md` §5-§8 中与 create_agent 构造、运行边界、finish_task schema、6 槽、checkpointer、usage 相关的核源记录；该文件覆盖整条 WS-E1，本需求书只截取步骤 1。
- 现状锚点：
  - `docs/engine/mvp1/02-mechanism/05-run-inner/01-agent-loop/baseline.md`
  - `docs/engine/mvp1/02-mechanism/03-assemble/baseline.md`
  - `docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/baseline.md`
  - `docs/engine/mvp1/02-mechanism/05-run-inner/03-cognitive/baseline.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md`
  - `docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/baseline.md`
- 本地 LangChain 源码核对点：`.venv/lib/python3.12/site-packages/langchain/agents/factory.py` 的 `create_agent` 签名、`state_schema` 合并逻辑、默认 `recursion_limit`、`graph.compile(checkpointer=...)`。
- 实现前必读源码并回述关键现状：
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:88` `assemble_graph`，`:151` 外层 `builder.compile(checkpointer=...)`，`:158` `_build_phase_node`，`:193` SUBGRAPH 现传 checkpointer，`:201` AGENT 现不传 checkpointer，`:437-576` `_build_skill_node` 和手写 loop，`:510` phase `max_iterations`，`:514` `LLMCallEvent`，`:750` token usage 提取。
  - `packages/graph-agent/src/graph_agent/core/state.py:203` `WorkflowState`，尤其 `data`、`flow`、`messages` 的 DeltaChannel reducer。
  - `packages/graph-agent/src/graph_agent/middleware/factory.py:29` `build_middleware_chain` 6 槽，`:68` 单槽 `build_middleware_chain_cognitive_flow`。
  - `packages/graph-agent/src/graph_agent/middleware/__init__.py:58` 6 槽顺序契约。
  - `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:21` `FinishTaskInput`，`:30` `build_finish_task_tool`。
  - `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:348` `wrap_tool_call`，`:469` `_handle_finish_task`，`:501` `business_data_md` 校验。
  - `packages/graph-agent/src/graph_agent/core/runner.py:663` 外层 checkpointer resolution，`:689` 外层 invoke 只传 `thread_id`。

## 3. 文件归属(并发锁,IR1)

本 WS 步骤 1 owns 见 frontmatter `owns_files`。允许新建 `test_ws_e1_create_agent_step1.py` 两个测试文件；已有 `test_cognitive_flow.py` 与 `test_v21_finish_task.py` 只允许做 finish_task schema 对齐相关断言更新。

禁止触碰：

- `packages/graph-agent/src/graph_agent/core/loader.py`、`core/manifest.py`：WS-E1 后续 iterate / 子图 io 步骤 owns；本步骤不做。
- `packages/graph-agent/src/graph_agent/core/purity.py`：WS-E6 owns。
- `packages/graph-agent/src/graph_agent/core/checkpointer.py`、`core/state.py`：WS-E5 / data-contracts owns；本步骤只消费现有 `WorkflowState` 和 checkpointer，不改 state/checkpointer 实现。
- `packages/graph-agent/src/graph_agent/callbacks/events.py`、`callbacks/emit.py`、`middleware/tracing.py`、`middleware/tool_error.py`、`middleware/loop_detection.py`：WS-E2 / WS-E4 owns；本步骤只把 6 槽链接进 create_agent，不实现后三槽逻辑。
- `packages/graph-agent/src/graph_agent/core/predict*`、`core/_predict_internal/**`、`packages/graph-agent-gateway/**`：gateway/predict 接缝只做不回归测试，不在本步骤改。
- subagent 派发重接相关实现区：`graph_assembler.py` 里的 `_invoke_subagent_tool_t21` / `_subagent_runtime_map` 可以只读核对，但重接线属于 WS-E1 步骤 2，不在本步骤实现。

共享文件协调：`graph_assembler.py` 是 WS-E1 串行热点文件。本步骤完成并验收后，才能继续同文件的 subagent、LOGIC、iterate、子图 io 放宽后续步骤。并发 WS 不得在本步骤进行时修改该文件。

## 4. 现状锚点(baseline)

当前 `assemble_graph` 外层图是 `StateGraph(WorkflowState)`，但 AGENT 分支 `_build_skill_node` 产出的内层执行仍是手写 `for max_turns` loop：手动 bind tools、手动 `model.invoke`、手动追加 `ToolMessage`，只接单槽 CognitiveFlow，并通过 `handle_finish_task_tool_result` 处理工具执行结果。6 槽工厂已经存在但 live 不用；finish_task 工具暴露单字段 markdown，而 create_agent 路径下 CognitiveFlow 会直接读取 raw tool-call args；AGENT 分支目前也没有接收外层传入的 checkpointer。

## 5. 目标行为(可测的契约)

### 5.1 AGENT phase 由 create_agent 承载

- live `assemble_graph` 的 AGENT phase 必须走 LangChain `create_agent`，由它处理 model/tool 循环；不再由 `graph_assembler.py` 手拼 tool-call 消息配对或自行决定 finish_task。
- `create_agent` 的 model 必须是 `_resolve_phase_chat_model` 得到的 gateway/predict-aware chat model；engine 不能按 provider 分支。
- tools 必须把业务工具、framework 工具、resource 工具和 finish_task 工具交给 `create_agent`。subagent 工具可先保持后续步骤处理，但本步骤不得引入会隐藏步骤 2 断裂的假成功。
- system prompt 必须等价使用现有 `_agent_system_prompt(...)` 结果，包含 reference-reader markdown 和 cognitive template 渲染内容。

### 5.2 WorkflowState 保真

- `create_agent` 必须以 engine 的 `WorkflowState` 作为 agent state schema 或等价保证，使 `data`、`flow`、`messages` 三个顶层 key 在内层 agent 图中都可见、可更新、可返回。
- 不能退回 LangChain 默认 `AgentState` 只保 messages 的形态；`WorkflowState.data` 业务黑板、`WorkflowState.flow` 框架态和 `messages` DeltaChannel 语义都必须在 create_agent 跑完后保留。

### 5.3 6 槽 middleware 接入，但后三槽逻辑不在本步骤实现

- AGENT phase 必须消费 `build_middleware_chain(...)` 的 6 槽顺序，而不是单槽 `build_middleware_chain_cognitive_flow(...)`。
- ProtocolValidation、CognitiveFlow、ExecutionControl 的既有逻辑要在 create_agent 路径保持可运行；Tracing、ToolError、LoopDetection 在本步骤只要求作为链路槽位接入，不要求从 no-op 变成完整逻辑。
- 6 槽构造必须拿到当前 phase 所需的 schema / io / validator / callbacks 上下文；不能因迁移 create_agent 而绕过 finish_task validation 或 iteration/dead-end 事件。

### 5.4 finish_task schema 与 CognitiveFlow raw args 对齐

- 绑定给 create_agent 的 finish_task 工具 schema，必须与 `CognitiveFlowMiddleware.wrap_tool_call` / `_handle_finish_task` 实际读取的 raw tool-call args 一致。
- 当前 live drift 是：`cognitive/finish_task.py` 暴露 `markdown` 单字段，而 `CognitiveFlowMiddleware` 读取 `business_data_md`，并可记录 `reasoning`、`diagnostics_md`。本步骤必须把这个 drift 收敛到一个单一契约，且测试必须证明模型按该 schema 发 tool call 后，CognitiveFlow 能接受 finish、结构化结果进入 `flow.finish_task_result`，必要的 business data hoist 仍发生。
- 收敛后的 schema 必须携带“最终业务 markdown”语义；字段名和附加诊断字段以 `03-cognitive` 与现有 CognitiveFlow raw args 契约为准，不能让 create_agent 绑定的工具 schema与 middleware 期望继续分裂。

### 5.5 phase max_iterations 仍生效

- 现有 `phase_ast.max_iterations` 是每个 AGENT phase 的迭代上限。迁移 create_agent 后，该上限必须仍能限制内层 agent 的 model/tool 循环。
- 不能被 LangChain `create_agent` 默认 `recursion_limit=10000` 吞掉，造成阶段实际近似无界。

### 5.6 内层 checkpointer 只做接线可运行，不做 E5 优化

- 如果外层 `assemble_graph(..., checkpointer=...)` 收到 checkpointer，AGENT create_agent 内层也必须能使用同一共享 base，并在 invoke config 中带可区分外层 thread 的内层 namespace。
- 本步骤验收只要求小 N agent loop 真能运行、checkpoint 写入不污染外层 `WorkflowState`、`thread_id` / `checkpoint_ns` 可寻址；blackboard delta、messages compaction、resume API 和 durability 调优属于 WS-E5 / 后续 WS，不在本步骤实现。

### 5.7 LLM usage 和 predict/gateway 接缝不回归

- 迁移后不能静默丢掉 token usage、tool-call metadata、thinking blocks。若本步骤不把 usage 重新桥接回现有 `LLMCallEvent`，必须至少保证 usage / thinking / tool-call metadata 仍在 message metadata 或 gateway/predict tracing 可见，并把事件流补齐明确 defer 到 WS-E4。
- predict 路径必须保持 `_resolve_phase_chat_model(... predict_context=...)` 能返回 predict-aware model，`bind_tools()` 仍由 predict mock 拦截，不真调 provider，usage 仍归零。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，且 PM 契约门通过后才能写实施任务书。标 ★ 的必须覆盖真实或接近真实的端到端路径，不能只靠静态 grep 绿。

- ★ create_agent 构造路径：assemble 一个最小 AGENT skill，断言 live AGENT phase 调用 `create_agent`，传入 gateway/predict-aware model、tools、system_prompt、6 槽 middleware、WorkflowState schema、checkpointer；手写 model/tool loop 不再是决策主体。
- ★ WorkflowState 保真：构造带 `data`、`flow`、`messages` 的 state 跑 AGENT，断言 create_agent 内层能读到并返回这些字段；另有反例证明默认 `AgentState` 会丢 `data/flow`，防止假绿。
- 6 槽接线：断言 live AGENT phase 使用 `build_middleware_chain` 的 6 槽顺序，且不再只调 `build_middleware_chain_cognitive_flow`；前 3 槽在最小运行中被真实调用，后 3 槽只要求处于 chain 中。
- finish_task schema 一致：绑定工具 schema 与 CognitiveFlow raw args 契约一致；模型发出目标 schema 的 finish_task tool call 后，CognitiveFlow 接受并写入 `flow.finish_task_result`，schema 不一致时测试失败。
- finish_task drift 回归：覆盖现有 `cognitive/finish_task.py` 与 `middleware/cognitive_flow.py` 的一致性，防止一个文件改了、另一个仍按旧字段读取。
- max_iterations 保活：用一个始终要求继续 tool loop 的 fake model，证明 phase 上限生效并停止；不能依赖 `recursion_limit=10000`。
- ★ checkpointer 可运行：用内存或 sqlite checkpointer 跑一个小 N AGENT create_agent loop，config 带外层 `thread_id` 和内层 namespace，断言 checkpoint 写入可寻址且外层 state 不被内层 graph runtime 对象污染。
- usage / metadata 不丢：gateway-like fake message 带 usage、tool-call metadata、thinking block；迁移后至少在事件流或 message metadata 中可见。若 defer 到 WS-E4，测试必须断言 message metadata 保留并登记 defer。
- predict 回归：predict_context 透传到 model resolver；`PredictGatewayChatModel.bind_tools()` 仍返回 predict-aware bound model，不发生 provider 调用，usage 保持归零。
- ★ 真实 e2e：一条真实 v0.3/v2.1 skill 经 create_agent 跑通工具循环并 finish_task，最终结构化输出落 state；不是只 monkeypatch `create_agent` 参数。
- 旧测试改写清单：如果因 finish_task schema 收敛需要更新既有 markdown 单字段断言，Codex 必须逐条列出改了哪些测试、原断言是什么、新断言是什么；不得用删除测试掩盖迁移。

## 7. 硬依赖约束

1. 先让 RED 测试证明当前 live 路径仍是手写 loop、单槽 middleware、finish_task schema drift、AGENT 无内层 checkpointer；这些测试过 PM 契约门后，才能进入实现。
2. 6 槽接线与 create_agent 构造必须在同一垂直切片验收；create_agent 构造本身要消费 middleware，拆开会留下不可运行中间态。
3. finish_task schema 对齐必须先于真实 e2e 验收；否则 create_agent 可以跑起来但最终交付不会被 CognitiveFlow 正确接受。
4. 内层 checkpointer 接线只做运行边界验证；发现 delta/compaction/resume 缺口时登记到 deferred 或 WS-E5，不在本步骤扩散。

## 8. 验收标准(硬退出,IR4)

- [ ] §6 RED 测试先失败，PM 契约门通过后实现到 GREEN。
- [ ] live AGENT phase 走 `create_agent`；`graph_assembler.py` 不再用手写 `for max_turns` model/tool loop 作为 AGENT 主执行路径。
- [ ] `WorkflowState.data`、`WorkflowState.flow`、`WorkflowState.messages` 在 create_agent 内层运行后保真，不退化为默认 `AgentState`。
- [ ] AGENT phase 传入 6 槽 middleware；前 3 槽可运行，后 3 槽作为 no-op 槽位接入且不在本步骤扩展逻辑。
- [ ] finish_task 工具 schema 与 CognitiveFlow raw args 完全一致；finish_task 成功时结构化结果进入 `flow.finish_task_result`，必要 business data hoist 仍成立。
- [ ] `phase_ast.max_iterations` 生效，未被 create_agent 默认 recursion limit 吞掉。
- [ ] create_agent 内层 checkpointer 接线小 N 真跑，`thread_id` / `checkpoint_ns` 可寻址，不污染外层 state；delta/compaction/resume 未越界实现。
- [ ] usage / thinking / tool-call metadata 不静默丢失；若事件桥接 defer 到 WS-E4，有测试和 deferred 记录。
- [ ] predict/gateway 接缝不回归：predict mock 不真调 provider，usage 归零；普通 gateway-like 模型 metadata 保留。
- [ ] 至少一条真实 e2e 跑通 create_agent 工具循环 + finish_task。
- [ ] 验证命令至少包括相关 `packages/graph-agent/tests/core`、`tests/middleware`、`tests/cognitive`、`tests/e2e` 的 pytest，以及 `uv run mypy` 覆盖改动文件。

## 9. 不做(范围锁定,IR7)

- 不做 WS-E1 步骤 2 的 subagent 工具重接；若 create_agent 裸调 subagent placeholder 的风险暴露，记录为步骤 2 必测项，不在本步骤偷偷修。
- 不做 LOGIC 纯返回 / Context mutation / purity run_skill 禁令；分别归 WS-E1 后续 LOGIC 子步和 WS-E6。
- 不做 iterate / 图级 loop / manifest `BatchSpec` 迁移；归 WS-E1 后续 iterate 子步。
- 不做 11-io 子图 io 放宽、文件 lazy 注入、artifact business_data_md；归 WS-E1 后续子步和 WS-E1-io。
- 不实现 Tracing / ToolError / LoopDetection 后三槽真实逻辑；归 WS-E2 / WS-E4。
- 不改 gateway 内部；本步骤只消费 `GatewayChatModel` / predict-aware model 接口。
- 不回写 baseline 到目标态；只有真实代码落地且 Codex 审查通过后，才按 §10 回写。
- 范围外问题登记到 `docs/deferred-items.md` 或对应 WS，不顺手扩散。

## 10. baseline 回写指令(IR6)

实现落地后，Codex 按真实代码回写：

- `docs/engine/mvp1/02-mechanism/05-run-inner/01-agent-loop/baseline.md`：AGENT inner loop 是否已由 create_agent 承载、WorkflowState schema、max_iterations、usage 处理现状。
- `docs/engine/mvp1/02-mechanism/03-assemble/baseline.md`：`_build_skill_node` 的 create_agent 构造收口和 AGENT checkpointer 传递现状。
- `docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/baseline.md`：live 是否已接 6 槽，后三槽是否仍 no-op。
- `docs/engine/mvp1/02-mechanism/05-run-inner/03-cognitive/baseline.md`：finish_task schema 与 CognitiveFlow raw args 的真实一致形态。
- `docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md` 与 `05-run-inner/08-messages-state/baseline.md`：只记录本步骤实际落地的内层 checkpointer 接线，不把 E5 的 delta/compaction/resume 目标提前写成现状。

## 11. 评审检查点

- 契约门(PM 审测试)：重点查 RED 是否忠实编码 create_agent 构造、WorkflowState 保真、6 槽接线、finish_task schema 一致、max_iterations、checkpointer 小 N、usage/predict 回归；不得只用静态 grep 替代真实运行。
- Codex 审查退出：必须逐条满足 §8；尤其核对没有越界改 subagent/LOGIC/iterate/11-io/E2/E5 文件。
- PM 终审：看实现是否忠实承接 `spec_ssot`，baseline 是否照真实代码回写，测试是否存在 mock 到绿、旧 finish_task 断言残留或自动审批绕过人工确认。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准的 RED 测试写 `.kiro/specs/graph-agent-engine-mvp1/tasks-ws-e1-step1-create-agent-core-start.md`，遵守：

- 来源 = 已批准测试；每个任务项都必须能追到 §6 的某条测试契约。
- 格式 = Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: WS-E1-step1.<契约项>` + 验证命令。
- frontmatter 指回本需求书、`task-spec-standard.md`、`IMPL_PLAN.md` 和相关 alignment；不重写设计。
- 嵌入编排注解：owns_files、实现者 = Gemini、§8 硬退出条件、用户明确确认闸门。
- 行号由 Codex 落地时重新核；不得照抄本需求书里的行号作为编辑坐标。
- 不跑 `/kiro:spec-tasks` 自动生成，避免 clobber。
- 产出 Gemini prompt 时必须包含工作区路径、必读文件、已批准 RED 测试结果、owns_files / 禁止触碰、目标行为、验证命令和回报格式。
