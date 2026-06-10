---
ws_id: WS-E4-runtime-edge-events
task_type: implementation
implementer: Gemini
author: Codex
status: drafted
created: 2026-06-10
requirements: .kiro/specs/engine-mvp1/requirements-ws-e4-runtime-edge-events.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
spec_ssot:
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md §3/§5/§8
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md 后端功能 §1/§4/§5
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md §2/§3/§5/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md §2/§3/§5/§7
  - docs/engine/mvp1/03-api-contract/mvp1-alignment.md §2.2/§3.2
approved_red_tests:
  - packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py
  - packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py
red_result: "uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py -q -> 4 failed, 1 xfailed"
base:
  branch: codex/engine-mvp1-ws-e4-runtime-edge-events
  commit: 34ee40f1
  stacked_on_ws_e1_io: false
owns_files:
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/src/graph_agent/runtime/state_mapper.py
  - packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py
  - packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py
forbidden_files:
  - apps/studio/**
  - packages/graph-agent-gateway/**
  - packages/graph-agent/src/graph_agent/callbacks/events.py
  - packages/graph-agent/src/graph_agent/callbacks/emit.py
  - packages/graph-agent/src/graph_agent/callbacks/base.py
  - packages/graph-agent/src/graph_agent/core/runner.py
  - packages/graph-agent/src/graph_agent/io/**
  - packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
  - packages/graph-agent/src/graph_agent/core/checkpointer.py
  - packages/graph-agent/src/graph_agent/core/exceptions.py
  - packages/graph-agent/src/graph_agent/core/error_registry.py
  - packages/graph-agent/src/graph_agent/core/result.py
---

# WS-E4 Runtime Edge Events Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Re-run them before editing production code, do not weaken them, and keep `InputFileInjectedEvent` behind the WS-E1-io dependency gate.

**Goal:** Emit V4 runtime edge events from real engine execution for phase input dispatch and declared accumulate/reducer operations, so callbacks and `trace.jsonl` observe the same typed runtime facts.

**Architecture:** Keep the change local to engine runtime boundaries. `InputDispatchEvent` belongs where phase-local inputs are sliced from the blackboard and handed to a phase; `BlackboardReduceEvent` belongs where declared iterate/accumulate merges update the blackboard. Existing event schema, default callback recognition, and JSONL serialization already exist, so callback modules should stay untouched unless a fresh RED proves drift.

**Tech Stack:** Python 3.13 in this worktree, pytest, Pydantic v2 typed callback events, LangGraph compiled graph runtime, existing `WorkflowState` / `StateMapper` helpers.

---

## Phase 0: Grounding, File Lock, And RED Recheck

- [ ] Read the approved requirements and SSOT pointers before editing.
  _Requirements: WS-E4-runtime-edge-events §2 / §12; task-spec-standard IR2 / IR5._
  Required files:
  - `.kiro/specs/engine-mvp1/requirements-ws-e4-runtime-edge-events.md`
  - `docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md`
  - `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`

- [ ] Report the current live grounding before implementation.
  _Requirements: WS-E4-runtime-edge-events §3 / §5._
  Include the current behavior of:
  - phase wrapping / input slicing in `PhaseWrapper.wrap(...)`
  - callbacks passed through `assemble_graph(...)`
  - iterate wrappers in `_build_batch_iterate_phase(...)` and `_build_loop_iterate_phase(...)`
  - current absence of file lazy injection path on this base
  - base/stacked state: `34ee40f1`, not stacked on WS-E1-io

- [ ] Re-run the approved RED suite before editing production code.
  _Requirements: TDD RED evidence; WS-E4-runtime-edge-events §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py -q`
  Expected now: `4 failed, 1 xfailed`.
  Expected failure shape:
  - serial graph succeeds but subscriber has no `InputDispatchEvent`
  - batch iterate succeeds but branch dispatch events are empty
  - loop accumulate succeeds but `BlackboardReduceEvent` events are empty
  - e2e `run_skill` succeeds but subscriber and `trace.jsonl` contain no `input_dispatch`
  - file injection test remains xfailed because WS-E1-io has not landed

- [ ] Confirm file lock before implementation.
  _Requirements: WS-E4-runtime-edge-events §3 / §9._
  Verification command:
  `git status --short -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/runtime/state_mapper.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/callbacks/base.py apps/studio packages/graph-agent-gateway`
  Expected before implementation: only approved requirements/RED/task/prompt docs may be dirty; callback modules, Studio, and gateway must have no production diff.

## Phase 1: Serial Phase Input Dispatch

- [ ] Implement the minimal runtime path that emits `InputDispatchEvent` before each normal phase body receives its sliced input.
  _Requirements: WS-E4-runtime-edge-events §5 / §6; approved RED serial test._
  Contract:
  - event class: existing `graph_agent.callbacks.events.InputDispatchEvent`
  - emit path: existing generic callbacks sink via `_safe_emit_event`
  - `to_phase`: current phase id
  - `from_phase`: `None` for graph input dispatch, otherwise the upstream phase whose output provided the dispatched data when determinable from current runtime state
  - `dispatched_keys`: keys in the actual phase-local input slice
  - `changed_keys`: same engine operation keys for the dispatch
  - `blackboard_snapshot`: dispatch-time business blackboard snapshot after any input preparation and before phase execution
  - `branch_index`: `None` for non-iterate execution
  Do not add Studio-only fields or new callback hooks.

- [ ] Verify the serial dispatch RED turns GREEN.
  _Requirements: approved RED serial test._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py::test_serial_graph_emits_input_dispatch_for_each_phase_before_execution -q`
  Expected after implementation: pass.

- [ ] Verify the e2e trace RED sees the same dispatch events through subscriber and `trace.jsonl`.
  _Requirements: WS-E4-runtime-edge-events §5 / §6._
  Verification command:
  `uv run pytest packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py::test_runtime_edge_events_reach_event_subscriber_and_trace_jsonl -q`
  Expected after implementation: pass.

## Phase 2: Iterate Branch Dispatch

- [ ] Extend dispatch emission so declared batch/iterate executions emit one `InputDispatchEvent` per actual branch or round.
  _Requirements: WS-E4-runtime-edge-events §5 / §6; approved RED branch test._
  Contract:
  - each item execution gets a dispatch event
  - branch numbering is stable and 1-based, matching existing `iter1`, `iter2`, ... runtime convention
  - `branch_index` values for the approved batch test are `[1, 2, 3]`
  - `dispatched_keys` and `changed_keys` describe the branch-local input keys, not the whole original list
  - no event may be emitted only for the last branch

- [ ] Verify branch dispatch GREEN without regressing serial dispatch.
  _Requirements: approved RED serial + branch tests._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py::test_serial_graph_emits_input_dispatch_for_each_phase_before_execution packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py::test_batch_iterate_emits_input_dispatch_for_each_branch_with_stable_branch_index -q`
  Expected after implementation: both tests pass.

## Phase 3: Declared Blackboard Reduce Events

- [ ] Emit `BlackboardReduceEvent` after each declared loop accumulate merge updates the blackboard.
  _Requirements: WS-E4-runtime-edge-events §5 / §6; observability OB4/OB5; approved RED reduce test._
  Contract:
  - event class: existing `graph_agent.callbacks.events.BlackboardReduceEvent`
  - `to_phase`: phase where the declared accumulate operation occurs
  - `from_phase`: the same upstream source used by this runtime operation if known; `None` is acceptable when no upstream phase is available for graph input/loop-local operations
  - `reducer`: the declared accumulate merge name such as `append`
  - `changed_keys`: the accumulator key changed by the reducer, such as `["collected"]`
  - `blackboard_snapshot`: business blackboard snapshot after the merge
  - do not compute or add authoritative before/after reducer diff

- [ ] Verify reduce RED turns GREEN.
  _Requirements: approved RED reduce test._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py::test_loop_accumulate_emits_blackboard_reduce_after_each_declared_merge -q`
  Expected after implementation: pass.

- [ ] Verify all approved WS-E4 runtime RED tests.
  _Requirements: hard exit for approved RED._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py -q`
  Expected after implementation: `4 passed, 1 xfailed` while WS-E1-io remains absent.

## Phase 4: Dependency Gate And Scope Hygiene

- [ ] Keep `InputFileInjectedEvent` dependency-gated.
  _Requirements: WS-E4-runtime-edge-events §5 / §6 / §7 / §9._
  Current base has no WS-E1-io file lazy injection path. Do not implement file import syntax, read_file wiring, artifact storage, runner/io/storage changes, or `InputFileInjectedEvent` production emission in this task. The approved file-injection test must remain xfailed until WS-E1-io lands.

- [ ] Confirm callback schema and sink modules were not changed.
  _Requirements: WS-E4-runtime-edge-events §3 / §9._
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/callbacks/base.py`
  Expected: no diff.

- [ ] Confirm Studio, gateway, runner/io/read_file/artifact/checkpoint/error contract files were not changed.
  _Requirements: WS-E4-runtime-edge-events §3 / §9._
  Verification command:
  `git diff -- apps/studio packages/graph-agent-gateway packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/core/result.py`
  Expected: no diff.

## Phase 5: Regression Verification

- [ ] Run the approved runtime edge suite to GREEN.
  _Requirements: WS-E4-runtime-edge-events §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py -q`
  Expected while WS-E1-io remains absent: `4 passed, 1 xfailed`.

- [ ] Run iterate and state mapper regression tests.
  _Requirements: no regression in graph-exec / iterate behavior._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/runtime/test_state_mapper.py -q`
  Expected: all selected tests pass.

- [ ] Run callback emission regression tests.
  _Requirements: callback/event sink compatibility._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_emit.py packages/graph-agent/tests/callbacks/test_on_event_characterization.py -q`
  Expected: all selected tests pass.

- [ ] Run the focused create-agent smoke regression touched by `graph_assembler.py` history.
  _Requirements: no create_agent runtime regression._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py -q`
  Expected: all selected tests pass.

- [ ] Run lint and diff hygiene.
  _Requirements: implementation quality gate._
  Verification commands:
  - `uv run ruff check packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/runtime/state_mapper.py packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py`
  - `git diff --check`
  Expected: both commands pass with no errors.

- [ ] Restore `uv.lock` if `uv run` dirtied it.
  _Requirements: no dependency changes._
  Verification command:
  `git status --short -- uv.lock`
  If dirty and no approved dependency change exists: `git restore -- uv.lock`

## Phase 6: Baseline Handoff After GREEN

- [ ] Do not update baseline before implementation is GREEN and Codex review accepts hard exit.
  _Requirements: task-spec-standard IR6; WS-E4-runtime-edge-events §10._
  After GREEN, report the exact landed runtime behavior so Codex can truthfully update:
  - `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md`
  - graph-exec baseline status; if `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md` is absent, report that instead of inventing one.

## Hard Exit Checklist

- [ ] Approved WS-E4 runtime RED suite is GREEN as `4 passed, 1 xfailed` while WS-E1-io is absent.
- [ ] Serial graph emits `InputDispatchEvent` before each phase execution.
- [ ] `InputDispatchEvent` reaches both generic event subscriber and `trace.jsonl`.
- [ ] Batch/iterate branches each emit one `InputDispatchEvent` with stable 1-based `branch_index`.
- [ ] Declared loop accumulate emits `BlackboardReduceEvent` after each merge.
- [ ] `BlackboardReduceEvent` reports reducer name, changed keys, and post-merge blackboard snapshot without authoritative before/after diff.
- [ ] `InputFileInjectedEvent` remains dependency-gated; no file lazy injection/read_file/artifact/storage/runner semantics were implemented.
- [ ] Callback schema/sink/default callback modules have no diff unless Codex explicitly expanded owns after a proved drift.
- [ ] Studio, gateway, runner/io/read_file/artifact/checkpoint/error-contract files have no diff.
- [ ] Focused iterate/state/callback/create-agent regression commands pass.
- [ ] `uv.lock` is clean.
- [ ] `graph_assembler.py` vs WS-E1-io coordination status is reported with base/stacked state.

## Gemini Report Format

When finished, report:

1. Files changed.
2. The exact tests run and pass/fail output summary.
3. Where `InputDispatchEvent` is emitted, including how `from_phase`, `dispatched_keys`, `changed_keys`, `blackboard_snapshot`, and `branch_index` are derived.
4. Where `BlackboardReduceEvent` is emitted, including reducer name and snapshot timing.
5. Confirmation that `InputFileInjectedEvent` stayed dependency-gated because WS-E1-io is not present on this base.
6. Confirmation that forbidden files have no diff, especially `apps/studio/**`, `packages/graph-agent-gateway/**`, callback modules, runner/io/read_file/artifact/checkpoint/error-contract files.
7. The `graph_assembler.py` coordination status: base commit, whether stacked on WS-E1-io, and any remaining merge risk.
8. Any remaining risk or hard-exit item not satisfied.
