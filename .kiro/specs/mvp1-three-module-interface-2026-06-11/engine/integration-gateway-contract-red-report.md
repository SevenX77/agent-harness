# Engine Integration Gateway Contract RED Report

## Scope

- Modified test: `packages/graph-agent/tests/core/test_predict_internal_imports.py`
- Added RED test: `packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py`
- Production code changes: 0
- Kiro task / Gemini prompt written: No

## Why The Old Failure Was Not Enough

The previous integration failure was partly caused by the test itself still constructing Gateway's
`ModelResolver` with the removed `registry_snapshot=...` argument. That made the failure ambiguous:
it proved the test fixture was stale, but did not cleanly prove the Engine production owner path was
still using the old Gateway Step 4 contract.

`test_predict_internal_imports.py` now uses the Gateway Step 4 constructor shape:
`ModelResolver(config_store=..., user_id=...)`. The test-side config store provides both required
truth-store records: `credentials` and `roles`.

## New RED Owner-Path Assertion

`test_productization_gateway_contract_integration_red.py` pins the real Engine integration defect:
`packages/graph-agent/src/graph_agent/core/runner.py` must not construct Gateway's resolver with
`ModelResolver(registry_snapshot=...)`.

Current expected RED:

- The import-boundary tests should no longer fail because their own fixture uses the old constructor.
- The integration RED should fail because the Engine production path still contains
  `ModelResolver(registry_snapshot=snapshot)` in `runner.py`.

## Verification

Fresh runs:

- pytest RED summary:
  - Command:
    `uv run pytest packages/graph-agent/tests/core/test_predict_internal_imports.py packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py -q --tb=short`
  - Result: `1 failed, 3 passed`
  - Failure:
    `test_engine_default_predict_resolver_uses_gateway_step4_contract` fails because
    `packages/graph-agent/src/graph_agent/core/runner.py` still contains
    `ModelResolver(registry_snapshot=snapshot)`.
- ruff summary:
  - Command:
    `uv run ruff check packages/graph-agent/tests/core/test_predict_internal_imports.py packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py`
  - Result: `All checks passed!`
- preflight summary:
  - `missing_engine_artifact_api: []`
  - `gateway_model_resolver_signature: (*, config_store: 'ConfigTruthStore', user_id: 'str', client_manager: 'Any' = None, credential_provider: 'CredentialProviderProtocol | None' = None) -> 'None'`
- scope guard summary:
  - Command:
    `git diff --name-only -- packages/graph-agent/src packages/graph-agent-gateway apps/studio docs/engine docs/graph-agent-gateway docs/studio uv.lock`
  - Raw output includes existing integration-synced Engine/Gateway/Studio production diffs already present in the worktree before this RED step.
  - This RED step modified no production files.
- diff check:
  - Command: `git diff --check`
  - Result: no whitespace errors.

## Handoff

- Production code modifications by this RED step: 0
- Kiro task / Gemini prompt written for this integration fix: No
- Ready for Codex review: Yes
