# Round 29 Tasks — Complexity Gate & C901 Refactoring

> Retrospective backfill. `requirements.md`, `research.md`, and `design.md` were already locked; this file records the completed SOP-08 task trail for Round 29.

## Stage 1: Spec (4 件套)

- [x] `requirements.md` — Round 29 P0-2 complexity gate requirements.
- [x] `research.md` — industry C901 practice and 13-helper current-state research.
- [x] `design.md` v7 — final locked design, including §0 prerequisite worktree cleanup, §1 charter, §3 package-local TOML config, §5 full 13 src violation list, and §7 Golden Principle verification table.
- [x] `tasks.md` — this retrospective task list.

## Stage 2: 分歧辩论收敛

- [x] Design v5 -> v6 -> v7 convergence completed.
- [x] a3 audit found 4 gaps and all were resolved:
  - [x] A: PR-8 mislabel corrected.
  - [x] B: obsolete invoke item removed.
  - [x] C: `scripts/` two C901 violations handled via scoped ignore.
  - [x] D: docs/public scope removed from the refactor plan.

## Stage 3: Tests-first

- [x] a1 wrote 8 characterization test files to lock 9 helper baselines before src refactor.
  - [x] `test_dynamic_schema_characterization.py` — 23 tests.
  - [x] `test_md_to_json_helpers_characterization.py` — 7 tests.
  - [x] `test_md2json_characterization.py` — 14 tests.
  - [x] `test_llm_config_characterization.py` — 6 tests.
  - [x] `test_predict_stub_characterization.py` — 12 tests.
  - [x] `test_purity_characterization.py` — 14 tests.
  - [x] `test_on_event_characterization.py` — 12 tests.
  - [x] `test_state_legacy_context_characterization.py` — 12 tests.
- [x] Characterization baseline total: 100 tests passed.

## Stage 4: Src 实施

- [x] `packages/graph-agent/pyproject.toml` gained a package-local `[tool.ruff]` section:
  - [x] `extend = "../../pyproject.toml"`.
  - [x] `extend-select = ["C901"]`.
  - [x] `max-complexity = 10`.
  - [x] `per-file-ignores` for `scripts/**`.
- [x] Refactored 13 src helpers from C901 violations to `<=10`:
  1. [x] `execute` (`core/phase_nodes/llm_phase_node.py:80`, 44 -> <=10) — split phase runtime preparation, model resolve, tools, middleware, cognitive loop, and finalize helpers.
  2. [x] `run` (`core/harness.py:435`, 25 -> <=10) — split initial state, persistent preflight, RunContext, graph invoke, and success/crash finalize paths.
  3. [x] `on_event` (`callbacks/base.py:139`, 14 -> <=10) — Strategy/Table dispatcher pattern for legacy, typed-only, and per-event dispatch.
  4. [x] `resume` (`core/harness.py:949`, 13 -> <=10) — split tool-call lookup, runtime inputs restore, storage restore, and heartbeat stop.
  5. [x] `parse_output_example` (`tools/dynamic_schema.py:71`, 12 -> <=10) — split output-example extraction, line classification, item-header parsing, and field-line parsing.
  6. [x] `_build_type_runtime` (`tools/dynamic_schema.py:316`, 12 -> <=10) — split scalar, `Literal[...]`, list runtime, and list enum validation.
  7. [x] `_parse_block_data` (`tools/md_to_json.py:332`, 12 -> <=10) — split block-line classification, nested-field flush, and list nested-child parsing.
  8. [x] `_coerce_value` (`cognitive/md2json.py:88`, 11 -> <=10) — split JSON-like parsing, scalar coercion, and array fallback.
  9. [x] `_validate_cross_references` (`config/llm_config.py:359`, 11 -> <=10) — split model-provider, role-model, and role-provider validation.
  10. [x] `_normalise_type` (`core/_predict_internal/stub.py:115`, 11 -> <=10) — split string alias normalization into a table-backed helper.
  11. [x] `_violation_for_call` (`core/purity.py:130`, 11 -> <=10) — split name-call and attribute-call purity violation checks.
  12. [x] `legacy_context_from_state` (`core/state.py:167`, 21 -> <=10) — split not-None, non-empty, and copied metadata buckets.
  13. [x] `_wrap_tool_for_langchain` (`core/tool_wrapper.py:102`, 24 -> <=10) — split signature parsing, schema field construction, context/plain invocation helpers, and `StructuredTool` assembly.

## Stage 5: Src 偏移 Audit (双重)

- [x] a2 grep verify passed:
  - [x] 0 new Event.
  - [x] 0 new public def.
  - [x] 3 `__all__` additions verified as scope control.
- [x] a3 PM-proxy audit passed:
  - [x] Quality A+.
  - [x] 3 safeguards preserved: callback emit ordering, WorkflowState lifecycle, and state deepcopy.
  - [x] Hidden coupling preserved.
  - [x] Characterization coverage was real, not decorative.

## Stage 6: Docs Sync

- [x] `mvp0-alignment.md` gained the Round 29 section.
  - [x] 41-line Round 29 section at lines 19-59.
- [x] `00-PROGRESS-STATUS.md` updated the Round 29 / P0-2 Complexity Gate entry.
  - [x] Diff size: +3 / -3.
- [x] `docs/engine/*` unchanged; FROZEN docs SHA remained protected.

## Stage 7: PR Report

- [x] PM-facing natural-language report written to `/tmp/round29-pr-report.md`.
- [x] Report shape: 3 paragraphs aligned to design, implementation evidence, and post-merge behavior.
- [x] Report size: 749 non-whitespace characters.

## Stage 8: Forward PM

- [x] Controller forwarded the report verbatim to PM.

## Stage 9: Merge

- [ ] Pending PM acknowledgement.
- [ ] Merge target: `stage/engine-v030` via `--no-ff`, per staged merge workflow.

## Verify Evidence

- [x] `uv run ruff check --select C901 packages/graph-agent/`: 0 violations.
- [x] 100 characterization tests passed.
- [x] 4 contract gates passed: `test_public_api_contract`, `test_contract_hash_lock`, `test_round28_contract_manifests`, and `test_round28_invariant_guards`.
- [x] Contract gate total: 38 tests passed.
- [x] Full graph-agent test suite: 1171 passed, 2 skipped, 19 xfailed.

## Golden Principle Verify

- [x] 65 public API symbols stable.
- [x] 92 error codes stable.
- [x] 33 event types stable.
- [x] 53 skill-spec H2 sections stable.
- [x] 14 FROZEN docs SHA-256 stable.
- [x] Round 28 five mechanisms stable.
