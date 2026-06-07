---
ws_id: WS-E1-step1-create-agent-core-start
kind: implementation_tasks
status: ready-for-gemini
created: 2026-06-06
implementer: Gemini
source_requirement: .kiro/specs/graph-agent-engine-mvp1/requirements-ws-e1-step1-create-agent-core-start.md
task_standard: docs/development/task-spec-standard.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
spec_ssot:
  - docs/engine/mvp1/02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md §2/§3/§5/§6
  - docs/engine/mvp1/02-mechanism/03-assemble/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/mvp1-alignment.md §2/§3/§6
  - docs/engine/mvp1/02-mechanism/06-seam/01-models/mvp1-alignment.md
approved_red_tests:
  - packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py
  - packages/graph-agent/tests/cognitive/test_v21_finish_task.py
  - packages/graph-agent/tests/cognitive/test_v21_finish_task.py::test_finish_task_tool_schema_matches_cognitive_flow_raw_args_contract
  - packages/graph-agent/tests/middleware/test_cognitive_flow.py
  - packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py
approved_red_results:
  - command: uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py -q
    result: 2 failed, 3 passed
    failure_signal: live AGENT path has not called create_agent; predict path has not entered create_agent
  - command: uv run pytest packages/graph-agent/tests/cognitive/test_v21_finish_task.py packages/graph-agent/tests/middleware/test_cognitive_flow.py -q
    result: 2 failed
    failure_signal: FinishTaskInput still exposes markdown-only schema
  - command: uv run pytest packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py -q
    result: 1 failed
    failure_signal: hand-written loop plus old finish_task schema rejects target raw args
  - command: git diff --check
    result: passed
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
legacy_finish_task_fixture_allowlist:
  - packages/graph-agent/tests/e2e/test_execution_runtime_v030.py
  - packages/graph-agent/tests/e2e/test_pr2_v030_observability_trace_red.py
  - packages/graph-agent/tests/runner/test_event_subscriber_cutover.py
  - packages/graph-agent/tests/core/test_v030_agent_compilation.py
  - packages/graph-agent/tests/core/test_reference_reader_assembly_fallback.py
  - packages/graph-agent/tests/tools/test_builtin_resource_tools.py
  - packages/graph-agent/tests/core/test_gamma2_reference_reader_sandbox.py
  - packages/graph-agent/tests/callbacks/test_pr_e_tracing_emission_red.py
forbidden_files:
  - packages/graph-agent/src/graph_agent/core/loader.py
  - packages/graph-agent/src/graph_agent/core/manifest.py
  - packages/graph-agent/src/graph_agent/core/purity.py
  - packages/graph-agent/src/graph_agent/core/checkpointer.py
  - packages/graph-agent/src/graph_agent/core/state.py
  - packages/graph-agent/src/graph_agent/callbacks/events.py
  - packages/graph-agent/src/graph_agent/callbacks/emit.py
  - packages/graph-agent/src/graph_agent/middleware/tracing.py
  - packages/graph-agent/src/graph_agent/middleware/tool_error.py
  - packages/graph-agent/src/graph_agent/middleware/loop_detection.py
  - packages/graph-agent/src/graph_agent/core/predict.py
  - packages/graph-agent/src/graph_agent/core/_predict_internal/
  - packages/graph-agent-gateway/
known_unrelated_modified_files:
  - packages/graph-agent/src/graph_agent/core/exceptions.py
  - packages/graph-agent/src/graph_agent/core/result.py
hard_exit: requirements §8 all checks green; no baseline rewrite before Codex implementation review
confirmation_gate: production code changes require explicit user-confirmed implementation turn
---

# WS-E1 Step 1 create_agent 核心起步 - 实施任务书

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development before production edits, then use superpowers:executing-plans or superpowers:subagent-driven-development to implement phase by phase.

**Goal:** 把 live AGENT phase 从 `graph_assembler.py` 的手写 model/tool loop 迁到 LangChain `create_agent`，同时保住 `WorkflowState`、6 槽 middleware、finish_task raw args、phase 上限、内层 checkpoint、metadata 和 predict 接缝。

**Architecture:** 外层仍由 `assemble_graph` 构建 `StateGraph(WorkflowState)`；AGENT phase 内部改为构造一次 LangChain agent graph，并由 `create_agent(...).invoke(...)` 执行 model/tool 循环。middleware、finish_task schema、checkpoint config 和 message metadata 都必须从 engine state 进入 create_agent 路径并返回 engine-visible state。

**Tech Stack:** Python 3.12, LangGraph, LangChain `create_agent`, Pydantic v2, pytest, uv.

---

## Phase 0 - 进入实现前的硬闸

- [ ] 重新阅读需求书、任务规范、alignment 指针和 approved RED 测试，回述当前 live 缺口；不要把本文件里的历史行号当编辑坐标。
  _Requirements: WS-E1-step1.grounding_
  Verify: `sed -n '1,260p' .kiro/specs/graph-agent-engine-mvp1/requirements-ws-e1-step1-create-agent-core-start.md`

- [ ] 复跑 approved RED，确认失败信号仍是契约门批准的真实缺口；如果失败点变成导入错误、fixture 错误或无关文件污染，先报告并停在测试修复层。
  _Requirements: WS-E1-step1.red-contract_
  Verify:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py -q`
  `uv run pytest packages/graph-agent/tests/cognitive/test_v21_finish_task.py packages/graph-agent/tests/middleware/test_cognitive_flow.py -q`
  `uv run pytest packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py -q`

- [ ] 保护当前工作区里与本任务无关的 modified 文件：`packages/graph-agent/src/graph_agent/core/exceptions.py` 和 `packages/graph-agent/src/graph_agent/core/result.py` 不属于本任务，不回退、不纳入实现说明。
  _Requirements: WS-E1-step1.scope-lock_
  Verify: `git status --short -- packages/graph-agent/src/graph_agent packages/graph-agent/tests`

## Phase 1 - finish_task schema 先收敛

- [ ] 在 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py` 中把 public tool schema 收敛到 CognitiveFlow raw args 契约：`business_data_md` 承载最终业务 markdown，`reasoning` 和 `diagnostics_md` 作为诊断字段；`markdown` 字段不得继续出现在 `FinishTaskInput` 或 `build_finish_task_tool(...).args_schema`。
  _Requirements: WS-E1-step1.finish-task-schema_
  Verify: `uv run pytest packages/graph-agent/tests/cognitive/test_v21_finish_task.py -q`

- [ ] 保持 `build_finish_task_tool` 的语义：直接调用工具时仍把 `business_data_md` 送入现有 markdown 解析/修复链路，返回值能被既有 CognitiveFlow/IO 处理消费；不要把 schema 改成只为测试存在的空壳。
  _Requirements: WS-E1-step1.finish-task-schema_
  Verify: `uv run pytest packages/graph-agent/tests/middleware/test_cognitive_flow.py::TestFinishTask -q`

- [ ] 如 schema 收敛导致旧 fake model/tool fixture 仍发旧 `markdown` args，只在 frontmatter `legacy_finish_task_fixture_allowlist` 里逐项改为新 raw args：`reasoning` 使用 `"done"`，`diagnostics_md` 使用 `"schema aligned"`，`business_data_md` 逐字承接原 `markdown` 字段值；不得删除测试，也不得改变测试原本要验证的事件、trace、输出语义。`test_pr_e_tracing_emission_red.py` 里的 callback 返回若不绑定 create_agent tool schema，只能在确认失败相关后改。
  _Requirements: WS-E1-step1.legacy-test-rewrite-list_
  Verify: `rg -n '"args": \\{"markdown"|FinishTaskInput|business_data_md' packages/graph-agent/tests packages/graph-agent/src/graph_agent -g '*.py'`

## Phase 2 - live AGENT path 改为 create_agent

- [ ] 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py` 的 AGENT phase 路径中使用 LangChain `create_agent` 构造内层 agent；`graph_assembler.py` 不再以手写 `for max_turns`、手动 `bind_tools`、手动追加 `ToolMessage` 的循环作为 AGENT 主执行路径。
  _Requirements: WS-E1-step1.create-agent-construct_
  Verify: `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py::test_agent_phase_constructs_create_agent_with_workflow_state_boundaries -q`

- [ ] `create_agent` 入参必须来自现有 engine 构造件：model 使用 `_resolve_phase_chat_model(... predict_context=...)` 的返回值；tools 包含业务工具、resource 工具、framework 工具和 finish_task；system prompt 使用 `_agent_system_prompt(...)`，并保留 reference-reader markdown。
  _Requirements: WS-E1-step1.create-agent-construct_
  Verify: `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py::test_agent_phase_constructs_create_agent_with_workflow_state_boundaries -q`

- [ ] `create_agent` 必须传 `state_schema=WorkflowState`，invoke input 至少包含 `data`、`flow`、`messages`；返回后这些字段仍是 engine 可见 state，而不是退化成默认 `AgentState` 只剩 messages。
  _Requirements: WS-E1-step1.workflow-state_
  Verify: `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py::test_default_langchain_agent_state_drops_workflow_data_and_flow packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py::test_agent_phase_constructs_create_agent_with_workflow_state_boundaries -q`

- [ ] invoke config 传入外层 `thread_id`，为内层 agent 写入可区分 phase/agent 的 `checkpoint_ns`，并把 `phase_ast.max_iterations` 映射到有效的内层循环上限；`recursion_limit` 必须是有界小值，不使用 LangChain 默认近似无界值。
  _Requirements: WS-E1-step1.max-iterations, WS-E1-step1.inner-checkpointer_
  Verify: `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py::test_phase_max_iterations_stops_repeated_tool_loop -q`

## Phase 3 - 6 槽 middleware 接入 create_agent

- [ ] live AGENT phase 使用 `build_middleware_chain(...)` 的 6 槽顺序，不再只用 `build_middleware_chain_cognitive_flow(...)`。传入当前 phase 的 `io_manager`、`schema_engine`、输出 schema、phase name、callbacks、unattended/interrupt 上下文；不要在本步骤实现 Tracing、ToolError、LoopDetection 的真实逻辑。
  _Requirements: WS-E1-step1.six-slot-middleware_
  Verify: `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py::test_agent_phase_constructs_create_agent_with_workflow_state_boundaries -q`

- [ ] 保证前 3 槽在最小 create_agent loop 中真实运行：ProtocolValidation 的 before/after、CognitiveFlow 的 tool wrap、ExecutionControl 的 before/after 都被 LangChain agent 调到。
  _Requirements: WS-E1-step1.six-slot-middleware_
  Verify: `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py::test_first_three_middleware_slots_run_in_minimal_create_agent_loop -q`

- [ ] finish_task 由 CognitiveFlow raw args 路径接受并写入 `flow.finish_task_result`；成功 finish 时走 `END`，schema drift 时不能被 graph_assembler 的旧手写 finish 逻辑吞掉。
  _Requirements: WS-E1-step1.finish-task-schema_
  Verify: `uv run pytest packages/graph-agent/tests/cognitive/test_v21_finish_task.py::test_finish_task_tool_schema_matches_cognitive_flow_raw_args_contract packages/graph-agent/tests/middleware/test_cognitive_flow.py::TestFinishTask::test_finish_validates_and_hoists_business_data -q`

## Phase 4 - max_iterations、checkpoint 和 metadata 行为级 GREEN

- [ ] 用 approved fake looping model 证明 `phase_ast.max_iterations` 确实限制 create_agent model/tool loop；失败时优先修 AGENT invoke config/loop termination，不把测试调宽。
  _Requirements: WS-E1-step1.max-iterations_
  Verify: `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py::test_phase_max_iterations_stops_repeated_tool_loop -q`

- [ ] 外层 `assemble_graph(..., checkpointer=...)` 收到 checkpointer 时，AGENT create_agent 内层也使用同一 base，并通过 `checkpoint_ns` 写出可寻址 checkpoint；外层 `flow` 不能混入 graph runtime 对象或 callable。
  _Requirements: WS-E1-step1.inner-checkpointer_
  Verify: `uv run pytest packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py::test_agent_create_agent_loop_finishes_with_target_schema_and_inner_checkpoint -q`

- [ ] 保留 gateway-like AIMessage 的 `usage_metadata`、`response_metadata.thinking_blocks` 和 `response_metadata.tool_call_metadata` 到 `result["messages"]` 或等价 engine-visible 输出；本步骤不要求补齐 WS-E4 事件桥接，但不能静默丢 metadata。
  _Requirements: WS-E1-step1.metadata-usage_
  Verify: `uv run pytest packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py::test_agent_create_agent_loop_finishes_with_target_schema_and_inner_checkpoint -q`

## Phase 5 - predict/gateway 接缝不回归

- [ ] `_resolve_phase_chat_model` 仍接收并传递 `predict_context`；create_agent 工具绑定时不能把 `PredictGatewayChatModel` unwrap 成普通 provider model。
  _Requirements: WS-E1-step1.predict_
  Verify: `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py::test_predict_gateway_model_stays_predict_bound_and_zero_usage -q`

- [ ] predict bound model invoke 不触发 `LLMClientManager` provider probe/dispatch，usage 保持零；如果需要适配 bind_tools 返回值，改 engine consume 方式，不改 gateway/predict 内部文件。
  _Requirements: WS-E1-step1.predict_
  Verify: `uv run pytest packages/graph-agent/tests/models/test_predict_gateway_chat_model.py -q`

## Phase 6 - 回归命令

- [ ] approved RED 全部变 GREEN。
  _Requirements: WS-E1-step1.hard-exit_
  Verify:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py -q`
  `uv run pytest packages/graph-agent/tests/cognitive/test_v21_finish_task.py packages/graph-agent/tests/middleware/test_cognitive_flow.py -q`
  `uv run pytest packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py -q`

- [ ] finish_task schema 相关旧回归不因 fake fixture 仍发旧 `markdown` 而失败；若改了 allowlist 中的旧测试，回报里逐项写“文件、原 fake args、新 fake args、原测试语义是否保持”。
  _Requirements: WS-E1-step1.legacy-test-rewrite-list_
  Verify:
  `uv run pytest packages/graph-agent/tests/e2e/test_execution_runtime_v030.py packages/graph-agent/tests/e2e/test_pr2_v030_observability_trace_red.py packages/graph-agent/tests/runner/test_event_subscriber_cutover.py packages/graph-agent/tests/core/test_v030_agent_compilation.py packages/graph-agent/tests/core/test_reference_reader_assembly_fallback.py packages/graph-agent/tests/tools/test_builtin_resource_tools.py packages/graph-agent/tests/core/test_gamma2_reference_reader_sandbox.py -q`

- [ ] 相关 core/middleware/cognitive/e2e 与类型检查通过；如果 broad e2e 因本任务无关历史失败卡住，保留失败输出并至少保证本任务文件和 allowlist 文件全绿。
  _Requirements: WS-E1-step1.hard-exit_
  Verify:
  `uv run pytest packages/graph-agent/tests/core packages/graph-agent/tests/middleware packages/graph-agent/tests/cognitive packages/graph-agent/tests/e2e -q`
  `uv run mypy packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/middleware/factory.py packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py packages/graph-agent/src/graph_agent/cognitive/finish_task.py`
  `git diff --check`

## Phase 7 - Codex 审查与 baseline 回写边界

- [ ] Gemini 实现到 GREEN 后，Codex 先按需求书 §8 做硬退出审查；未通过时打回实现，不回写 baseline。
  _Requirements: WS-E1-step1.review-gate_
  Verify: `git diff --stat`

- [ ] 只有 Codex 审查确认真实代码落地后，Codex 按真实现状回写需求书 §10 的 6 个 baseline 文件；Gemini 本轮 prompt 不负责 baseline 回写。
  _Requirements: WS-E1-step1.baseline-after-green_
  Verify: `git status --short -- docs/engine/mvp1/02-mechanism`

## Gemini Prompt

```text
你在 /Users/sevenx/Documents/coding/agent-harness 工作。请作为 graph-agent engine 实现者执行 WS-E1 step1：把 live AGENT phase 从 graph_assembler.py 的手写 loop 起步迁到 LangChain create_agent，并把 approved RED 做到 GREEN。

必须先读并简短回述：
- .kiro/specs/graph-agent-engine-mvp1/requirements-ws-e1-step1-create-agent-core-start.md
- .kiro/specs/graph-agent-engine-mvp1/tasks-ws-e1-step1-create-agent-core-start.md
- docs/development/task-spec-standard.md
- docs/engine/mvp1/_impl/IMPL_PLAN.md
- packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py
- packages/graph-agent/tests/cognitive/test_v21_finish_task.py
- packages/graph-agent/tests/middleware/test_cognitive_flow.py
- packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/src/graph_agent/middleware/factory.py
- packages/graph-agent/src/graph_agent/middleware/__init__.py
- packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py
- packages/graph-agent/src/graph_agent/cognitive/finish_task.py

approved RED 结果：
- uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py -q -> 2 failed, 3 passed；失败点是 live AGENT 未调用 create_agent，predict 未进入 create_agent 路径。
- uv run pytest packages/graph-agent/tests/cognitive/test_v21_finish_task.py packages/graph-agent/tests/middleware/test_cognitive_flow.py -q -> 2 failed；失败点是 FinishTaskInput 仍只有 markdown。
- uv run pytest packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py -q -> 1 failed；失败点是旧 hand-written loop + 旧 schema 吃不了目标 raw args。
- git diff --check -> passed。

只能改任务书 frontmatter 的 owns_files 列表所列文件；旧 finish_task fake fixture 如仍发 {"markdown": ...}，只允许在 legacy_finish_task_fixture_allowlist 中做 schema fixture 对齐，并逐项回报。禁止触碰 core/state.py、core/checkpointer.py、loader.py、manifest.py、callbacks/events.py、callbacks/emit.py、middleware/tracing.py、middleware/tool_error.py、middleware/loop_detection.py、gateway/predict 内部文件和 packages/graph-agent-gateway。当前 core/exceptions.py 与 core/result.py 已是无关 modified，保持原样，不回退、不纳入本任务。

目标行为：
1. AGENT phase 使用 LangChain create_agent 承载 model/tool loop。
2. model 来自 _resolve_phase_chat_model(... predict_context=...)；tools 包含业务/resource/framework/finish_task；system_prompt 保留 _agent_system_prompt 与 reference-reader markdown。
3. state_schema=WorkflowState，invoke input/return 保住 data、flow、messages。
4. middleware 使用 build_middleware_chain 的 6 槽；前三槽真实运行，后三槽只接线不扩展逻辑。
5. finish_task tool schema 与 CognitiveFlow raw args 一致：reasoning、diagnostics_md、business_data_md；不再暴露 markdown。
6. phase_ast.max_iterations 行为级限制 create_agent loop；recursion_limit 不使用默认近似无界值。
7. 外层 checkpointer 传给内层 create_agent，config 带 thread_id 和含 phase/agent 的 checkpoint_ns；外层 state 不被 runtime 对象污染。
8. usage/thinking/tool-call metadata 在 engine-visible result["messages"] 或等价输出中保留。
9. PredictGatewayChatModel.bind_tools 后仍是 predict-aware model，不真调 provider，usage 为零。

按任务书 Phase 0-6 执行。必须遵守 TDD：先确认 approved RED，再改生产代码；不要删除或放宽 approved tests。完成后运行并报告：
- uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py -q
- uv run pytest packages/graph-agent/tests/cognitive/test_v21_finish_task.py packages/graph-agent/tests/middleware/test_cognitive_flow.py -q
- uv run pytest packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py -q
- uv run pytest packages/graph-agent/tests/models/test_predict_gateway_chat_model.py -q
- uv run pytest packages/graph-agent/tests/e2e/test_execution_runtime_v030.py packages/graph-agent/tests/e2e/test_pr2_v030_observability_trace_red.py packages/graph-agent/tests/runner/test_event_subscriber_cutover.py packages/graph-agent/tests/core/test_v030_agent_compilation.py packages/graph-agent/tests/core/test_reference_reader_assembly_fallback.py packages/graph-agent/tests/tools/test_builtin_resource_tools.py packages/graph-agent/tests/core/test_gamma2_reference_reader_sandbox.py -q
- uv run mypy packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/middleware/factory.py packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py packages/graph-agent/src/graph_agent/cognitive/finish_task.py
- git diff --check

回报格式：
1. 读到的当前实现缺口摘要。
2. 改动文件清单，标明生产代码、测试 fixture、未触碰的 unrelated modified 文件。
3. 每条目标行为的达成状态。
4. 运行命令结果；若有失败，贴最小失败信号和是否与本任务相关。
5. 如改了 legacy fixture，逐项列出原 fake args、新 fake args、原测试语义如何保持。
```
