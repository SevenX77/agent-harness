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
