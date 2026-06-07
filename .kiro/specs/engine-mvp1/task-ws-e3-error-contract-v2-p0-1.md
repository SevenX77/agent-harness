---
ws_id: WS-E3-error-contract-v2-p0-1
task_type: implementation
implementer: Gemini
author: Codex
status: drafted
created: 2026-06-06
requirements: .kiro/specs/engine-mvp1/requirements-ws-e3-error-contract-v2-p0-1.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
spec_ssot:
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md §3.1/§3.1.1
  - docs/engine/mvp1/01-contract/04-data-contracts/mvp1-alignment.md §3/§5 DC5/§6
  - docs/engine/mvp1/03-api-contract/mvp1-alignment.md §2.1/§2.2/§3.3
approved_red_tests:
  - packages/graph-agent/tests/core/test_error_payload_contract.py
  - packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py
  - packages/graph-agent/tests/predict/test_predict_skill_run_result.py
  - packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py
red_result: "uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py packages/graph-agent/tests/predict/test_predict_skill_run_result.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q -> 9 failed, 53 passed"
owns_files:
  - packages/graph-agent/src/graph_agent/core/exceptions.py
  - packages/graph-agent/src/graph_agent/core/result.py
  - packages/graph-agent/tests/core/test_error_payload_contract.py
  - packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py
  - packages/graph-agent/tests/predict/test_predict_skill_run_result.py
  - packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py
forbidden_files:
  - packages/graph-agent/src/graph_agent/core/error_registry.py
  - packages/graph-agent/src/graph_agent/core/runner.py
  - packages/graph-agent/src/graph_agent/callbacks/events.py
  - packages/graph-agent/src/graph_agent/callbacks/emit.py
  - apps/studio/**
---

# WS-E3 Error Contract V2 P0-1 Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Do not weaken them. Implement task-by-task until the approved RED suite is GREEN.

**Goal:** Implement the P0-1 minimum closed loop for error contract V2: `ErrorPayload.details`, `GraphAgentError.context -> payload.details`, and bounded `RunResult.diagnostics`.

**Architecture:** Keep the change additive and local to `core/exceptions.py` and `core/result.py`. `ErrorPayload` owns JSON-safe diagnostic payload normalization; `RunResult` owns final bounded diagnostics snapshot derivation. Existing runner/artifact writes should pick up the new fields through `model_dump(mode="json")` without modifying `runner.py`.

**Tech Stack:** Python 3.12, Pydantic v2 models, pytest, existing `ERROR_REGISTRY`.

---

## Phase 0: Grounding And Scope Lock

- [ ] Read the requirements file and SSOT pointers before editing.
  _Requirements: IR2 / IR5 grounding._
  Verify by reporting the current live symbols: `ErrorPayload`, `make_error_payload`, `GraphAgentError.__init__`, `RunResult`, `WorkflowResult`, and the `run_skill` failure boundary.

- [ ] Confirm only these production files need implementation changes: `packages/graph-agent/src/graph_agent/core/exceptions.py` and `packages/graph-agent/src/graph_agent/core/result.py`.
  _Requirements: IR1 file ownership, WS-E3 P0-1 scope._
  Verification command: `git status --short -- packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py`

- [ ] Re-run the approved RED suite once before implementing, and keep the failure shape unchanged.
  _Requirements: TDD RED evidence._
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py packages/graph-agent/tests/predict/test_predict_skill_run_result.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q`
  Expected now: `9 failed, 53 passed`, with failures caused by missing `details` / `diagnostics`.

## Phase 1: ErrorPayload.details And JSON-Safe Normalization

- [ ] Implement `ErrorPayload.details` as an additive field with empty-object default semantics.
  _Requirements: `01-contract/04-data-contracts` DC5; requirements §5.1 / §6._
  Target tests:
  `packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_payload_details_default_to_empty_json_object`
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_payload_details_default_to_empty_json_object -q`

- [ ] Normalize `details` into stable JSON-safe values at model construction / validation time.
  _Requirements: requirements §5.1 JSON-safe boundary._
  Approved RED expects:
  `Path -> str`, `set -> sorted list`, nested `BaseModel -> dict`, `Exception -> "TypeName: message"`.
  Target tests:
  `packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_payload_details_are_json_safe_and_stable`
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_payload_details_are_json_safe_and_stable -q`

- [ ] Preserve existing metadata behavior and legacy constructors.
  _Requirements: requirements §5.5 backward compatibility._
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_payload_autofills_registry_metadata packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_payload_rejects_unknown_code packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_payload_requires_nonempty_message -q`

## Phase 2: GraphAgentError.context Enters Payload Details

- [ ] When a `GraphAgentError` creates a payload from an embedded registered code and receives `context`, merge that context into `payload.details["context"]`.
  _Requirements: requirements §5.2 context enters payload._
  Target test:
  `packages/graph-agent/tests/core/test_error_payload_contract.py::test_graph_agent_error_generated_payload_carries_context_details`
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py::test_graph_agent_error_generated_payload_carries_context_details -q`

- [ ] When a caller passes an explicit payload with explicit `details` and also passes exception `context`, keep both visible without overwriting explicit details.
  _Requirements: requirements §5.2 merge rule._
  Required merge shape from approved RED: existing top-level `details` keys stay as-is; normalized exception context appears under `details["context"]`.
  Target test:
  `packages/graph-agent/tests/core/test_error_payload_contract.py::test_graph_agent_error_merges_explicit_payload_details_and_context`
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py::test_graph_agent_error_merges_explicit_payload_details_and_context -q`

- [ ] Keep the external gateway-code compatibility branch payloadless.
  _Requirements: requirements §5.5 / §6 compatibility._
  Target test:
  `packages/graph-agent/tests/core/test_error_payload_contract.py::test_graph_agent_error_keeps_external_gateway_codes_payloadless`
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py::test_graph_agent_error_keeps_external_gateway_codes_payloadless -q`

## Phase 3: RunResult.diagnostics Snapshot, Bounds, And Counts

- [ ] Add `diagnostics`, `diagnostics_limit`, `diagnostics_truncated`, and `diagnostic_counts` to `RunResult`, inherited by `WorkflowResult`.
  _Requirements: requirements §5.3 / §5.5._
  Safe defaults: success results have `diagnostics == []`, positive `diagnostics_limit`, `diagnostics_truncated is False`, and counts `{"total": 0, "by_level": {}, "by_code": {}}`.
  Target tests:
  `packages/graph-agent/tests/predict/test_predict_skill_run_result.py::test_predict_skill_returns_run_result_with_predict_source`
  `packages/graph-agent/tests/predict/test_predict_skill_run_result.py::test_run_result_defaults_diagnostics_for_success_and_error_only_failure`
  Verification command: `uv run pytest packages/graph-agent/tests/predict/test_predict_skill_run_result.py::test_predict_skill_returns_run_result_with_predict_source packages/graph-agent/tests/predict/test_predict_skill_run_result.py::test_run_result_defaults_diagnostics_for_success_and_error_only_failure -q`

- [ ] Derive a failure diagnostics snapshot from `error` when no explicit diagnostics are provided.
  _Requirements: requirements §5.3 main fatal compatibility._
  The main fatal `error` remains present and the diagnostics list includes the same payload at least once.
  Verification command: `uv run pytest packages/graph-agent/tests/predict/test_predict_skill_run_result.py::test_run_result_defaults_diagnostics_for_success_and_error_only_failure -q`

- [ ] For explicit diagnostics, place the main `error` first, dedupe it from the rest of the list, apply a deterministic limit, and set `diagnostics_truncated`.
  _Requirements: requirements §5.3 bounded deterministic snapshot._
  Approved RED expects the visible list to be `[main_error, warn]` when explicit diagnostics are `[warn, main_error, other_fatal]` and `diagnostics_limit=2`.
  Target test:
  `packages/graph-agent/tests/predict/test_predict_skill_run_result.py::test_run_result_diagnostics_merge_main_error_dedupe_bound_and_count_full_snapshot`
  Verification command: `uv run pytest packages/graph-agent/tests/predict/test_predict_skill_run_result.py::test_run_result_diagnostics_merge_main_error_dedupe_bound_and_count_full_snapshot -q`

- [ ] Compute `diagnostic_counts` from the full deduped diagnostic input before truncation, grouped by `level` and `code`.
  _Requirements: requirements §5.3 counts._
  Approved RED expects `total == 3`, `by_level == {"FATAL": 2, "WARN": 1}`, and all three codes counted even when the visible list is truncated to two.
  Verification command: `uv run pytest packages/graph-agent/tests/predict/test_predict_skill_run_result.py::test_run_result_diagnostics_merge_main_error_dedupe_bound_and_count_full_snapshot -q`

- [ ] Preserve `RunResult.status` and old construction forms.
  _Requirements: requirements §5.5 backward compatibility._
  Verification command: `uv run pytest packages/graph-agent/tests/predict/test_predict_skill_run_result.py::test_run_result_success_derives_from_path_diff -q`

## Phase 4: WorkflowResult And Real run_skill E2E

- [ ] Ensure `WorkflowResult` inherits the new fields and its dict-like `get` / `__getitem__` shims can read `diagnostics`.
  _Requirements: requirements §5.5 WorkflowResult compatibility._
  Target test:
  `packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py::test_workflow_result_exposes_diagnostics_through_dump_and_dict_like_shims`
  Verification command: `uv run pytest packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py::test_workflow_result_exposes_diagnostics_through_dump_and_dict_like_shims -q`

- [ ] Keep `model_dump(mode="json")`, `model_dump_json()`, and `json.dumps(result.model_dump(mode="json"))` safe with non-JSON-native `details`.
  _Requirements: requirements §5.1 / §8 JSON write boundary._
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_payload_details_are_json_safe_and_stable packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py::test_workflow_result_exposes_diagnostics_through_dump_and_dict_like_shims -q`

- [ ] Pass the real `run_skill` missing-`GRAPH.md` failure e2e without modifying `runner.py`.
  _Requirements: requirements §6 real e2e / §9 no runner edits._
  The existing `run_skill` boundary should pick up diagnostics through `WorkflowResult` defaults and `_write_workflow_result_artifacts(... result.model_dump(mode="json"))`.
  Target test:
  `packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py::test_run_skill_missing_graph_root_writes_error_diagnostics_snapshot`
  Verification command: `uv run pytest packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py::test_run_skill_missing_graph_root_writes_error_diagnostics_snapshot -q`

## Phase 5: Full Verification And Scope Audit

- [ ] Run the approved WS-E3 suite to GREEN.
  _Requirements: requirements §8 hard exit._
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py packages/graph-agent/tests/predict/test_predict_skill_run_result.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q`
  Expected after implementation: all tests pass.

- [ ] Run focused existing compatibility tests for registry size and public error surface.
  _Requirements: requirements §5.5 / §8 no registry metadata shape change._
  Verification command: `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_registry_matches_error_code_spec_key_set packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py::test_public_error_catalog_exports_only_five_family_classes packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py::test_workflow_result_error_accepts_structured_payload -q`

- [ ] Confirm forbidden production files are untouched.
  _Requirements: IR1 / IR7 scope lock._
  Verification command: `git diff -- packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py`
  Expected: no diff in these forbidden engine files. `apps/studio/**` is outside this WS and may already be dirty in the shared worktree; do not edit it, and report any pre-existing status separately with `git status --short -- apps/studio`.

- [ ] Run diff hygiene.
  _Requirements: implementation quality gate._
  Verification command: `git diff --check -- packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/tests/core/test_error_payload_contract.py packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py packages/graph-agent/tests/predict/test_predict_skill_run_result.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py`

## Hard Exit Checklist

- [ ] Approved RED suite is GREEN.
- [ ] `ErrorPayload.details` is present, default-readable as `{}`, and JSON-safe.
- [ ] `GraphAgentError.context` appears under payload details without swallowing explicit details.
- [ ] `RunResult` and `WorkflowResult` expose bounded `diagnostics`, `diagnostics_limit`, `diagnostics_truncated`, and `diagnostic_counts`.
- [ ] Failure results with only `error` automatically expose that main fatal in diagnostics.
- [ ] Real `run_skill` failure e2e writes `result.json` with diagnostics.
- [ ] `ERROR_REGISTRY` key set stays 93 and `ErrorCodeMetadata` shape is untouched.
- [ ] No P0-2/P0-3/WS-E4 work was implemented: no `remediation`, `doc_ref`, `doc_url`, `details_schema`, `GET /errors`, `DiagnosticEmittedEvent`, or runtime error-code split.
- [ ] Forbidden engine files have no diff, and `apps/studio/**` was not touched by this WS.

## Gemini Report Format

When finished, report:

1. Files changed.
2. The exact tests run and pass/fail output summary.
3. Confirmation that forbidden engine files have no diff and `apps/studio/**` was not edited by this WS.
4. Any remaining risk or reason a hard-exit item is not satisfied.
