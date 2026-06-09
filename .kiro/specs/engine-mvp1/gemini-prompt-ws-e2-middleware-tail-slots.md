---
ws_id: WS-E2-middleware-tail-slots
artifact: gemini-prompt
status: ready-for-gemini
created: 2026-06-09
task_file: .kiro/specs/engine-mvp1/task-ws-e2-middleware-tail-slots.md
requirements: .kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md
---

# Gemini Prompt - WS-E2 Middleware Tail Slots

```text
你是 /Users/sevenx/Documents/coding/agent-harness/.worktrees/engine-mvp1-ws-e2-middleware-tail-slots 工作区的 engine 模块实现者。请按 TDD 执行 WS-E2 middleware tail slots：RED 测试已由 Codex 写好，并已通过 PM 契约门审查。你的任务是只做最小 GREEN 实现，不扩范围。

工作区：
/Users/sevenx/Documents/coding/agent-harness/.worktrees/engine-mvp1-ws-e2-middleware-tail-slots

当前分支 / 基线：
codex/engine-mvp1-e2-middleware-tail-slots
HEAD: 047d46f6 fix(engine): stabilize ci environment assumptions
Related PR: https://github.com/SevenX77/agent-harness/pull/118

注意：当前 worktree 里已有未提交/未跟踪的 WS-E2 requirements 和 RED 测试。这些是已通过契约门的输入，不是你的实现结果。不要削弱 RED。

任务书：
.kiro/specs/engine-mvp1/task-ws-e2-middleware-tail-slots.md

需求书：
.kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md

铁律：
1. 必须使用 TDD。先复跑已批准 RED，确认失败形状仍是 3 failed, 2 passed，再写生产实现。
2. 已批准 RED 是实现契约；不要改弱测试来变绿。
3. 只做后三槽：Tracing、ToolError、LoopDetection。不得重排六槽链，不得削弱前三槽。
4. 不新增 callback schema，不改 Error V2 registry，不做 checkpoint/state、exit/nudge、file lazy/artifact、runner/io/read_file、Studio、gateway 或依赖锁改动。
5. 如果 RED 或回归证明必须改 forbidden file，先停下汇报，不要直接扩范围。

必须先读并回述关键现状：
- .kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md
  重点：目标行为、owns_files、forbidden files、测试要求、baseline 回写指令。
- .kiro/specs/engine-mvp1/task-ws-e2-middleware-tail-slots.md
  重点：Phase 0 到 Phase 6、Hard Exit Checklist、验证命令。
- docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/mvp1-alignment.md
  重点：六槽顺序、后三槽 no-op 现状、LoopDetection 与 ExecutionControl 分工。
- docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/mvp1-alignment.md
  重点：ToolError 将普通工具异常转为 error ToolMessage。
- docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md
  重点：TracingMiddleware 是内层 tool/LLM 微观 trace 发射器，现阶段只能消费已有 callback/event surface。
- packages/graph-agent/src/graph_agent/middleware/factory.py
  重点：build_middleware_chain 的六槽构造顺序，callbacks 当前只传给 ExecutionControl。
- packages/graph-agent/src/graph_agent/middleware/tracing.py
  重点：当前 no-op，wrap_tool_call 会落到 LangChain base NotImplementedError。
- packages/graph-agent/src/graph_agent/middleware/tool_error.py
  重点：当前 no-op，wrap_tool_call 会落到 LangChain base NotImplementedError。
- packages/graph-agent/src/graph_agent/middleware/loop_detection.py
  重点：当前 no-op，after_model 静默 None。
- packages/graph-agent/src/graph_agent/middleware/execution_control.py
  只读 grounding：已有 dead-end warning 和轻量 loop callback。不要删除或弱化。
- packages/graph-agent/src/graph_agent/callbacks/base.py
  只读：Callback.on_event 默认能分发 ToolCallEvent 到 legacy on_tool_call。
- packages/graph-agent/src/graph_agent/callbacks/events.py
  只读：ToolCallEvent 已有 phase_name/tool_name/args/result/duration_ms/parent_node_id/node_type 字段。不要改 schema。

已批准 RED 测试：
- packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py

先运行 RED：
uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py -q

当前预期 RED：
3 failed, 2 passed

失败形状必须保持干净：
- test_tool_error_converts_tool_exception_to_error_tool_message：ToolErrorHandlingMiddleware.wrap_tool_call 仍是 LangChain base NotImplementedError。
- test_tracing_tail_slot_records_tool_context_from_factory_callbacks：TracingMiddleware.wrap_tool_call 仍是 LangChain base NotImplementedError。
- test_loop_detection_reports_repeated_no_progress_tool_loop：LoopDetectionMiddleware.after_model 对重复 same tool/signature 窗口返回 None。

已通过项：
- test_factory_keeps_tail_slots_in_mvp1_contract_order：六槽顺序仍是 ProtocolValidation -> CognitiveFlow -> ExecutionControl -> Tracing -> ToolError -> LoopDetection。
- test_live_agent_assembly_passes_tail_slots_to_create_agent：live assemble_graph 已把后三槽传入 create_agent middleware chain。

允许修改：
- packages/graph-agent/src/graph_agent/middleware/tracing.py
- packages/graph-agent/src/graph_agent/middleware/tool_error.py
- packages/graph-agent/src/graph_agent/middleware/loop_detection.py
- packages/graph-agent/src/graph_agent/middleware/factory.py

已批准的契约/测试/交接输入可保留；除非发现夹具错误，否则不要改弱：
- .kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md
- .kiro/specs/engine-mvp1/task-ws-e2-middleware-tail-slots.md
- .kiro/specs/engine-mvp1/gemini-prompt-ws-e2-middleware-tail-slots.md
- packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py

禁止修改：
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/src/graph_agent/core/checkpointer.py
- packages/graph-agent/src/graph_agent/core/state.py
- packages/graph-agent/src/graph_agent/middleware/nudge_injector.py
- packages/graph-agent/src/graph_agent/callbacks/events.py
- packages/graph-agent/src/graph_agent/callbacks/emit.py
- packages/graph-agent/src/graph_agent/callbacks/base.py
- packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
- packages/graph-agent/src/graph_agent/io/**
- packages/graph-agent/src/graph_agent/core/runner.py
- apps/studio/**
- packages/graph-agent-gateway/**
- uv.lock

目标行为：
1. ToolError：普通工具执行抛出 ordinary Exception 时，返回 ToolMessage(status="error")，不要让 phase 直接崩。
2. ToolError：error ToolMessage 必须保留 phase、tool name、tool_call_id、异常类型和异常摘要。
3. ToolError：GraphBubbleUp / GraphInterrupt / NodeInterrupt 等 LangGraph 控制流必须原样 re-raise，不得包成普通工具错误。
4. ToolError：实现 sync wrap_tool_call，也补 async awrap_tool_call parity。
5. Tracing：build_middleware_chain(callbacks=[...]) 生成的 TracingMiddleware 必须拿到 callbacks。
6. Tracing：tool hook 调 handler 后原样返回结果，并对 ToolMessage 结果发出 tool trace 上下文。
7. Tracing：通过现有 Callback/ToolCallEvent surface 发出 phase、tool、args、result 摘要；可以使用 ToolCallEvent 的 parent_node_id/node_type 现有字段，但不得改 callbacks/events.py。
8. Tracing：callback 抛错不能破坏工具执行；handler 抛错不要在 Tracing 中吞掉。
9. LoopDetection：重复同一 tool/signature 且无进展达到阈值时，不得静默 None；必须产生中断或可见诊断。
10. LoopDetection：最小 GREEN 可返回 {"messages": [HumanMessage(name="loop_detection_diagnostic", content=...)]}，内容必须含 phase 和 tool。
11. LoopDetection：与 ExecutionControl 分工清楚，不删除、不弱化、不复制 dead-end warning；不做 exit gate、finish_task marker 或 nudge 注入。
12. 六槽顺序和 live create_agent 接线保持不变。

实现建议边界：
- ToolError 中先 `except GraphBubbleUp: raise`，再 `except Exception as exc:`；不要 catch BaseException。
- ToolError 的 diagnostic 文本保持短而可诊断，例如包含 phase/tool/call_id/RuntimeError/boom。
- Tracing 发 ToolCallEvent 时，如果没有可靠 parent_node_id，就使用 None；node_type 可以是 "tool"。不要发不存在的事件类。
- Tracing 可先调用 callback.on_event(event)。如果 callback 未覆盖 on_event，Callback 基类会分发到 on_tool_call；如果需要兼容直接 legacy callback，可做安全 fallback，但不要双发重复事件给同一个 callback。
- LoopDetection 的 signature 可基于 tool name + ToolMessage content 的稳定字符串/JSON 摘要。窗口和阈值保持小而保守，例如 window=5、threshold=3。
- LoopDetection 诊断去重按 signature 做，避免同一状态反复注入相同消息。
- 如果遇到 Command 结果，ToolError 和 Tracing 应原样传回；不要为了本 WS 解析或重写 Command。

执行顺序：
1. 先运行 RED 命令，确认仍是 3 failed, 2 passed 且失败形状如上。
2. 实现 ToolError sync hook，跑：
   uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py::test_tool_error_converts_tool_exception_to_error_tool_message -q
3. 给 ToolError 补 async parity，并跑：
   uv run mypy packages/graph-agent/src/graph_agent/middleware/tool_error.py
4. 让 factory 把 callbacks 传给 TracingMiddleware，实现 Tracing sync hook，跑：
   uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py::test_tracing_tail_slot_records_tool_context_from_factory_callbacks -q
5. 给 Tracing 补 async parity，并跑：
   uv run mypy packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/factory.py
6. 实现 LoopDetection after_model，跑：
   uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py::test_loop_detection_reports_repeated_no_progress_tool_loop -q
7. 跑完整 WS-E2 RED 到 GREEN：
   uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py -q
8. 跑 WS-E1 必需回归：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q
9. 跑 middleware-adjacent 回归：
   uv run pytest packages/graph-agent/tests/middleware/test_execution_control.py packages/graph-agent/tests/middleware/test_cognitive_flow.py packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py -q
10. 跑 touched-file mypy：
    uv run mypy packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/middleware/factory.py
11. 跑 scope / hygiene：
    git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py packages/graph-agent/src/graph_agent/middleware/nudge_injector.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/callbacks/base.py packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/core/runner.py
    git status --short -- apps/studio packages/graph-agent-gateway uv.lock
    git diff --check -- .kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md .kiro/specs/engine-mvp1/task-ws-e2-middleware-tail-slots.md .kiro/specs/engine-mvp1/gemini-prompt-ws-e2-middleware-tail-slots.md packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/middleware/factory.py packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py

uv.lock 注意：
- 本 WS 没有依赖变更。
- 如果 uv run 摸脏 uv.lock，且没有真实依赖变更，恢复 uv.lock。

不要更新 baseline，除非用户/PM 明确要求。GREEN 后只报告真实落地行为，交给 Codex/PM 回写：
- docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/baseline.md
- docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/baseline.md
- docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md
- docs/engine/mvp1/_impl/IMPL_PLAN.md 仅 PM 要求维护进度面板时更新

回报格式：
1. 修改了哪些文件。
2. 每条验证命令的结果摘要。
3. 明确说明 forbidden engine files、apps/studio/**、packages/graph-agent-gateway/**、uv.lock 是否无 WS-E2 diff。
4. 说明最终 ToolError、Tracing、LoopDetection、六槽顺序、live create_agent 接线行为。
5. baseline 是否留给 Codex/PM 回写。
6. 若有任何 hard-exit 项无法满足，说明原因并停下，不要扩大范围。
```
