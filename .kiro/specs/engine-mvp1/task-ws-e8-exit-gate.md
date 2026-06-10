---
ws_id: WS-E8-exit-gate
task_type: implementation
implementer: Gemini
author: Codex
status: drafted
created: 2026-06-09
requirements: .kiro/specs/engine-mvp1/requirements-ws-e8-exit-gate.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md
  - docs/engine/mvp1/_impl-backlog.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md
  - docs/development/task-spec-standard.md
approved_red_tests:
  - packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py
red_result: "uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q -> 4 failed, 1 passed"
contract_gate: passed
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e8-exit-gate.md
  - packages/graph-agent/src/graph_agent/middleware/exit_control.py
  - packages/graph-agent/src/graph_agent/middleware/nudge_injector.py
  - packages/graph-agent/src/graph_agent/core/nudge_injector.py
  - packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py
  - packages/graph-agent/src/graph_agent/middleware/factory.py
  - packages/graph-agent/src/graph_agent/middleware/__init__.py
  - packages/graph-agent/src/graph_agent/core/error_registry.py
  - packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py
  - docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/baseline.md
forbidden_files:
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
---

# WS-E8 Exit Gate Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Do not weaken them. Implement task-by-task until the approved RED suite is GREEN.

**Goal:** Add AGENT phase exit governance so a phase succeeds only after a qualified `finish_task` marker reaches the `after_agent` exit gate; otherwise the loop nudges the model or returns explicit failure/diagnostics when budget is exhausted.

**Architecture:** Keep the implementation in middleware-owned files. `CognitiveFlowMiddleware` remains responsible for finish_task schema validation and marker writes, while a new exit-control middleware owns the final success/failure decision at the agent exit boundary. Existing six middleware slots must keep their relative order; WS-E8 may add exit-control wiring but must not implement WS-E2 tracing/tool-error/loop-detection behavior or edit `graph_assembler.py` unless a fresh review explicitly approves that hotspot change.

**Tech Stack:** Python 3.13 in this worktree, LangChain `create_agent` middleware hooks, LangGraph `Command` / `jump_to`, Pydantic state models, pytest.

---

## Phase 0: Grounding And Contract Lock

- [ ] Read the requirements file and SSOT pointers before editing.
  _Requirements: WS-E8.grounding / IR2 / IR5._
  Report the current live symbols and behavior:
  - `graph_assembler._build_skill_node`: `create_agent(...)`, `build_middleware_chain(...)`, `max_iterations` / `recursion_limit`, and the current `GraphRecursionError` partial-state fallback. Read only; do not edit.
  - `CognitiveFlowMiddleware._handle_finish_task`: accepted marker write, schema validation, ToolMessage, and current direct `goto=END` behavior.
  - `build_middleware_chain` and `MVP0_MIDDLEWARE_ORDER_CONTRACT`: current chain construction and order.
  - `NudgeInjector.try_standard` / `try_planning` / `counts`: existing nudge text and budget semantics.
  - `ERROR_REGISTRY`: current registered runtime codes and exit-control absence.

- [ ] Confirm the implementation scope before writing production code.
  _Requirements: WS-E8.scope-lock / IR1 / IR7._
  Verification command:
  `git status --short -- packages/graph-agent/src/graph_agent/middleware/exit_control.py packages/graph-agent/src/graph_agent/middleware/nudge_injector.py packages/graph-agent/src/graph_agent/core/nudge_injector.py packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py packages/graph-agent/src/graph_agent/middleware/factory.py packages/graph-agent/src/graph_agent/middleware/__init__.py packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  Expected before implementation: the approved RED test file may be dirty; forbidden `graph_assembler.py` must have no WS-E8 diff.

- [ ] Re-run the approved RED suite before implementing and keep the failure shape unchanged.
  _Requirements: WS-E8.RED / requirements §6 / §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q`
  Expected now: `4 failed, 1 passed`.
  Expected failing tests:
  - `test_agent_without_finish_task_returns_explicit_failure`
  - `test_no_tool_calls_gets_nudged_back_to_model_before_success`
  - `test_max_iterations_exhaustion_is_failure_not_empty_success`
  - `test_finish_task_success_must_pass_through_after_agent_exit_gate`

## Phase 1: Exit-Control Middleware Wiring

- [ ] Create `packages/graph-agent/src/graph_agent/middleware/exit_control.py` with the exit gate as an `AgentMiddleware`.
  _Requirements: WS-E8.after-agent-gate / requirements §5._
  Required public behavior from approved RED:
  - It participates in real `create_agent` middleware execution.
  - It exposes an `after_agent` hook.
  - It can continue the loop by returning `jump_to: "model"` when the phase has no qualified `finish_task_result` and budget still allows a retry.
  - It can fail explicitly when exit governance is exhausted.
  Use LangChain hook metadata such as `@hook_config(can_jump_to=["model"])` or an equivalent supported mechanism if conditional `jump_to` is needed.
  Verification command after wiring:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_finish_task_success_must_pass_through_after_agent_exit_gate -q`
  Expected after later phases: this test passes because normal successful finish reaches `after_agent`.

- [ ] Wire exit-control into `factory.py` / `__init__.py` without reordering the existing six slots.
  _Requirements: WS-E8.middleware-order / requirements §3 / §5._
  Existing slots must remain ordered:
  `ProtocolValidation`, `CognitiveFlow`, `ExecutionControl`, `Tracing`, `ToolError`, `LoopDetection`.
  Add exit-control so it participates in the chain and is visible to `create_agent`, but do not implement or reorder WS-E2 slots.
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_chain_topology.py packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_finish_task_success_must_pass_through_after_agent_exit_gate -q`
  If an existing topology test intentionally pins exactly six slots and fails only because exit-control is now wired, update only the topology assertion needed to represent the new exit-control contract.

- [ ] Use `packages/graph-agent/src/graph_agent/middleware/nudge_injector.py` only if a middleware-side adapter makes the existing core nudge semantics clearer.
  _Requirements: WS-E8.nudge / requirements §2 / §5._
  If this file is created, it must wrap or explain the existing `core/nudge_injector.py` semantics; it must not fork unrelated nudge behavior. If no adapter is needed, leave the file absent and report that decision.

## Phase 2: finish_task Success Must Not Bypass The Gate

- [ ] Adjust `CognitiveFlowMiddleware._handle_finish_task` so accepted finish_task writes the marker and business output but does not directly declare phase success by bypassing the exit gate.
  _Requirements: WS-E8.finish-marker / requirements §5._
  Required preserved marker fields:
  - `reasoning`
  - `diagnostics_md`
  - `business_data_md`
  - `schema_validation`
  - `business_data_parsed` when parsed items exist
  Rejection paths must still return model-visible correction feedback and route back to the model.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_finish_task_marker_preserves_schema_fields_and_business_output packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_finish_task_success_must_pass_through_after_agent_exit_gate -q`

- [ ] Keep schema gate and business validator behavior unchanged.
  _Requirements: WS-E8.schema-no-regression / requirements §5 / §6._
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_beta_cognitive_flow_schema_gate.py packages/graph-agent/tests/runtime/test_gamma2_state_io_red.py -q`
  If these files already include unrelated known failures in this worktree, report the exact failing tests before changing scope.

## Phase 3: No finish_task / No Tool Calls Must Nudge Or Fail

- [ ] Implement the no-finish path in exit-control.
  _Requirements: WS-E8.no-finish-failure / requirements §5 / §6._
  Approved RED behavior:
  - A model response with no tool calls and no qualified `finish_task_result` must not become `RunResult.success=True`.
  - If budget remains, inject a visible nudge message containing `finish_task` and continue the agent loop.
  - If budget is exhausted, raise or return explicit failure/diagnostics with phase / exit-control semantics.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_agent_without_finish_task_returns_explicit_failure packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_no_tool_calls_gets_nudged_back_to_model_before_success -q`

- [ ] Preserve existing core nudge text semantics where possible.
  _Requirements: WS-E8.nudge-semantics / requirements §2 / §5._
  The approved RED only asserts that the retry message is visible to the model and mentions `finish_task`; do not weaken existing `NudgeInjector` tests.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_nudge_injector.py packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_no_tool_calls_gets_nudged_back_to_model_before_success -q`

## Phase 4: Iteration / Recursion Exhaustion Must Be Explicit Failure

- [ ] Make max-iteration / recursion exhaustion fail explicitly instead of returning partial empty state as success.
  _Requirements: WS-E8.exhaustion-failure / requirements §5 / §6 / §8._
  Approved RED behavior:
  - `LoopingToolChatModel` repeatedly calls the business tool.
  - With `max_iterations=2`, the final `RunResult` must have `success is False`.
  - The result must expose `error` or `diagnostics`.
  - `context["answer"]` must remain absent.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_max_iterations_exhaustion_is_failure_not_empty_success -q`

- [ ] If the only viable fix requires editing `packages/graph-agent/src/graph_agent/core/graph_assembler.py`, stop and request review before making that change.
  _Requirements: WS-E8.hotspot-stop / requirements §3 / §7 / §9._
  Verification command before requesting review:
  `git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  Expected for normal WS-E8 implementation: no diff. If not empty, do not continue without explicit approval.

- [ ] Ensure machine-readable failure semantics identify exit-control.
  _Requirements: WS-E8.structured-failure / requirements §5._
  Acceptable implementation forms:
  - a registered runtime FATAL code in `core/error_registry.py` for exit-control, for example `[F-v3-agent-exit-control-failed]`; or
  - an existing registered runtime FATAL code with diagnostic text/details that clearly identify `phase` and `exit-control`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_agent_without_finish_task_returns_explicit_failure packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_max_iterations_exhaustion_is_failure_not_empty_success -q`

## Phase 5: Approved RED Suite To GREEN

- [ ] Run the full approved WS-E8 suite to GREEN.
  _Requirements: WS-E8.hard-exit / requirements §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q`
  Expected after implementation: all five tests pass.

- [ ] Confirm `finish_task` success path still writes marker and business output.
  _Requirements: WS-E8.finish-marker / requirements §8._
  Target tests:
  - `test_finish_task_marker_preserves_schema_fields_and_business_output`
  - `test_finish_task_success_must_pass_through_after_agent_exit_gate`
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_finish_task_marker_preserves_schema_fields_and_business_output packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py::test_finish_task_success_must_pass_through_after_agent_exit_gate -q`

## Phase 6: Required Regression Commands

- [ ] Run WS-E1 create_agent core regressions.
  _Requirements: requirements §6 / §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py -q`

- [ ] Run subagent regressions.
  _Requirements: requirements §6 / §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_gamma2_child_graph_isolation.py packages/graph-agent/tests/runtime/test_gamma2_state_io_red.py -q`

- [ ] Run logic, iterate, and subgraph IO regressions.
  _Requirements: requirements §6 / §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q`

- [ ] Run middleware topology / cognitive-flow regressions.
  _Requirements: requirements §6 / §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/middleware/test_chain_topology.py packages/graph-agent/tests/middleware/test_beta_cognitive_flow_schema_gate.py packages/graph-agent/tests/core/test_nudge_injector.py -q`

## Phase 7: Scope Audit And Handoff

- [ ] Confirm forbidden files are untouched.
  _Requirements: IR1 / IR7 / requirements §8._
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py`
  Expected: no diff. Also run:
  `git status --short -- apps/studio packages/graph-agent-gateway`
  Expected: do not edit these paths; report any pre-existing shared-worktree dirty state separately.

- [ ] Run diff hygiene on WS-E8 touched files.
  _Requirements: implementation quality gate._
  Verification command:
  `git diff --check -- packages/graph-agent/src/graph_agent/middleware/exit_control.py packages/graph-agent/src/graph_agent/middleware/nudge_injector.py packages/graph-agent/src/graph_agent/core/nudge_injector.py packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py packages/graph-agent/src/graph_agent/middleware/factory.py packages/graph-agent/src/graph_agent/middleware/__init__.py packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py`

- [ ] Do not update `docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/baseline.md` before implementation is GREEN and Codex review accepts hard exit.
  _Requirements: IR6 / requirements §10._
  After GREEN, report the exact implemented facts so Codex can truthfully update baseline:
  - exit-control middleware wiring
  - finish_task marker gate behavior
  - nudge behavior and budget/exhaustion failure behavior
  - any still-unimplemented boundary

## Hard Exit Checklist

- [ ] Approved WS-E8 RED suite is GREEN.
- [ ] `finish_task` success marker is written, business output is preserved, and success passes through `after_agent`.
- [ ] AGENT with no `finish_task` never returns silent success.
- [ ] No tool_calls / no completion signal receives visible nudge and can return to the model.
- [ ] Nudge / iteration / recursion exhaustion returns explicit failure or diagnostics.
- [ ] Failure output is machine-readable and identifies phase / exit-control semantics.
- [ ] CognitiveFlow schema validation and business validator retry feedback do not regress.
- [ ] WS-E1 create_agent, subagent, logic, iterate, and subgraph IO regressions pass.
- [ ] Forbidden files have no diff.
- [ ] Baseline update is deferred until Codex review accepts hard exit.

## Gemini Report Format

When finished, report:

1. Files changed.
2. The exact tests run and pass/fail output summary.
3. Whether `graph_assembler.py` remained untouched; if not, stop-state review details.
4. Confirmation that forbidden files have no diff and `apps/studio/**` / `packages/graph-agent-gateway/**` were not edited by this WS.
5. The final exit-control behavior: success gate, nudge path, exhaustion failure path, and failure code/diagnostic form.
6. Any remaining risk or reason a hard-exit item is not satisfied.
