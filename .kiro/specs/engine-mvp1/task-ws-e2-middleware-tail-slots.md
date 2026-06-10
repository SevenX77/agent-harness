---
ws_id: WS-E2-middleware-tail-slots
task_type: implementation
implementer: Gemini
author: Codex
status: ready-for-gemini
created: 2026-06-09
requirements: .kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
related_pr: https://github.com/SevenX77/agent-harness/pull/118
contract_gate: "PASS by PM/user on 2026-06-09; approved RED result is 3 failed, 2 passed"
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md
  - docs/engine/mvp1/_impl-backlog.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/baseline.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/baseline.md
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md
approved_red_tests:
  - packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py
red_result: "uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py -q -> 3 failed, 2 passed"
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md
  - .kiro/specs/engine-mvp1/task-ws-e2-middleware-tail-slots.md
  - .kiro/specs/engine-mvp1/gemini-prompt-ws-e2-middleware-tail-slots.md
  - packages/graph-agent/src/graph_agent/middleware/tracing.py
  - packages/graph-agent/src/graph_agent/middleware/tool_error.py
  - packages/graph-agent/src/graph_agent/middleware/loop_detection.py
  - packages/graph-agent/src/graph_agent/middleware/factory.py
  - packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py
forbidden_files:
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
---

# WS-E2 Middleware Tail Slots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Do not weaken them. Implement the smallest GREEN behavior for the approved RED suite, then run the required regressions.

**Goal:** Turn the three tail middleware slots from no-op placeholders into the MVP1 minimum behavior for tracing, tool-error recovery, and hard loop diagnostics while preserving the six-slot create_agent chain.

**Architecture:** Keep the work inside the existing middleware tail slots. `ToolErrorHandlingMiddleware` owns ordinary tool exception conversion, `TracingMiddleware` owns tool hook callback emission, and `LoopDetectionMiddleware` owns repeated no-progress diagnostics. `factory.py` may only pass callbacks/config into the tail slots; it must not reorder or weaken the first three slots.

**Tech Stack:** Python 3.13 in this worktree, pytest, LangChain `AgentMiddleware`, LangGraph `ToolCallRequest`, LangChain `ToolMessage`, existing graph-agent callback/event surface.

---

## Phase 0: Grounding And Scope Lock

- [ ] Read the requirements file and SSOT pointers before editing.
  _Requirements: requirements §2, §3, §7._
  Verify by reporting the current live symbols and behavior:
  - `packages/graph-agent/src/graph_agent/middleware/factory.py`: `build_middleware_chain` constructs the six slots in contract order, but passes callbacks only to `ExecutionControlMiddleware`.
  - `packages/graph-agent/src/graph_agent/middleware/tracing.py`: currently stores only `_phase_name`; `wrap_tool_call` falls through to the LangChain base `NotImplementedError`.
  - `packages/graph-agent/src/graph_agent/middleware/tool_error.py`: currently stores only `_phase_name`; `wrap_tool_call` falls through to the LangChain base `NotImplementedError`.
  - `packages/graph-agent/src/graph_agent/middleware/loop_detection.py`: currently stores only `_phase_name`; `after_model` falls through to the base no-op and returns `None`.
  - `packages/graph-agent/src/graph_agent/middleware/execution_control.py`: already owns dead-end warnings and lightweight loop callbacks; read it for boundaries, do not replace it.
  - `packages/graph-agent/src/graph_agent/callbacks/base.py` and `callbacks/events.py`: read-only callback/event surface for Tracing.

- [ ] Confirm the working tree contains only approved WS-E2 input before implementing.
  _Requirements: file ownership / forbidden files._
  Verification command:
  `git status --short`
  Expected before implementation: approved requirements and RED test may be dirty/untracked; `task-ws-e2-middleware-tail-slots.md` and `gemini-prompt-ws-e2-middleware-tail-slots.md` are handoff files; no production implementation diff yet; no `uv.lock` diff.

- [ ] Re-run the approved RED suite before implementing and keep the failure shape unchanged.
  _Requirements: TDD RED evidence; requirements §6 / §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py -q`
  Expected now: `3 failed, 2 passed`.
  Expected failure causes:
  - `test_tool_error_converts_tool_exception_to_error_tool_message`: `ToolErrorHandlingMiddleware.wrap_tool_call` raises the LangChain base `NotImplementedError`.
  - `test_tracing_tail_slot_records_tool_context_from_factory_callbacks`: `TracingMiddleware.wrap_tool_call` raises the LangChain base `NotImplementedError`.
  - `test_loop_detection_reports_repeated_no_progress_tool_loop`: `LoopDetectionMiddleware.after_model` silently returns `None`.
  - `test_factory_keeps_tail_slots_in_mvp1_contract_order` passes.
  - `test_live_agent_assembly_passes_tail_slots_to_create_agent` passes.

## Phase 1: ToolError Ordinary Exception Recovery

- [ ] Implement sync `ToolErrorHandlingMiddleware.wrap_tool_call` for ordinary tool exceptions.
  _Requirements: requirements §5.2._
  Required behavior from approved RED:
  - Call the provided `handler(request)`.
  - If the handler returns a `ToolMessage` or `Command`, pass it through unchanged.
  - If the handler raises `langgraph.errors.GraphBubbleUp` or a subclass such as `GraphInterrupt` / `NodeInterrupt`, re-raise it unchanged.
  - If the handler raises an ordinary `Exception`, return `ToolMessage(status="error", name=tool_name, tool_call_id=tool_call_id, content=diagnostic)`.
  - The diagnostic content must include phase name, tool name, tool call id, exception type, and exception summary.
  - Do not catch `BaseException`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py::test_tool_error_converts_tool_exception_to_error_tool_message -q`
  Expected after implementation: test passes.

- [ ] Add async parity with `awrap_tool_call`.
  _Requirements: live create_agent may run sync or async; requirements §5.1 tail slots must be real hook participants._
  Required behavior:
  - Match sync behavior exactly, using `await handler(request)`.
  - Re-raise `GraphBubbleUp` / interrupts unchanged.
  - Convert only ordinary `Exception` into an error `ToolMessage`.
  Verification command:
  `uv run mypy packages/graph-agent/src/graph_agent/middleware/tool_error.py`
  Expected after implementation: `Success: no issues found`.

## Phase 2: Tracing Tool Hook And Callback Context

- [ ] Update `build_middleware_chain` to pass callbacks into `TracingMiddleware`.
  _Requirements: requirements §5.4 / §6 Tracing via `build_middleware_chain(callbacks=[...])`._
  Required behavior:
  - Keep `MIDDLEWARE_ORDER_CONTRACT` unchanged.
  - Keep all first-three-slot constructor arguments unchanged.
  - Only pass `callbacks=callbacks` and `phase_name=phase_name` into `TracingMiddleware`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py::test_factory_keeps_tail_slots_in_mvp1_contract_order -q`
  Expected after implementation: test still passes.

- [ ] Implement sync `TracingMiddleware.wrap_tool_call`.
  _Requirements: requirements §5.4 / observability alignment §2 / §6._
  Required behavior from approved RED:
  - Call the handler exactly once.
  - Return the handler result unchanged.
  - When the result is a `ToolMessage`, emit tool trace context to the configured callbacks.
  - Emitted context must include phase name, tool name, args, and a string result summary.
  - Prefer `ToolCallEvent` via `callback.on_event(event)` because existing schema already supports `parent_node_id` and `node_type`.
  - If a callback only implements legacy `on_tool_call`, make sure it can still receive the event through `Callback.on_event` default dispatch or an explicit fallback.
  - Callback failures must not break tool execution.
  - If no reliable parent node id is available in `ToolCallRequest`, leave `parent_node_id=None`; set `node_type="tool"` only if using the existing `ToolCallEvent` field. Do not modify `callbacks/events.py`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py::test_tracing_tail_slot_records_tool_context_from_factory_callbacks -q`
  Expected after implementation: test passes.

- [ ] Add async parity with `awrap_tool_call`.
  _Requirements: requirements §5.4 live hook coverage._
  Required behavior:
  - Match sync tracing behavior exactly with `await handler(request)`.
  - Do not swallow exceptions; let ToolError or the caller handle them according to middleware order.
  Verification command:
  `uv run mypy packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/factory.py`
  Expected after implementation: `Success: no issues found`.

## Phase 3: LoopDetection Repeated No-Progress Diagnostic

- [ ] Implement `LoopDetectionMiddleware.after_model` for repeated no-progress tool output windows.
  _Requirements: requirements §5.3 and middleware alignment MW2._
  Required behavior from approved RED:
  - Inspect recent `ToolMessage` entries from `state["messages"]`.
  - Detect at least three occurrences of the same tool/signature within a small recent window.
  - The signature must be based on tool name plus stable content summary so repeated identical results are treated as no progress.
  - When threshold is reached, do not return `None`.
  - Either raise `GraphAgentFatalError` with a diagnostic containing phase and tool, or return a state update with a visible diagnostic message containing phase and tool.
  - The smallest preferred GREEN is `{"messages": [HumanMessage(name="loop_detection_diagnostic", content=diagnostic)]}`.
  - Deduplicate repeated diagnostics by signature so repeated `after_model` calls do not spam identical diagnostics.
  - Do not delete, weaken, or duplicate `ExecutionControlMiddleware` dead-end warning behavior.
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py::test_loop_detection_reports_repeated_no_progress_tool_loop -q`
  Expected after implementation: test passes.

- [ ] Keep LoopDetection separate from exit/nudge behavior.
  _Requirements: requirements §5.3 / §9._
  Required non-behavior:
  - Do not implement exit gate.
  - Do not write finish_task markers.
  - Do not inject nudge messages.
  - Do not touch `middleware/nudge_injector.py`.
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/middleware/nudge_injector.py`
  Expected after implementation: no diff.

## Phase 4: Approved RED Suite To GREEN

- [ ] Run the full approved WS-E2 RED suite to GREEN.
  _Requirements: requirements §8 hard exit._
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py -q`
  Expected after implementation: all tests pass.

- [ ] Confirm the six-slot live chain still enters create_agent.
  _Requirements: requirements §5.1 / §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py::test_factory_keeps_tail_slots_in_mvp1_contract_order packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py::test_live_agent_assembly_passes_tail_slots_to_create_agent -q`
  Expected after implementation: both tests pass.

## Phase 5: WS-E1 Regression And Quality Gates

- [ ] Run the existing WS-E1 create_agent and runtime regressions required by WS-E2.
  _Requirements: requirements §5.5 / §6 / §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q`
  Expected after implementation: all selected tests pass, except pre-existing unrelated failures must be reported with exact names and evidence.

- [ ] Run middleware-adjacent regression coverage.
  _Requirements: no regression to first three slots._
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_execution_control.py packages/graph-agent/tests/middleware/test_cognitive_flow.py packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py -q`
  Expected after implementation: all selected tests pass, except pre-existing unrelated failures must be reported with exact names and evidence.

- [ ] Run type checking for touched middleware files.
  _Requirements: implementation quality gate._
  Verification command:
  `uv run mypy packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/middleware/factory.py`
  Expected after implementation: `Success: no issues found`.

- [ ] Confirm forbidden files are untouched.
  _Requirements: requirements §3 / §9._
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py packages/graph-agent/src/graph_agent/middleware/nudge_injector.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/callbacks/base.py packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/core/runner.py`
  Expected: no diff.

- [ ] Confirm Studio, gateway, and dependency lock are untouched.
  _Requirements: requirements §3 / §9._
  Verification command:
  `git status --short -- apps/studio packages/graph-agent-gateway uv.lock`
  Expected: no WS-E2 diff. If `uv.lock` was touched by `uv run` and no dependency changed, restore it.

- [ ] Run diff hygiene.
  _Requirements: implementation quality gate._
  Verification command:
  `git diff --check -- .kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md .kiro/specs/engine-mvp1/task-ws-e2-middleware-tail-slots.md .kiro/specs/engine-mvp1/gemini-prompt-ws-e2-middleware-tail-slots.md packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/middleware/factory.py packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py`
  Expected: no output.

## Phase 6: Baseline Handoff After GREEN

- [ ] Do not update baseline before implementation is GREEN and Codex review accepts the hard exit.
  _Requirements: requirements §10._
  After GREEN, report the exact landed behavior so Codex can truthfully update:
  - `docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/baseline.md`: record the actual tail slot hook behavior, callback/config wiring, and live six-slot state.
  - `docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/baseline.md`: record ordinary tool exception to error `ToolMessage` behavior and control-flow boundary.
  - `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md`: record only the TracingMiddleware callback/tool trace behavior that truly landed; do not claim WS-E4 emit or future schema work.
  - `docs/engine/mvp1/_impl/IMPL_PLAN.md`: update only if PM asks for progress-panel maintenance.

## Hard Exit Checklist

- [ ] Approved WS-E2 RED suite is GREEN.
- [ ] ToolError converts ordinary tool exceptions into `ToolMessage(status="error")`.
- [ ] ToolError diagnostic includes phase, tool name, tool call id, and exception summary.
- [ ] ToolError re-raises `GraphBubbleUp` / interrupt control flow unchanged.
- [ ] Tracing receives callbacks from `build_middleware_chain(callbacks=[...])`.
- [ ] Tracing tool hook returns handler results unchanged and emits tool context to existing callback/event surface.
- [ ] Tracing does not modify `callbacks/events.py`, `callbacks/emit.py`, or `callbacks/base.py`.
- [ ] LoopDetection reports or interrupts repeated same tool/signature no-progress loops and does not silently return `None` at threshold.
- [ ] LoopDetection does not delete or weaken `ExecutionControlMiddleware`.
- [ ] Six-slot order remains `ProtocolValidation -> CognitiveFlow -> ExecutionControl -> Tracing -> ToolError -> LoopDetection`.
- [ ] Live agent assembly still passes the tail slots into `create_agent`.
- [ ] WS-E1 create_agent, logic runtime, iterate runtime, and subgraph IO regressions do not degrade.
- [ ] No checkpoint/state, exit/nudge, callback schema/emit, file lazy/artifact, runner/io/read_file, Studio, gateway, or `uv.lock` work was implemented.
- [ ] `git diff --check` is clean.

## Gemini Report Format

When finished, report:

1. Files changed.
2. The exact verification commands run and pass/fail output summary.
3. Confirmation that forbidden engine files, `apps/studio/**`, `packages/graph-agent-gateway/**`, and `uv.lock` have no WS-E2 diff.
4. Final landed behavior for ToolError, Tracing, LoopDetection, six-slot order, and live agent assembly.
5. Whether baseline docs were intentionally left for Codex/PM handoff or updated by explicit instruction.
6. Any hard-exit item not satisfied and the reason you stopped instead of expanding scope.
