---
ws_id: WS-E1-step3-logic-runtime
task_type: implementation
implementer: Gemini
author: Codex
status: ready-for-gemini
created: 2026-06-08
requirements: .kiro/specs/engine-mvp1/requirements-ws-e1-step3-logic-runtime.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
contract_gate: "passed by PM/user on 2026-06-08; approved RED result is 8 failed, 23 passed"
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md §四 WS-E1 Step 3
  - docs/engine/mvp1/_impl/WS-E1-create-agent-core.md §5/§6/§7/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md §2/§3/§5/§8
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md §2.3
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md §2.1/§2.3/§4
approved_red_tests:
  - packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py
  - packages/graph-agent/tests/core/test_context_facade_logic_action.py
  - packages/graph-agent/tests/core/test_action_registry_v030.py
  - packages/graph-agent/tests/core/validators/test_purity_le2.py
red_result: "uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q -> 8 failed, 23 passed"
owns_files:
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py
  - packages/graph-agent/tests/core/test_context_facade_logic_action.py
  - packages/graph-agent/tests/core/test_action_registry_v030.py
forbidden_files:
  - packages/graph-agent/src/graph_agent/core/loader.py
  - packages/graph-agent/src/graph_agent/core/manifest.py
  - packages/graph-agent/src/graph_agent/core/purity.py
  - packages/graph-agent/src/graph_agent/core/error_registry.py
  - packages/graph-agent/src/graph_agent/cognitive/context_facade.py
  - packages/graph-agent/src/graph_agent/core/checkpointer.py
  - packages/graph-agent/src/graph_agent/core/state.py
  - packages/graph-agent/src/graph_agent/middleware/tracing.py
  - packages/graph-agent/src/graph_agent/middleware/tool_error.py
  - packages/graph-agent/src/graph_agent/middleware/loop_detection.py
  - packages/graph-agent/src/graph_agent/middleware/nudge_injector.py
  - apps/studio/**
  - packages/graph-agent-gateway/**
---

# WS-E1 Step3 LOGIC Runtime Contract Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Do not weaken them. Implement task-by-task until the approved RED suite is GREEN.

**Goal:** Convert LOGIC runtime from mutable `Context` facade + data diff writes to the MVP1 pure action contract: each action receives a plain dict input slice and the only blackboard writes come from returned dicts.

**Architecture:** Keep the change local to `packages/graph-agent/src/graph_agent/core/graph_assembler.py`, specifically the LOGIC runtime path in `_build_logic_node`. `PhaseWrapper` / `StateMapper` already slice `io.inputs` and merge declared outputs; this task should make `_build_logic_node` pass plain dict snapshots through the action chain, validate returned dicts, and stop treating local mutation as an implicit output channel. Do not edit loader, purity, iterate, subgraph io, middleware, checkpoint, Studio, or gateway files.

**Tech Stack:** Python 3.12, pytest, existing graph-agent compile/assemble/invoke path, existing `GraphAgentFatalError` payload codes.

---

## Phase 0: Grounding And Scope Lock

- [ ] Read the requirements file and SSOT pointers before editing.
  _Requirements: WS-E1-step3-logic-runtime._
  Verify by reporting the current live symbols and behavior:
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`: `_build_logic_node`, `_validate_logic_update_keys`, `_dict_delta`, `phase_inputs_from_state`.
  - `packages/graph-agent/src/graph_agent/core/loader.py`: `_validate_action_signature` is read-only grounding only. It currently requires the first parameter name to be `context` or `ctx`; do not edit loader in this WS.
  - `packages/graph-agent/src/graph_agent/cognitive/context_facade.py`: read-only grounding for the old facade; do not edit it.

- [ ] Confirm the working tree contains only the approved RED/test/spec input before implementing.
  _Requirements: file ownership / forbidden files._
  Verification command:
  `git status --short -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/src/graph_agent/core/purity.py packages/graph-agent/src/graph_agent/core/manifest.py packages/graph-agent/src/graph_agent/cognitive/context_facade.py apps/studio packages/graph-agent-gateway uv.lock`
  Expected before implementation: no diff in the listed production/forbidden files and no `uv.lock` diff.

- [ ] Re-run the approved RED suite before implementing and keep the failure shape unchanged.
  _Requirements: TDD RED evidence._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q`
  Expected now: `8 failed, 23 passed`.
  Expected failure causes:
  - `Context:hello` instead of `dict:hello`.
  - action 2 reads `missing` instead of the previous action's returned `normalized`.
  - `context.set`, `context.update`, item assignment, and `setdefault` still write to business data.
  - old Context facade regression now expects `dict:scored 1 segments`.
  - action-registry mutation regression sees `foo == 99` instead of preserving `foo == 1`.

## Phase 1: Replace Context Facade Execution With Plain Dict Snapshots

- [ ] Change `_build_logic_node` so each action is called with a plain dict, not `Context`.
  _Requirements: pure-return runtime / input view._
  Required behavior from approved RED:
  - `type(context).__name__` inside a LOGIC action should be `dict`.
  - Existing fixture action parameter names may remain `context` because loader currently accepts `context` / `ctx` names only; this task changes the runtime object, not the loader signature rule.
  - If you believe the parameter-name cleanup to `inputs` requires `loader.py`, stop and ask PM to expand owns. Do not edit `loader.py` in this WS.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py::test_logic_action_receives_plain_dict_inputs_and_writes_only_returned_output packages/graph-agent/tests/core/test_context_facade_logic_action.py::test_logic_action_receives_plain_dict_not_context_facade -q`
  Expected after implementation: both tests pass.

- [ ] Remove the old implicit mutation diff path from `_build_logic_node`.
  _Requirements: Context mutation退场._
  Required behavior from approved RED:
  - The runtime must not create `Context(data, ...)` for LOGIC action calls.
  - Local mutation APIs on the passed object must not become blackboard writes unless the action explicitly returns those keys in its result dict.
  - `_dict_delta` may remain in the file because subgraph/subagent paths still use it.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py::test_context_style_mutation_is_not_a_blackboard_output_channel packages/graph-agent/tests/core/test_action_registry_v030.py::test_context_style_mutation_is_not_a_logic_output_channel -q`
  Expected after implementation: all mutation-channel tests pass.

## Phase 2: Preserve Multi-Action Returned-Output Chaining

- [ ] Make later actions see earlier actions' returned fields as input increments.
  _Requirements: multi-action chain explicit return propagation._
  Required behavior from approved RED:
  - For action order `normalize` then `score`, `normalize` returns `{"normalized": "HELLO"}`.
  - `score` receives a plain dict where `context.get("normalized") == "HELLO"`.
  - The final business output contains `report == "HELLO"` and phase output for `score` is `{"report": "HELLO"}`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py::test_logic_action_chain_reads_previous_returned_outputs_as_input_increment -q`
  Expected after implementation: test passes.

- [ ] Preserve phase input slicing through the existing wrapper.
  _Requirements: only declared `io.inputs` visible._
  Required behavior from approved RED:
  - Root input `root_secret` and upstream phase output `upstream_secret` are not visible to a LOGIC phase that declares only `public`.
  - The action returns `"public"` when it joins sorted input keys.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py::test_logic_action_sees_only_declared_phase_inputs -q`
  Expected after implementation: test passes.

## Phase 3: Preserve Existing LOGIC Error Contracts

- [ ] Keep undeclared returned output keys on the existing runtime FATAL path.
  _Requirements: output boundary not relaxed._
  Required behavior from approved RED:
  - Returning `{"missing": ...}` from a LOGIC action whose `io.outputs.properties` contains only `report` raises `GraphAgentFatalError`.
  - `payload.code == "[F-v3-logic-output-field-undeclared]"`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py::test_undeclared_return_key_still_uses_logic_output_field_error packages/graph-agent/tests/core/test_action_registry_v030.py::test_runtime_dynamic_return_key_must_use_v030_output_field_error -q`
  Expected after implementation: both tests pass.

- [ ] Keep non-dict returns on the existing runtime FATAL path.
  _Requirements: non-dict return contract._
  Required behavior from approved RED:
  - Returning `["not", "a", "dict"]` raises `GraphAgentFatalError`.
  - `payload.code == "[F-v3-logic-action-return-invalid]"`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py::test_non_dict_return_still_uses_logic_action_return_invalid_error packages/graph-agent/tests/core/test_action_registry_v030.py::test_action_returning_non_dict_is_runtime_fatal -q`
  Expected after implementation: both tests pass.

## Phase 4: Full Verification And Scope Audit

- [ ] Run the approved WS-E1 Step3 RED suite to GREEN.
  _Requirements: requirements §8 hard exit._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q`
  Expected after implementation: all tests pass.

- [ ] Run the baseline regression suite named in the requirements.
  _Requirements: no regression / WS-E6 purity remains green._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_purity_le2.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q`
  Expected after implementation: all tests pass.

- [ ] Run type checking for the touched production file.
  _Requirements: requirements §8._
  Verification command:
  `uv run mypy packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  Expected after implementation: `Success: no issues found`.

- [ ] Confirm forbidden files are untouched.
  _Requirements: IR1 / IR7 scope lock._
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/src/graph_agent/core/manifest.py packages/graph-agent/src/graph_agent/core/purity.py packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/cognitive/context_facade.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/middleware/nudge_injector.py`
  Expected: no diff.

- [ ] Confirm Studio, gateway, and dependency lock are untouched.
  _Requirements: forbidden files / no dependency change._
  Verification command:
  `git status --short -- apps/studio packages/graph-agent-gateway uv.lock`
  Expected: no diff from this WS. If `uv.lock` was touched by `uv run` and no dependency changed, restore it.

- [ ] Run diff hygiene.
  _Requirements: implementation quality gate._
  Verification command:
  `git diff --check -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py`
  Expected: no output.

## Phase 5: Baseline Handoff After GREEN

- [ ] Do not update baseline before implementation is GREEN and Codex review accepts the hard exit.
  _Requirements: IR6 / requirements §10._
  After GREEN, report the exact landed behavior so Codex can truthfully update:
  - `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`: LOGIC runtime no longer uses mutable Context diff as a write channel.
  - `docs/engine/mvp1/01-contract/02-skill-syntax/baseline.md`: action runtime receives plain dict snapshots while loader signature naming may still be a separate live drift if unchanged.
  - `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`: no update unless the implementation truly changes error-code or purity behavior.
  - `docs/engine/mvp1/_impl/IMPL_PLAN.md`: only update Step3 completion status if PM asks for progress-panel maintenance.

## Hard Exit Checklist

- [ ] Approved RED suite is GREEN.
- [ ] LOGIC action runtime object is a plain dict.
- [ ] LOGIC action writes are sourced only from returned dicts.
- [ ] `context.set`, `context.update`, item assignment, and `setdefault` do not write implicitly to blackboard.
- [ ] Later actions can read earlier actions' returned fields.
- [ ] LOGIC input slicing remains limited to declared `io.inputs`.
- [ ] Undeclared returned output keys still raise `[F-v3-logic-output-field-undeclared]`.
- [ ] Non-dict returns still raise `[F-v3-logic-action-return-invalid]`.
- [ ] WS-E6 purity regression suite remains GREEN.
- [ ] No iterate, subgraph io, middleware, checkpoint, Studio, gateway, loader, manifest, purity, or error-registry work was implemented.
- [ ] `uv.lock` is clean or restored.
- [ ] `git diff --check` is clean.

## Gemini Report Format

When finished, report:

1. Files changed.
2. The exact verification commands run and pass/fail output summary.
3. Confirmation that forbidden engine files, `apps/studio/**`, `packages/graph-agent-gateway/**`, and `uv.lock` have no WS-E1 Step3 diff.
4. The final LOGIC runtime behavior: action input object, action-chain propagation, mutation-channel behavior, output validation behavior.
5. Any hard-exit item not satisfied and the reason you stopped instead of expanding scope.
