# Engine MVP0 Alignment

## Round 28 Contract Manifests Status

Round 28 is complete as the manifest-based upgrade of the Round 27 feature checklist. The old strict checklist guard has been upgraded from a 30 item hard lock to a 35 feature hard lock: `features.yaml` has 35 business features, `feature-compliance-checklist.md` has 35 H3 entries, and the checklist has 35 collectable coverage references.

The current Round 28 manifest baseline is:

- `packages/graph-agent/spec/features.yaml`: 35 independently named business features. The manifest assigns exactly one primary owner for each of the 92 concrete `[F-v3-*]` error codes and each of the 33 `CallbackEvent` variants.
- `packages/graph-agent/spec/source_file_map.yaml`: all 121 `packages/graph-agent/src/graph_agent/**/*.py` files are mapped. The current clustering is 61 `feature` files and 60 `detail` files, with no unclassified source file.
- `packages/graph-agent/spec/contract_map.yaml`: the public API axis covers 65 symbols, the skill-spec axis covers 53 H2 sections, and the consumer axis covers stable exports, live consumers, and 6 vendor-only debt entries.
- `packages/graph-agent/scripts/validate_round28_manifest.py`: validates target test collection, primary owner uniqueness and completeness, source file coverage, feature/core-path reverse mapping, vendor-only coverage, public API coverage, contract feature id references, runtime compatibility patches, cutover attestation, and skill-spec anchor existence.
- `.github/workflows/ci.yml`: the graph-agent matrix job runs the Round 28 validator after the graph-agent pytest step. Any non-zero validator exit blocks the CI job.

The dual-run guard is intentionally still present. `packages/graph-agent/tests/test_feature_traceability_matrix.py` remains as the upgraded checklist guard and now locks the Round 28 baseline at 35. `packages/graph-agent/tests/test_round28_contract_manifests.py` is the fixture-based manifest guard with 18 tests. `packages/graph-agent/tests/test_round28_invariant_guards.py` adds 5 mechanism guards for prompt slots, middleware ordering, tool sandboxing, blackboard state mapping, and error registry shape.

Round 27 frozen contract docs remain unchanged: `docs/engine/public-api-contract.md` and `docs/engine/skill-spec/*.md` are still protected by the contract hash lock. Round 28 freezes `docs/engine/feature-compliance-checklist.md` as a generated checklist from `features.yaml`.

## Round 29 Complexity Gate & C901 Refactoring Status

Round 29 is complete as an internal refactor-only complexity gate pass. It enabled the graph-agent ruff C901 gate and refactored the remaining 13 high-complexity `src/graph_agent` helpers without changing the public contract, event surface, or frozen engine docs.

`packages/graph-agent/pyproject.toml` now has a package-local `[tool.ruff]` section with `extend = "../../pyproject.toml"`, `[tool.ruff.lint].extend-select = ["C901"]`, `[tool.ruff.lint.mccabe].max-complexity = 10`, and `[tool.ruff.lint.per-file-ignores]."scripts/**" = ["C901"]`. The two script-only validator violations (`_validate_features` at `scripts/validate_round28_manifest.py:130` and `main` at `scripts/validate_round28_manifest.py:246`) are intentionally exempted because the Round 28 manifest validator is a one-off contract gate script, not runtime engine code.

The 13 refactored src helpers are:

1. `execute` (`core/phase_nodes/llm_phase_node.py:80`, C901 44-><=10) — split into `_prepare_phase_runtime`, model resolve, tools, middleware, cognitive loop, and finalize helpers.
2. `run` (`core/harness.py:435`, C901 25-><=10) — split initial state, persistent preflight, RunContext, graph invoke, and success/crash finalize paths.
3. `on_event` (`callbacks/base.py:139`, C901 14-><=10) — converted to a Strategy/Table dispatcher pattern with legacy dispatch, typed-only dispatch, and per-event dispatchers.
4. `resume` (`core/harness.py:949`, C901 13-><=10) — split tool-call lookup, runtime inputs restore, storage restore, and heartbeat stop.
5. `parse_output_example` (`tools/dynamic_schema.py:71`, C901 12-><=10) — split output-example extraction, line classification, item-header parsing, and field-line parsing.
6. `_build_type_runtime` (`tools/dynamic_schema.py:316`, C901 12-><=10) — split scalar, `Literal[...]`, list runtime, and list enum validation.
7. `_parse_block_data` (`tools/md_to_json.py:332`, C901 12-><=10) — split block-line classification, nested-field flush, and list nested-child parsing.
8. `_coerce_value` (`cognitive/md2json.py:88`, C901 11-><=10) — split JSON-like parsing, integer/number/boolean scalar coercion, and array fallback.
9. `_validate_cross_references` (`config/llm_config.py:359`, C901 11-><=10) — split model-provider, role-model, and role-provider validation.
10. `_normalise_type` (`core/_predict_internal/stub.py:115`, C901 11-><=10) — split string alias normalization into a table-backed helper.
11. `_violation_for_call` (`core/purity.py:130`, C901 11-><=10) — split name-call and attribute-call purity violation checks.
12. `legacy_context_from_state` (`core/state.py:167`, C901 21-><=10) — split not-None, non-empty, and copied metadata buckets while preserving shallow-copy and `_`-field behavior.
13. `_wrap_tool_for_langchain` (`core/tool_wrapper.py:102`, C901 24-><=10) — split signature parsing, schema field construction, context/plain invocation helpers, and `StructuredTool` assembly.

Verification evidence from the Round 29 implementation run:

- `uv run ruff check --select C901 packages/graph-agent/`: 0 violations.
- Characterization baseline: 100 tests passed.
- Contract gates: 38 tests passed for public API, contract hash lock, Round 28 manifests, and Round 28 invariant guards.
- Full graph-agent test suite: 1171 passed, 2 skipped, 19 xfailed.

Golden contract invariants did not drift: 0 new `CallbackEvent` classes, 0 new public defs, `events.py` unchanged, and the 65 public API symbols, 92 error codes, 33 events, 53 skill-spec H2 sections, and Round 28 five mechanism guards all stayed stable.

Round 29 also locked the helper baseline with 8 characterization test files:

- `tests/tools/test_dynamic_schema_characterization.py` — `parse_output_example` and `_build_type_runtime`, 23 cases.
- `tests/tools/test_md_to_json_helpers_characterization.py` — `_parse_block_data`, 7 cases.
- `tests/cognitive/test_md2json_characterization.py` — `_coerce_value`, 14 cases.
- `tests/config/test_llm_config_characterization.py` — `_validate_cross_references`, 6 cases.
- `tests/core/test_predict_stub_characterization.py` — `_normalise_type`, 12 cases.
- `tests/core/test_purity_characterization.py` — `_violation_for_call`, 14 cases.
- `tests/callbacks/test_on_event_characterization.py` — `on_event`, legacy Strategy/Table dispatch plus typed-only and fallback behavior.
- `tests/core/test_state_legacy_context_characterization.py` — `legacy_context_from_state`, shallow-copy semantics, `_`-field preservation, and invariant assertions.
