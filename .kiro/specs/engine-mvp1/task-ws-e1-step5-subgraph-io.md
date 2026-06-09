---
ws_id: WS-E1-step5-subgraph-io
task_type: implementation
implementer: Gemini
author: Codex
status: implemented
created: 2026-06-09
requirements: .kiro/specs/engine-mvp1/requirements-ws-e1-step5-subgraph-io.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_workstream: docs/engine/mvp1/_impl/WS-E1-create-agent-core.md
contract_gate: "passed by PM/user on 2026-06-09; approved RED result is 3 failed, 1 passed"
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md §四 WS-E1 Step 5
  - docs/engine/mvp1/_impl/WS-E1-create-agent-core.md §5/§6/§7/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md §2/§5
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md §2.4.3/§2.10.2
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md subgraph domain
approved_red_tests:
  - packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py
  - packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time
  - packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_output_mismatch_is_rejected_at_compile_time
  - packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py::test_corrupted_skill_raises_dedicated_located_code[subgraph-io-mismatch]
red_result: "uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q -> 3 failed, 1 passed"
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e1-step5-subgraph-io.md
  - .kiro/specs/engine-mvp1/task-ws-e1-step5-subgraph-io.md
  - .kiro/specs/engine-mvp1/gemini-prompt-ws-e1-step5-subgraph-io.md
  - packages/graph-agent/src/graph_agent/core/loader.py
  - packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py
  - packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py
  - packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py
  - packages/graph-agent/spec/features.yaml
  - packages/graph-agent/tests/fixtures/round28/valid_features_primary_owners.yaml
  - packages/graph-agent/tests/fixtures/round28/valid_features_runtime_compat.yaml
forbidden_files:
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/src/graph_agent/runtime/state_mapper.py
  - packages/graph-agent/src/graph_agent/core/runner.py
  - packages/graph-agent/src/graph_agent/io/**
  - packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
  - packages/graph-agent/src/graph_agent/callbacks/events.py
  - packages/graph-agent/src/graph_agent/callbacks/emit.py
  - packages/graph-agent/src/graph_agent/middleware/**
  - packages/graph-agent/src/graph_agent/core/checkpointer.py
  - packages/graph-agent/src/graph_agent/core/state.py
  - apps/studio/**
  - packages/graph-agent-gateway/**
---

# WS-E1 Step5 Subgraph IO Relaxation Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Do not weaken them. Implement the smallest GREEN change, then stop for review.

**Goal:** Relax SUBGRAPH input mirror validation for MVP1 while keeping output validation strict.

**Architecture:** Keep the implementation local to `packages/graph-agent/src/graph_agent/core/loader.py`, specifically `_validate_subgraph_io_contracts`. Existing runtime grounding in `_wrap_phase_runtime_node`, `_build_subgraph_node`, and `StateMapper` already provides parent phase slicing and child graph slicing; treat those files as read-only unless a fresh RED failure proves this assumption wrong, in which case stop and ask PM to expand scope.

**Tech Stack:** Python 3.12, pytest, existing graph-agent `SkillLoader` / `compile_skill` / `assemble_graph` path, existing `[F-v3-subgraph-io-mismatch]` payload code.

---

## Phase 0: Grounding And Scope Lock

- [ ] Read the requirements file and SSOT pointers before editing.
  _Requirements: WS-E1-step5-subgraph-io._
  Verify by reporting the current live symbols and behavior:
  - `packages/graph-agent/src/graph_agent/core/loader.py`: `_validate_subgraph_io_contracts` currently compiles the child graph and compares both `inputs` and `outputs`.
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`: `_wrap_phase_runtime_node` and `_build_subgraph_node` are read-only grounding for parent phase slicing and child invocation.
  - `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`: `StateMapper.build_phase_input` / `wrap_phase_output` are read-only grounding for blackboard slicing and output merge.
  - `packages/graph-agent/spec/features.yaml`: live traceability now points to the MVP1 RED node id, not the removed MVP0 rejection node id.

- [ ] Confirm the working tree contains only the approved Step5 RED/spec input before implementing.
  _Requirements: file ownership / forbidden files._
  Verification command:
  `git status --short`
  Expected before implementation: Step5 requirements/RED/test/metadata files may be dirty; no production implementation file except `loader.py` should be dirty yet; no `uv.lock` diff.

- [ ] Re-run the approved RED suite before implementing and keep the failure shape unchanged.
  _Requirements: TDD RED evidence._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q`
  Expected now: `3 failed, 1 passed`.
  Expected failure causes:
  - parent input superset fails at `loader._validate_subgraph_io_contracts` with `inputs do not match`.
  - different input sets fail at `loader._validate_subgraph_io_contracts` with `inputs do not match`.
  - runtime relaxed-input case fails during compile for the same inputs mirror reason.
  - output mismatch still passes because it remains fatal with `[F-v3-subgraph-io-mismatch]`.

- [ ] Re-run the approved legacy-drift checks before implementing.
  _Requirements: old MVP0 tests converted, outputs still strict._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_output_mismatch_is_rejected_at_compile_time -q`
  Expected now: `1 failed, 1 passed`; the input mismatch test is the RED, and the output mismatch test remains GREEN.

## Phase 1: Relax Only SUBGRAPH Inputs Mirror Validation

- [ ] Change `_validate_subgraph_io_contracts` so it no longer rejects mismatched `io.inputs` between parent `SUBGRAPH.md` and child `GRAPH.md`.
  _Requirements: inputs relaxation / MVP1 design is SSOT._
  Required behavior from approved RED:
  - Parent `SUBGRAPH.md io.inputs` may be a superset of child `GRAPH.md io.inputs`.
  - Parent and child `io.inputs` may be different field sets at compile time.
  - Loader must still recursively compile the child skill through the resolver and must not skip existing resolver, recursion, or child-load behavior.
  - Old MVP0 tests asserting input mirror rejection must stay converted to MVP1 RED/GREEN form.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py::test_subgraph_input_mismatch_compiles_without_mirror_contract packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time -q`
  Expected after implementation: all selected tests pass.

- [ ] Keep `[F-v3-subgraph-io-mismatch]` for output mismatches only.
  _Requirements: outputs remain strict._
  Required behavior from approved RED:
  - Parent `SUBGRAPH.md io.outputs` and child `GRAPH.md io.outputs` still must match exactly.
  - The fatal payload code remains `[F-v3-subgraph-io-mismatch]`.
  - The failure message should make it clear the mismatch is on `outputs`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py::test_subgraph_output_mismatch_still_fatals_with_existing_code packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_output_mismatch_is_rejected_at_compile_time 'packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py::test_corrupted_skill_raises_dedicated_located_code[subgraph-io-mismatch]' -q`
  Expected after implementation: all selected tests pass.

## Phase 2: Verify Runtime Blackboard Slicing Still Holds

- [ ] Prove the child graph runs from its own `io.inputs` slice when parent `SUBGRAPH.md io.inputs` is relaxed.
  _Requirements: subgraph behaves like an ordinary blackboard-sliced node._
  Required behavior from approved RED:
  - The parent blackboard may include fields that are declared by the parent subgraph phase but not by the child graph.
  - The child LOGIC action sees only the child graph's declared input key.
  - The child output is merged back to the parent phase output.
  If this test fails after Phase 1 for a runtime reason outside `loader.py`, stop and report the exact failure before touching `graph_assembler.py` or `state_mapper.py`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py::test_subgraph_runtime_slices_parent_blackboard_with_relaxed_inputs -q`
  Expected after implementation: test passes.

## Phase 3: Traceability And MVP0 Drift Cleanup

- [ ] Confirm live traceability references the new MVP1 node id.
  _Requirements: contract gate traceability fix._
  Verification command:
  `uv run pytest --collect-only packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time -q`
  Expected: `1 test collected`.

- [ ] Confirm the old MVP0 rejection node id is gone from live test/manifest surfaces.
  _Requirements: no stale MVP0 assertion._
  Verification command:
  `rg "test_subgraph_io_input_mismatch_is_rejected_at_compile_time" packages/graph-agent/spec/features.yaml packages/graph-agent/tests -g "*.py" -g "*.yaml"`
  Expected: no output and exit code 1. The old name may remain only in historical/narrative docs such as this requirements file or MVP0 documentation; do not modify MVP0 history docs for this WS.

- [ ] Run round28 manifest checks because `features.yaml` and round28 fixtures changed.
  _Requirements: traceability fixtures stay valid._
  Verification command:
  `uv run pytest packages/graph-agent/tests/test_round28_contract_manifests.py -q`
  Expected after implementation: all tests pass.

## Phase 4: Full Verification And Scope Audit

- [ ] Run the approved Step5 contract suite to GREEN.
  _Requirements: requirements §8 hard exit._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_output_mismatch_is_rejected_at_compile_time 'packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py::test_corrupted_skill_raises_dedicated_located_code[subgraph-io-mismatch]' -q`
  Expected after implementation: all selected tests pass.

- [ ] Run Step3/Step4 WS-E1 regression coverage.
  _Requirements: no regression in logic runtime, iterate runtime, and purity contracts._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q`
  Expected after implementation: all tests pass.

- [ ] Run the standing create-agent / purity / diagnostics baseline.
  _Requirements: no regression outside Step5._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_purity_le2.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q`
  Expected after implementation: all tests pass.

- [ ] Run type checking for the touched production file.
  _Requirements: implementation quality gate._
  Verification command:
  `uv run mypy packages/graph-agent/src/graph_agent/core/loader.py`
  Expected after implementation: `Success: no issues found`.

- [ ] Confirm forbidden files are untouched.
  _Requirements: IR1 / IR7 scope lock._
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/runtime/state_mapper.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/middleware packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py`
  Expected: no diff.

- [ ] Confirm Studio, gateway, and dependency lock are untouched.
  _Requirements: forbidden files / no dependency change._
  Verification command:
  `git status --short -- apps/studio packages/graph-agent-gateway uv.lock`
  Expected: no diff from this WS. If `uv.lock` was touched by `uv run` and no dependency changed, restore it.

- [ ] Run diff hygiene.
  _Requirements: implementation quality gate._
  Verification command:
  `git diff --check -- packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py packages/graph-agent/spec/features.yaml packages/graph-agent/tests/fixtures/round28/valid_features_primary_owners.yaml packages/graph-agent/tests/fixtures/round28/valid_features_runtime_compat.yaml .kiro/specs/engine-mvp1/requirements-ws-e1-step5-subgraph-io.md .kiro/specs/engine-mvp1/task-ws-e1-step5-subgraph-io.md .kiro/specs/engine-mvp1/gemini-prompt-ws-e1-step5-subgraph-io.md`
  Expected: no output.

## Phase 5: Baseline Handoff After GREEN

- [ ] Do not update baseline before implementation is GREEN and Codex review accepts the hard exit.
  _Requirements: IR6 / requirements §10._
  After GREEN, report the exact landed behavior so Codex can truthfully update:
  - `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`: subgraph inputs are relaxed; outputs remain strict.
  - `docs/engine/mvp1/01-contract/02-skill-syntax/baseline.md`: SUBGRAPH inputs no longer require parent-child mirror equality.
  - `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`: update only if the implementation truly changes the meaning/text of `[F-v3-subgraph-io-mismatch]`.
  - `docs/engine/mvp1/_impl/IMPL_PLAN.md`: only update Step5 progress status if PM asks for progress-panel maintenance.

## Hard Exit Checklist

- [ ] Approved Step5 RED suite is GREEN.
- [ ] Parent/child `io.inputs` mismatch no longer fails compile.
- [ ] Parent `io.inputs` superset over child `io.inputs` compiles.
- [ ] Runtime relaxed-input case proves child action only sees child-declared input keys.
- [ ] Parent/child `io.outputs` mismatch still fails compile.
- [ ] Output mismatch still uses `[F-v3-subgraph-io-mismatch]` and message mentions `outputs`.
- [ ] Old MVP0 input-mismatch rejection test is not restored.
- [ ] `features.yaml` and round28 fixtures point to the new MVP1 node id.
- [ ] Step3 logic and Step4 iterate regressions remain GREEN.
- [ ] No file import lazy, artifact, callback event emit, runner/io/read_file/storage, middleware, checkpoint/state, Studio, or gateway work was implemented.
- [ ] `graph_assembler.py` and `state_mapper.py` remain untouched unless PM explicitly expanded scope after a runtime failure.
- [ ] `uv.lock` is clean or restored.
- [ ] `git diff --check` is clean.

## Gemini Report Format

When finished, report:

1. Files changed.
2. The exact verification commands run and pass/fail output summary.
3. Confirmation that forbidden engine files, `apps/studio/**`, `packages/graph-agent-gateway/**`, and `uv.lock` have no WS-E1 Step5 diff.
4. The final subgraph IO behavior: inputs compile behavior, runtime slicing behavior, outputs mismatch behavior.
5. Whether baseline docs were intentionally left for Codex/PM handoff or updated by explicit instruction.
6. Any hard-exit item not satisfied and the reason you stopped instead of expanding scope.

## Completion Record

Implemented on 2026-06-09. The minimal production change is local to
`packages/graph-agent/src/graph_agent/core/loader.py:_validate_subgraph_io_contracts`:
parent/child `io.inputs` are no longer mirror-compared, while parent/child
`io.outputs` remain strictly equal and still raise `[F-v3-subgraph-io-mismatch]`
with an outputs-specific message.

Verified:
- Step5 contract suite passed.
- Round14 core and compiler e2e coverage passed.
- Step3/Step4 regression coverage passed.
- Create-agent / purity / diagnostics baseline passed.
- `mypy` on `loader.py` passed.
- Forbidden engine files, Studio, gateway, and `uv.lock` had no Step5 diff.

Known non-WS blocker: full `test_round28_contract_manifests.py` still has
pre-existing infra/docs path/hash failures and was not fixed in WS-E1 Step5.
