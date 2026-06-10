---
ws_id: WS-E5-checkpoint-inner
task_type: implementation
implementer: Gemini
author: Codex
status: drafted
created: 2026-06-09
requirements: .kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
contract_gate: "passed by PM/user on 2026-06-09; approved RED result is 1 failed, 3 passed"
scope_expansion:
  - "2026-06-09: PM/user accepted that GREEN requires core/graph_assembler.py AGENT/iterate namespace wiring; graph_assembler.py is allowed for the minimal WS-E5 fix only."
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md
  - docs/engine/mvp1/_impl-backlog.md A3
  - docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md §1-§6/§8
  - docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/mvp1-alignment.md §1-§6/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md §2/§5/§6
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md §2/§5
  - docs/engine/mvp1/01-contract/04-data-contracts/mvp1-alignment.md §2/§5/§6
approved_red_tests:
  - packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py
red_result: "uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py -q -> 1 failed, 3 passed"
regression_result: "uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q -> 36 passed"
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md
  - .kiro/specs/engine-mvp1/task-ws-e5-checkpoint-inner.md
  - .kiro/specs/engine-mvp1/gemini-prompt-ws-e5-checkpoint-inner.md
  - packages/graph-agent/src/graph_agent/core/checkpointer.py
  - packages/graph-agent/src/graph_agent/core/state.py
  - packages/graph-agent/src/graph_agent/core/runner.py
  - packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py
forbidden_files:
  - packages/graph-agent/src/graph_agent/middleware/tracing.py
  - packages/graph-agent/src/graph_agent/middleware/tool_error.py
  - packages/graph-agent/src/graph_agent/middleware/loop_detection.py
  - packages/graph-agent/src/graph_agent/middleware/nudge_injector.py
  - packages/graph-agent/src/graph_agent/io/**
  - packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
  - packages/graph-agent/src/graph_agent/callbacks/events.py
  - packages/graph-agent/src/graph_agent/callbacks/emit.py
  - packages/graph-agent/src/graph_agent/core/loader.py
  - apps/studio/**
  - packages/graph-agent-gateway/**
---

# WS-E5 Checkpoint Inner Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Do not weaken them. Implement the smallest GREEN change that satisfies the approved RED suite, then stop for review.

**Goal:** Make AGENT inner loop checkpoints share the outer base checkpointer and remain recoverable under stable, non-colliding namespaces, including when AGENT runs inside graph iterate.

**Architecture:** Keep the state boundary split: outer graph checkpoints own `WorkflowState.data` / `flow`, inner AGENT checkpoints own messages / agent state, and both address the same base saver by `thread_id` plus `checkpoint_ns`. The preferred production landing area is `core/checkpointer.py` for GraphAgent-owned namespace/checkpointer helpers and `core/state.py` for business/framework boundary helpers. `core/runner.py` is only for run invoke/config boundary fixes. PM/user later expanded scope for the minimal `core/graph_assembler.py` AGENT/iterate namespace wiring required by the approved RED.

**Tech Stack:** Python 3.12, pytest, LangGraph `InMemorySaver`, existing `compile_skill` / `assemble_graph` / `WorkflowState` runtime.

---

## Phase 0: Grounding And Scope Lock

- [ ] Read the requirements file and SSOT pointers before editing.
  _Requirements: WS-E5-checkpoint-inner grounding._
  Verify by reporting the current live symbols and behavior:
  - `packages/graph-agent/src/graph_agent/core/checkpointer.py`: shared checkpointer factory exists; no GraphAgent-owned namespace helper is exported here yet.
  - `packages/graph-agent/src/graph_agent/core/state.py`: `BusinessData`, `FrameworkState`, `WorkflowState`, `StateManager.update_business`, `StateManager.update_framework`, and `StateManager.route_finish_task` own state boundary invariants.
  - `packages/graph-agent/src/graph_agent/core/runner.py`: run invoke path resolves a checkpointer and passes `thread_id` to graph config.
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`: read-only grounding for outer graph compile, current `NamespaceCheckpointer`, AGENT `create_agent`, and graph iterate config.

- [ ] Confirm the worktree starts from the approved WS-E5 RED state.
  _Requirements: TDD RED evidence / baseline audit._
  Verification command:
  `git status --short --branch`
  Expected before implementation: WS-E5 requirements, task/prompt, and approved RED test may be untracked or dirty; no production implementation file should be dirty yet.

- [ ] Re-run the approved RED suite before implementing.
  _Requirements: approved RED is the contract._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py -q`
  Expected before implementation: `1 failed, 3 passed`.
  Expected failing test:
  - `test_agent_inside_graph_iterate_preserves_iteration_namespace`
  Expected failure shape:
  - same base saver and same `thread_id` have outer `""` checkpoints and AGENT `"agent:main"` checkpoints;
  - no checkpoint namespace contains both `iter1`/`iter2` and `agent`;
  - failure is about namespace composition, not fixture setup, model calls, or business data parsing.

- [ ] Re-run the required WS-E1 regression baseline before implementing.
  _Requirements: WS-E1 dependency remains reliable._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q`
  Expected before implementation: all tests pass.

## Phase 1: Scope Feasibility Gate

- [ ] Determine whether the approved RED can be made GREEN using only `core/checkpointer.py`, `core/state.py`, and conditionally `core/runner.py`.
  _Requirements: owns_files / forbidden files._
  Required decision:
  - If the necessary change is only a reusable namespace/checkpointer helper or state boundary helper in owned files, continue to Phase 2.
  - If the necessary change is at AGENT `create_agent`, AGENT invoke config, graph iterate config, or the local namespace wrapper call site in `core/graph_assembler.py`, stop and report that PM must expand owns before implementation.
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  Expected: no diff. Do not create a speculative helper that is unused by the live path just to stay within owns.

## Phase 2: Shared Base And Namespace Helper Implementation

- [ ] If Phase 1 confirms an owned-file path exists, implement the smallest GraphAgent-owned namespace behavior needed by the approved RED.
  _Requirements: `04-run-outer/03-checkpoint` CK1/CK2; `05-run-inner/08-messages-state` HS1._
  Required behavior from approved RED:
  - with an explicit outer `InMemorySaver`, AGENT inner checkpoints use that same base saver;
  - the outer graph namespace remains queryable as `checkpoint_ns == ""`;
  - AGENT inner checkpoints include stable agent/phase ownership;
  - history APIs on the same base and same `thread_id` can distinguish outer and AGENT checkpoints.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_agent_inner_checkpoint_writes_to_shared_thread_and_namespace packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_history_queries_distinguish_outer_and_agent_checkpoints -q`
  Expected after implementation: selected tests pass.

- [ ] Preserve existing no-explicit-checkpointer behavior.
  _Requirements: requirements §5.1 default path._
  Required behavior:
  - no explicit outer checkpointer path should keep using the existing default behavior;
  - no second saver should be introduced when an explicit base saver exists.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py -q`
  Expected after implementation: all tests pass.

## Phase 3: Iterate And Agent Namespace Composition

- [ ] Make AGENT checkpoints created inside graph iterate preserve both iteration and agent/phase scope.
  _Requirements: `02-iterate` IT1/IT2; requirements §5.2._
  Required behavior from approved RED:
  - graph iterate round 1 produces at least one checkpoint namespace containing both `iter1` and `agent`;
  - graph iterate round 2 produces at least one checkpoint namespace containing both `iter2` and `agent`;
  - AGENT namespace must not overwrite or drop the active iterate namespace.
  Important scope gate:
  - If this requires changing `core/graph_assembler.py`, stop before editing and request PM scope expansion. Do not edit forbidden files.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_agent_inside_graph_iterate_preserves_iteration_namespace -q`
  Expected after allowed implementation or after explicit scope expansion: test passes.

## Phase 4: Business / Framework Boundary

- [ ] Preserve the existing business/framework split while checkpoint namespaces change.
  _Requirements: `01-contract/04-data-contracts` DC3; requirements §5.3/§5.5._
  Required behavior from approved RED:
  - final business data contains declared business output such as `answer`;
  - final business data does not contain `_`-prefixed fields;
  - final business data does not contain messages, tool calls, checkpoint config, runtime, callbacks, or compiled graph objects;
  - `flow.thread_id` and `flow.run_id` remain framework fields;
  - `StateManager.update_business` rejects `_checkpoint_ns`;
  - `StateManager.route_finish_task` routes `_` metadata into `flow.finish_task_result`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_agent_inner_checkpoint_writes_to_shared_thread_and_namespace packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_finish_task_framework_meta_stays_out_of_business_data -q`
  Expected after implementation: selected tests pass.

## Phase 5: Full Verification And Scope Audit

- [ ] Run the approved WS-E5 RED suite to GREEN.
  _Requirements: requirements §8 hard exit._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py -q`
  Expected after implementation: all tests pass.

- [ ] Run the required WS-E1 regression suite.
  _Requirements: requirements §6 regression suite._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q`
  Expected after implementation: all tests pass.

- [ ] Confirm forbidden files are untouched unless PM explicitly expanded scope.
  _Requirements: owns_files / forbidden files._
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/middleware/nudge_injector.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/core/loader.py apps/studio packages/graph-agent-gateway`
  Expected: no diff, unless PM expanded scope for `core/graph_assembler.py` after Phase 1/3.

- [ ] Confirm no dependency or lockfile churn.
  _Requirements: scope hygiene._
  Verification command:
  `git status --short -- uv.lock`
  Expected: no diff. If `uv.lock` was touched by `uv run` and no dependency changed, restore it.

- [ ] Run diff hygiene on touched WS files.
  _Requirements: implementation quality gate._
  Verification command:
  `git diff --check -- .kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md .kiro/specs/engine-mvp1/task-ws-e5-checkpoint-inner.md .kiro/specs/engine-mvp1/gemini-prompt-ws-e5-checkpoint-inner.md packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py packages/graph-agent/src/graph_agent/core/runner.py`
  Expected: no output.

## Phase 6: Baseline Handoff After GREEN

- [ ] Do not update baseline before implementation is GREEN and Codex review accepts the hard exit.
  _Requirements: requirements §10 / IR6._
  After GREEN, report the exact landed behavior so Codex/PM can truthfully update:
  - `docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md`: shared base, outer/inner namespace distinction, history/recovery boundary, and remaining data delta/compact/durability gaps.
  - `docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/baseline.md`: whether AGENT inner messages are checkpointed under namespace, and remaining summarization/HITL resume gaps.
  - `docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md`: true iterate namespace and checkpoint interaction only.
  - `docs/engine/mvp1/01-contract/04-data-contracts/baseline.md`: only if state helper or business/framework boundaries truly changed.
  - `docs/engine/mvp1/_impl/IMPL_PLAN.md`: only if PM asks to maintain the progress panel.

## Hard Exit Checklist

- [ ] Approved WS-E5 RED suite is GREEN.
- [ ] Required WS-E1 create_agent, LOGIC, iterate, and subgraph IO regression suite is GREEN.
- [ ] AGENT inner loop uses the shared base checkpointer when one is supplied by the outer graph.
- [ ] Same `thread_id` can query both outer and AGENT checkpoints from the same base saver.
- [ ] Outer namespace and AGENT namespace are distinguishable by history/get APIs.
- [ ] Two AGENT phases would not collapse into the same namespace because agent/phase ownership is stable.
- [ ] AGENT checkpoints inside graph iterate preserve both iteration and agent/phase scope.
- [ ] Outer `WorkflowState.data` is not polluted by messages, tool-call internals, checkpoint config, runtime/callback, compiled graph, or `_` framework fields.
- [ ] `StateManager.update_business` and `route_finish_task` keep `_` metadata out of business data.
- [ ] No WS-E1-io file lazy/artifact/business_data_md implementation was added.
- [ ] No callbacks/events/emit, middleware E2/E8, Studio, gateway, loader, or graph-agent IO work was added.
- [ ] `core/graph_assembler.py` remains untouched unless PM explicitly expanded scope after a stop request.
- [ ] `uv.lock` is clean or restored.
- [ ] `git diff --check` is clean.

## Gemini Report Format

When finished, report:

1. Files changed.
2. The exact verification commands run and pass/fail output summary.
3. Whether implementation stayed within owns_files; if not, include the explicit PM scope-expansion approval.
4. The final checkpoint behavior: shared base, namespace shape, history query behavior, and iterate+agent composition behavior.
5. The final state-boundary behavior: what remains in business data and what remains in framework/agent state.
6. Confirmation that forbidden engine files, `apps/studio/**`, `packages/graph-agent-gateway/**`, and `uv.lock` have no unauthorized WS-E5 diff.
7. Whether baseline docs were intentionally left for Codex/PM handoff or updated by explicit instruction.
8. Any hard-exit item not satisfied and the reason you stopped instead of expanding scope.
