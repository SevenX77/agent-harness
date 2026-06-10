---
ws_id: WS-E7-golden-resume
task_type: implementation
implementer: Gemini
author: Codex
status: drafted
created: 2026-06-10
requirements: .kiro/specs/engine-mvp1/requirements-ws-e7-golden-resume.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md S5/S6
contract_gate: "passed by Codex PM on 2026-06-10; approved RED result is 12 failed, all on missing public Engine APIs"
spec_ssot:
  - docs/engine/mvp1/03-api-contract/mvp1-alignment.md §3.1/§3.2/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md §2/§6/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment.md §2/§3/§6/§8
  - docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/baseline.md
  - docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md §2.2/§3/§8
approved_red_tests:
  - packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py
  - packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py
  - packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py
red_result: "uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py -q -> 12 failed; all failures are graph_agent.resume_skill / graph_agent.evaluate_golden_baseline missing public callables"
fixture_self_check: "temporary helper run verified run_skill can execute the deterministic resume fixture and locate a draft-before-final checkpoint"
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e7-golden-resume.md
  - .kiro/specs/engine-mvp1/task-ws-e7-golden-resume.md
  - .kiro/specs/engine-mvp1/gemini-prompt-ws-e7-golden-resume.md
  - packages/graph-agent/src/graph_agent/core/runner.py
  - packages/graph-agent/src/graph_agent/core/checkpointer.py
  - packages/graph-agent/src/graph_agent/core/result.py
  - packages/graph-agent/src/graph_agent/core/_predict_internal/**
  - packages/graph-agent/src/graph_agent/__init__.py
  - packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py
  - packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py
  - packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py
forbidden_files:
  - apps/studio/**
  - packages/graph-agent-gateway/**
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/src/graph_agent/core/loader.py
  - packages/graph-agent/src/graph_agent/io/**
  - packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
  - packages/graph-agent/src/graph_agent/callbacks/events.py
  - packages/graph-agent/src/graph_agent/callbacks/emit.py
  - packages/graph-agent/src/graph_agent/middleware/**
---

# WS-E7 Golden / Resume Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Do not weaken them. Implement the smallest GREEN change that satisfies the approved RED suite, then run the listed regressions.

**Goal:** Add Engine process APIs for checkpoint resume and `.workspace/golden` evaluation: `resume_skill(...) -> RunResult` and `evaluate_golden_baseline(...) -> dict/report`.

**Architecture:** Keep Studio and gateway out of this WS. `runner.py` owns public entrypoints and artifact writing, `checkpointer.py` may own checkpoint selection helpers, `result.py` may hold typed report models if needed, `__init__.py` exports the public API, and small helper code may live under `core/_predict_internal/**` if it prevents `runner.py` from growing. All workspace reads/writes must stay under caller-provided absolute `workspace_dir`.

**Tech Stack:** Python 3.13 in this worktree, pytest, LangGraph checkpointer/history/update-state semantics, existing `run_skill` / `compile_skill` / `assemble_graph`, Pydantic `RunResult`.

---

## Phase 0: Grounding And RED Lock

- [ ] Read the requirements and SSOT before editing production code.
  _Requirements: WS-E7.grounding / IR5._
  Report current live facts:
  - `graph_agent.__init__` exports `run_skill` and `predict_skill`, but not `resume_skill` or `evaluate_golden_baseline`.
  - `runner.py` has `_validate_workspace_dir`, `run_skill`, `predict_skill`, `_write_workflow_result_artifacts`, and V0.3 graph invoke/checkpointer wiring.
  - `checkpointer.py` has process-wide checkpointer resolution/reset but no resume selector helper.
  - `03-checkpoint/baseline.md` says WS-E5 namespace checkpointing is live, but full resume product is not.
  - `06-golden-eval/baseline.md` says engine does not read `.workspace/golden` and has no `evaluate_golden_baseline`.

- [ ] Re-run approved RED before implementation.
  _Requirements: approved RED is the contract._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py -q`
  Expected before implementation:
  - `12 failed`
  - every failure is `graph_agent.resume_skill must be a public callable` or `graph_agent.evaluate_golden_baseline must be a public callable`.
  - no syntax, fixture, compile, purity, or environment failures.

- [ ] Confirm scope starts clean for production files.
  _Requirements: WS-E7.scope-lock / IR1._
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/core/_predict_internal packages/graph-agent/src/graph_agent/__init__.py apps/studio packages/graph-agent-gateway`
  Expected before implementation: no production diff from WS-E7. Existing docs/test/spec dirty state may exist.

## Phase 1: Public API Surface

- [ ] Add `resume_skill` and `evaluate_golden_baseline` as public Engine APIs.
  _Requirements: `03-api-contract` §3.1/§3.2; requirements §3/§4._
  Required signatures are locked in the requirements:
  - `resume_skill(skill_path, *, workspace_dir, run_id, checkpoint_id=None, checkpoint_ns=None, context_overrides=None, human_response=None, skill_resolver, model_resolver=None, event_subscriber=None) -> RunResult`
  - `evaluate_golden_baseline(skill_path, *, workspace_dir, baseline_id, skill_resolver, model_resolver=None) -> dict[str, Any]`
  Public export:
  - `graph_agent.resume_skill`
  - `graph_agent.evaluate_golden_baseline`
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_skill_public_api_signature_is_locked packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_evaluate_golden_baseline_public_api_signature_is_locked -q`
  Expected after this phase: signature tests pass. Other tests should move past "missing callable" and fail on unimplemented behavior until later phases.

- [ ] Reuse existing workspace validation.
  _Requirements: physical-layout §2.2.1; requirements §3/§4._
  Both new APIs must reject relative `workspace_dir` before reading env/config/skill root.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_rejects_relative_workspace_dir packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_evaluate_golden_rejects_relative_workspace_dir -q`

## Phase 2: Golden Eval SDK

- [ ] Implement workspace golden loading.
  _Requirements: `06-golden-eval` GD1/GD3; physical-layout §2.2.3; requirements §4._
  Read only:
  - `workspace_dir/golden/<baseline_id>/baseline.json`
  - `workspace_dir/golden/<baseline_id>/cases/<case_id>.json`
  Minimal case schema:
  - `case_id`
  - `phase_id`
  - `inputs`
  - `expected_output`
  - `source`
  - `updated_at`
  Do not read or write `phases/**/golden.json`.

- [ ] Run deterministic LOGIC cases and extract phase output by `phase_id`.
  _Requirements: requirements §4._
  For each case, run the target skill with `case["inputs"]`, using caller-provided `skill_resolver`. Extract actual output from `RunResult.context["phase_outputs"][phase_id]` when available; fall back only to clearly equivalent final business fields if needed for current `BusinessData` compatibility. Do not depend on real LLM for approved RED.

- [ ] Produce report shape and write `report.json`.
  _Requirements: requirements §4._
  Report shape:
  - `baseline_id`
  - `summary`: `total_cases`, `passed`, `failed`, `stale`
  - `cases[]`: `case_id`, `phase_id`, `status`, `score`, `diff`, `stale_fields`
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_deterministic_logic_case_exact_match_writes_passed_report -q`

- [ ] Implement field-level diff for mismatches.
  _Requirements: `06-golden-eval` GD3; requirements §4._
  Approved RED expects a simple changed-field record:
  `{"path": "answer", "expected": "wrong", "actual": "score:alpha", "status": "changed"}`
  Keep the implementation small. Reuse the scoring idea from `apps/studio/backend/app/services/golden_diff.py` if useful, but do not import Studio code into Engine.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_golden_value_mismatch_returns_failed_case_with_field_diff -q`

- [ ] Implement eval-time stale detection.
  _Requirements: `06-golden-eval` GD2; requirements §4._
  If current phase `io.outputs.required` contains fields missing from `expected_output`, mark the case `stale`, include `stale_fields`, and do not make `compile_skill` fatal. Do not reintroduce compile-time `[F-v3-golden-stale-fields]`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_required_output_missing_from_expected_marks_case_stale_not_compile_fatal -q`

- [ ] Preserve workspace layout invariants.
  _Requirements: physical-layout §2.2.5; requirements §4._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_golden_eval_uses_workspace_golden_not_skill_source_or_predict_latest -q`
  Expected:
  - no `golden.json` under skill source tree
  - no `workspace_dir/predict/latest_predict.json`

## Phase 3: Resume SDK

- [ ] Implement checkpoint selector helpers.
  _Requirements: `03-checkpoint` CK1/CK2; requirements §3._
  Support:
  - exact `checkpoint_id`
  - `checkpoint_ns` + latest checkpoint in that namespace
  Use the same backend/thread as the original run. Do not fake resume by starting a clean run from the beginning.

- [ ] Implement `context_overrides` as business blackboard updates only.
  _Requirements: requirements §3; checkpoint baseline current boundary._
  Updates must not write runtime objects, callbacks, compiled graphs, config, or other non-persistent objects into state.
  Approved RED checks that resuming from a checkpoint after `prepare`, with only `topic` overridden, keeps the already-created `draft` and therefore proves the upstream phase was not rerun.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_from_checkpoint_applies_business_context_overrides_without_rerunning_upstream -q`

- [ ] Preserve namespace selector boundaries.
  _Requirements: WS-E5 namespace baseline; requirements §3._
  `checkpoint_ns=""` selects outer checkpoints and must not accidentally pick AGENT or iterate namespaces.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_selector_preserves_checkpoint_namespace_boundaries -q`

- [ ] Validate HITL human response input shape.
  _Requirements: API contract §3.2; requirements §3._
  Accepted shape: `{"content": str, "tool_call_id"?: str}`.
  Reject plain strings and dicts without `content`.
  If later implementing pending interrupt/tool call resolution, `tool_call_id` may be omitted only when exactly one pending call exists; multiple pending calls must fail with a stable Engine error.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_human_response_is_structured_and_plain_string_is_rejected -q`

- [ ] Write resume artifacts under the locked MVP1 policy.
  _Requirements: requirements §3._
  Resume reuses the original `run_id`. Return `RunResult.run_id == run_id` and write:
  - `workspace_dir/runs/<run_id>/result.json`
  - `workspace_dir/runs/<run_id>/final_state.json`
  - `workspace_dir/runs/<run_id>/metrics.json`
  - `workspace_dir/runs/<run_id>/trace.jsonl`

## Phase 4: E2E And Approved Suite

- [ ] Run the WS-E7 E2E RED to GREEN.
  _Requirements: requirements §5/§6._
  Verification command:
  `uv run pytest packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py -q`

- [ ] Run the full approved WS-E7 suite to GREEN.
  _Requirements: hard exit._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py -q`
  Expected after implementation: all tests pass.

## Phase 5: Required Regressions

- [ ] Run WS-E5 checkpoint namespace regression.
  _Requirements: requirements §6._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py -q`

- [ ] Run workspace-dir contract regressions.
  _Requirements: requirements §6._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_workspace_dir_contract_red.py apps/studio/backend/tests/test_workspace_dir_contract_red.py -q`

- [ ] Run E1/E1-io/E4 key runtime regressions.
  _Requirements: requirements §6._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py packages/graph-agent/tests/core/test_ws_e1_io_runtime_red.py packages/graph-agent/tests/e2e/test_ws_e1_io_runtime.py packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py -q`

- [ ] Run public API contract if exports changed.
  _Requirements: API surface lock._
  Verification command:
  `uv run pytest packages/graph-agent/tests/test_public_api_contract.py -q`
  If this fails because the contract snapshot needs an approved public API update for `resume_skill` / `evaluate_golden_baseline`, stop and report the exact diff needed instead of silently weakening the guard.

## Phase 6: Scope Audit And Baseline Handoff

- [ ] Confirm forbidden files are untouched.
  _Requirements: requirements §2 / owns_files._
  Verification command:
  `git diff -- apps/studio packages/graph-agent-gateway packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/middleware`
  Expected: no WS-E7 diff.

- [ ] Confirm no dependency churn.
  _Requirements: scope hygiene._
  Verification command:
  `git status --short -- uv.lock`
  Expected: no diff. If `uv run` touched `uv.lock` without a dependency change, restore it.

- [ ] Run diff hygiene.
  _Requirements: quality gate._
  Verification command:
  `git diff --check -- .kiro/specs/engine-mvp1/requirements-ws-e7-golden-resume.md .kiro/specs/engine-mvp1/task-ws-e7-golden-resume.md .kiro/specs/engine-mvp1/gemini-prompt-ws-e7-golden-resume.md packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/core/_predict_internal packages/graph-agent/src/graph_agent/__init__.py`

- [ ] Do not update baseline before GREEN and Codex review.
  _Requirements: requirements §6._
  After GREEN, report exact landed behavior so Codex/PM can update:
  - `docs/engine/mvp1/_impl/IMPL_PLAN.md`
  - `docs/engine/mvp1/03-api-contract/baseline.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md`
  - `docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/baseline.md`
  - `docs/engine/mvp1/01-contract/01-physical-layout/baseline.md`

## Hard Exit Checklist

- [ ] Approved WS-E7 suite is GREEN.
- [ ] `resume_skill` is public and returns `RunResult`.
- [ ] `resume_skill` rejects relative `workspace_dir`.
- [ ] Resume can select by `checkpoint_id` and by `checkpoint_ns` latest.
- [ ] Resume uses the original LangGraph thread/checkpointer semantics, not a fake full rerun.
- [ ] `context_overrides` update only business blackboard fields.
- [ ] HITL response accepts structured `{content, tool_call_id?}` and rejects plain strings.
- [ ] Resume reuses original `run_id` and writes the required run artifacts.
- [ ] `evaluate_golden_baseline` is public and returns/writes the same report shape.
- [ ] Golden cases are read from `workspace_dir/golden/<baseline_id>/cases/*.json`.
- [ ] Deterministic LOGIC exact match passes.
- [ ] Value mismatch fails with field-level diff.
- [ ] Missing newly-required output fields become eval-time stale, not compile fatal.
- [ ] No `golden.json` appears in skill source tree.
- [ ] No `workspace_dir/predict/latest_predict.json` is created.
- [ ] WS-E5 checkpoint namespace regression passes.
- [ ] Run/predict workspace-dir contract regressions pass.
- [ ] E1/E1-io/E4 key runtime regressions pass.
- [ ] Forbidden Studio/gateway/middleware/callback/io/loader/graph_assembler paths have no WS-E7 diff.
- [ ] `uv.lock` is clean or restored.

## Gemini Report Format

When finished, report:

1. Files changed.
2. Each verification command and pass/fail summary.
3. Whether implementation stayed within owns_files; if not, include explicit PM scope-expansion approval.
4. Resume behavior: selector forms, checkpoint/thread semantics, context override handling, HITL validation, artifact policy.
5. Golden eval behavior: file layout, case schema, diff format, stale handling, report path.
6. Confirmation that forbidden files, `apps/studio/**`, `packages/graph-agent-gateway/**`, and `uv.lock` have no unauthorized WS-E7 diff.
7. Whether baseline docs were left for Codex/PM handoff or updated by explicit instruction.
8. Any hard-exit item not satisfied and why you stopped.
