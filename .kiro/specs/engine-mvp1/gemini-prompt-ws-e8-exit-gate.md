---
ws_id: WS-E8-exit-gate
artifact: gemini-prompt
status: drafted
created: 2026-06-09
task_file: .kiro/specs/engine-mvp1/task-ws-e8-exit-gate.md
requirements: .kiro/specs/engine-mvp1/requirements-ws-e8-exit-gate.md
---

# Gemini Prompt - WS-E8 Exit Gate

```text
你是 /Users/sevenx/Documents/coding/agent-harness/.worktrees/engine-mvp1-ws-e8-exit-gate 工作区的 engine 模块实现者。请按 TDD 执行 WS-E8 exit gate：RED 测试已由 Codex 写好，并已通过 PM 契约门审查。你的任务是只做最小 GREEN 实现，不扩范围。

工作区：
/Users/sevenx/Documents/coding/agent-harness/.worktrees/engine-mvp1-ws-e8-exit-gate

任务书：
.kiro/specs/engine-mvp1/task-ws-e8-exit-gate.md

需求书：
.kiro/specs/engine-mvp1/requirements-ws-e8-exit-gate.md

必须先读并回述关键现状：
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
  只读。重点：AGENT create_agent 装配、build_middleware_chain 接线、max_iterations / recursion_limit、GraphRecursionError 当前 partial-state fallback。不要改 graph_assembler.py，除非 RED 证明必须改且先停下复审。
- packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py
  重点：CognitiveFlowMiddleware._handle_finish_task 的 accepted marker 写入、schema validation、ToolMessage、当前直接 goto=END 的成功出口。
- packages/graph-agent/src/graph_agent/middleware/factory.py
  重点：build_middleware_chain 和现有 6 槽顺序。
- packages/graph-agent/src/graph_agent/middleware/__init__.py
  重点：MVP0_MIDDLEWARE_ORDER_CONTRACT / public exports。
- packages/graph-agent/src/graph_agent/core/nudge_injector.py
  重点：NudgeInjector.try_standard / try_planning / counts 和既有 nudge 文案。
- packages/graph-agent/src/graph_agent/core/error_registry.py
  重点：当前可用运行期错误码；确认 exit-control 语义是否需要新增注册。
- 已批准 RED 测试：
  - packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py

RED 测试结果：
运行：
uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q
当前预期 RED：4 failed, 1 passed。

当前失败必须保持为契约失败：
1. test_agent_without_finish_task_returns_explicit_failure
   当前无 finish_task 被包装为 success=True。
2. test_no_tool_calls_gets_nudged_back_to_model_before_success
   当前无 tool_calls 没有 nudge 回模型，只调用模型 1 次。
3. test_max_iterations_exhaustion_is_failure_not_empty_success
   当前 max_iterations / recursion 耗尽后仍 success=True。
4. test_finish_task_success_must_pass_through_after_agent_exit_gate
   当前业务输出 answer=complete 已出现，但 after_agent sentinel 没有写入 exit_gate_after_agent_seen，证明成功路径绕过 after_agent。

当前通过项：
- test_finish_task_marker_preserves_schema_fields_and_business_output
  说明 finish_task marker/schema/basic business output 语义当前可观察，不能退化。

允许修改：
- packages/graph-agent/src/graph_agent/middleware/exit_control.py
- packages/graph-agent/src/graph_agent/middleware/nudge_injector.py
- packages/graph-agent/src/graph_agent/core/nudge_injector.py
- packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py
- packages/graph-agent/src/graph_agent/middleware/factory.py
- packages/graph-agent/src/graph_agent/middleware/__init__.py
- packages/graph-agent/src/graph_agent/core/error_registry.py
- packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py

baseline 文件只在实现 GREEN 且 Codex 审查接受硬退出后再回写：
- docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/baseline.md

禁止修改：
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/src/graph_agent/middleware/tracing.py
- packages/graph-agent/src/graph_agent/middleware/tool_error.py
- packages/graph-agent/src/graph_agent/middleware/loop_detection.py
- packages/graph-agent/src/graph_agent/core/checkpointer.py
- packages/graph-agent/src/graph_agent/core/state.py
- packages/graph-agent/src/graph_agent/core/runner.py
- packages/graph-agent/src/graph_agent/core/exceptions.py
- packages/graph-agent/src/graph_agent/core/result.py
- packages/graph-agent/src/graph_agent/callbacks/events.py
- packages/graph-agent/src/graph_agent/callbacks/emit.py
- apps/studio/**
- packages/graph-agent-gateway/**

目标行为：
1. AGENT phase 不得因为模型自然停顿、无 tool_calls、空输出、或达到循环/递归上限而静默成功。
2. 合格 finish_task 必须写入 FrameworkState.finish_task_result 等明确 marker。
3. 唯一成功出口是 after_agent exit gate 观察到合格 marker 后放行；CognitiveFlow 不能直接 goto=END 绕过 gate。
4. 模型没有完成信号但仍可继续时，exit-control 必须给模型可见 nudge，消息里要能被测试观察到 finish_task，并让 agent loop 继续。
5. nudge / iteration / recursion 预算耗尽时，结果必须是明确失败或明确诊断，不得 RunResult.success=True 且业务输出为空/残缺。
6. 失败结果必须可机器判定，并能定位 phase / exit-control 语义。可以新增一个清晰的运行期 FATAL 码，例如 [F-v3-agent-exit-control-failed]；也可以使用现有注册 runtime fatal code 加清晰诊断文本。如果新增错误码，只改 error_registry.py，不要改错误契约 V2 或 registry fixture。
7. finish_task schema 不得退化：business_data_md、reasoning、diagnostics_md、schema_validation、parsed data / business output 基本契约保持可用；schema gate / business validator 拒绝路径仍给模型可修正反馈。

实现提示，不是额外需求：
- LangChain AgentMiddleware 支持 after_agent hook；如需 after_agent 返回 jump_to，可使用 langchain.agents.middleware 的 hook_config / after_agent decorator 机制或等价方式声明 can_jump_to=["model"]。
- 如果选择创建 packages/graph-agent/src/graph_agent/middleware/nudge_injector.py，请保持它只是 middleware 侧适配器，不要复制一套不可解释的新 nudge 策略。
- 如果你认为必须改 graph_assembler.py 才能通过 max_iterations / recursion 耗尽测试，先停下汇报，不要擅自修改。

绝对不做：
- 不实现 WS-E2 的 tracing/tool_error/loop_detection 真实逻辑。
- 不做 checkpoint/state/resume。
- 不做 callbacks/events/emit。
- 不做 WS-E1-io 文件 lazy/artifact/read_file/storage。
- 不做 Studio/gateway。
- 不重写 finish_task schema/业务校验体系；只允许为退出闸调整 marker 和退出权边界。
- 不削弱或删除已批准 RED 断言。

执行顺序：
1. 先运行 RED 命令确认失败形态：
   uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q
2. 按 task 文件 Phase 1 -> Phase 5 做最小实现，每阶段跑对应命令。
3. WS-E8 RED 变 GREEN 后，跑完整 WS-E8 suite：
   uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q
4. 跑需求书要求的回归命令：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py -q
   uv run pytest packages/graph-agent/tests/core/test_gamma2_child_graph_isolation.py packages/graph-agent/tests/runtime/test_gamma2_state_io_red.py -q
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q
   uv run pytest packages/graph-agent/tests/middleware/test_chain_topology.py packages/graph-agent/tests/middleware/test_beta_cognitive_flow_schema_gate.py packages/graph-agent/tests/core/test_nudge_injector.py -q
5. 跑 scope / hygiene：
   git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py
   git status --short -- apps/studio packages/graph-agent-gateway
   git diff --check -- packages/graph-agent/src/graph_agent/middleware/exit_control.py packages/graph-agent/src/graph_agent/middleware/nudge_injector.py packages/graph-agent/src/graph_agent/core/nudge_injector.py packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py packages/graph-agent/src/graph_agent/middleware/factory.py packages/graph-agent/src/graph_agent/middleware/__init__.py packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py

回报格式：
1. 修改了哪些文件。
2. 每条验证命令的结果摘要。
3. 明确说明 graph_assembler.py 是否保持无 diff；如果你认为必须改它，停在复审请求，不要继续。
4. 明确说明 forbidden files 是否无 diff；apps/studio/** 和 packages/graph-agent-gateway/** 如已有 dirty，只报告为共享工作树既有状态，不要编辑。
5. 说明最终 exit-control 行为：成功 gate、nudge 路径、耗尽失败路径、失败码或诊断形式。
6. 若有任何 hard-exit 项无法满足，说明原因并停下，不要扩大范围。
```
