# MVP1 three-module final integration audit report

Date: 2026-06-12

Worktree: `/Users/sevenx/Documents/coding/agent-harness/.worktrees/mvp1-three-module-integration-2026-06-11`

Branch: `codex/mvp1-three-module-integration-2026-06-11`

Status: PASS

## Scope closed in this audit

- Gateway tests were updated to the Step 4 resolver contract: `ModelResolver(config_store=..., user_id=...)`.
- Gateway tests no longer construct `ModelResolver(registry_snapshot=...)`, `credentials_path=...`, or `roles_path=...`.
- Cross-module Graph-Agent tests now use package-relative imports so the combined pytest collection does not accidentally import Studio's `tests` package.
- `predict_skill` RunResult coverage now uses a provider-free logic fixture and clears the predict mock-source cache before assertion, avoiding cross-module test pollution.
- Graph-Agent public API contract now includes `compile_artifact`, `run_artifact`, and `predict_artifact`.
- `PredictGatewayChatModel` exposes an explicit constructor signature for the public API contract instead of leaking dynamic `*args, **kwargs`.
- MVP1 functional-completion follow-up removed the last two silent exception paths:
  - publish rollback failure now logs a warning before raising `PublishPartialFailure`.
  - Copilot Gateway fallback decision failure now logs a warning before treating the route as exhausted.
- Frontend typecheck dependency gap was closed by running `npm ci` followed by `npm run typecheck`.

## Verification

| Gate | Command | Result |
| --- | --- | --- |
| Silent-exception RED/GREEN | `uv run pytest apps/studio/backend/tests/services/test_productization_publish_atomicity_red.py::test_publish_pipeline_logs_rollback_failure apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py::test_next_copilot_route_logs_gateway_fallback_failure -q --tb=short` | RED first failed on empty `caplog.text`; GREEN result `2 passed` |
| Silent-exception related regression | `uv run pytest apps/studio/backend/tests/services/test_productization_publish_atomicity_red.py apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py -q --tb=short` | `19 passed` |
| Engine full | `uv run pytest packages/graph-agent/tests -q --tb=short` | `1297 passed, 2 skipped, 3 xfailed, 3 xpassed` |
| Gateway full | `uv run pytest packages/graph-agent-gateway/tests -q --tb=short` | `198 passed, 1 xfailed` |
| Studio backend full | `uv run pytest apps/studio/backend/tests -q --tb=short` | `474 passed, 2 warnings` |
| Frontend typecheck | `cd apps/studio/frontend && npm ci && npm run typecheck` | dependencies installed; `tsc -b --noEmit` passed |
| Ruff | `uv run ruff check packages/graph-agent packages/graph-agent-gateway apps/studio/backend` | `All checks passed!` |
| Diff whitespace | `git diff --check` | no output |

The three backend pytest gates were run in separate processes to avoid the known cross-module `tests.conftest` import-name collision.

## Preflight

```text
missing_engine_artifact_api: []
gateway_model_resolver_signature: (*, config_store: 'ConfigTruthStore', user_id: 'str', client_manager: 'Any' = None, credential_provider: 'CredentialProviderProtocol | None' = None) -> 'None'
```

## Static guards

- Studio app owner path guard for old runtime and old Gateway resolver contract: no output.
- Gateway resolver constructor guard for `registry_snapshot`, `credentials_path`, and `roles_path` in active source paths: no output.
- Full Studio app+tests guard only reports self-check strings in contract tests and an old integration test name; no active owner path calls `run_skill`, `predict_skill`, hidden runtime hooks, or `ModelResolver(registry_snapshot=...)`.

## Keyword coverage

The required temporary implementation plan file `temp/productization-mvp1-interface-implementation-plan-2026-06-11.md` is not present in this worktree. The same keyword self-check was run against the checked-in design directory:

`docs/mvp1-three-module-interface-design-and-changes-2026-06-11`

All required terms were found in the checked-in design/plan/work-order docs:

- `etag`
- `fencing`
- `幂等`
- `hash 校验`
- `超时`
- `原子`
- `seal`
- `HTTP 本地模拟`
- `Idempotency-Key`
- `schema_version`
- `ResponseEnvelope`

## Scope guard

`git diff --name-only -- docs/studio docs/engine docs/graph-agent-gateway uv.lock` produced no output.

FROZEN docs and `uv.lock` were not touched in this audit.

## Skipped, xfailed, xpassed, and warnings breakdown

These are not MVP1 functional failures, but they should stay visible in the handoff because they affect how to read the green gate.

### Engine skipped: 2

- `packages/graph-agent/tests/integration/test_mvp1_smoke.py::TestRealLLMSmoke` is skipped when no credentialed v4/v2 route registry is configured. This is an environment/cost guard for real-LLM smoke; compile and invariant layers still run.
- `packages/graph-agent/tests/middleware/test_execution_control.py` skips the `threshold=1` below-state case because that parameter combination has no meaningful "below" state.

### Engine xfailed: 3

All three are marked from `packages/graph-agent/tests/conftest.py` with:

`by-design: V1 layout skill awaiting user V2.1 cutover (Phase 1 baseline)`

- `packages/graph-agent/tests/integration/test_mvp1_smoke.py::TestCompileLayer::test_v3_skill_compiles_to_graph_agent_harness`
- `packages/graph-agent/tests/integration/test_mvp1_smoke.py::TestCompileLayer::test_v3_skill_io_outputs_declared`
- `packages/graph-agent/tests/tools/test_dual_run_shadow.py::test_dual_run_shadow_hello_world_idempotency`

These are historical V1-layout/V2.1-cutover expectations, not failures introduced by MVP1 productization.

### Engine xpassed: 3

These tests were still marked expected-failure, but now pass. They should be cleaned up in a small test-marker maintenance pass:

- `packages/graph-agent/tests/core/test_module_sandbox.py::test_loader_pipeline_resolves_skill_forward_ref_segment_class`
- `packages/graph-agent/tests/core/test_workspace_dir_contract_red.py::test_public_engine_entrypoints_require_workspace_dir_argument[predict_skill]`
- `packages/graph-agent/tests/core/test_workspace_dir_contract_red.py::test_public_engine_entrypoints_require_workspace_dir_argument[evaluate_golden_baseline]`

The two workspace-dir cases were originally marked for a later PR-E surface, but the public APIs now exist and satisfy the assertion.

### Gateway xfailed: 1

- `packages/graph-agent-gateway/tests/test_model_resolver_protocol.py::test_agent_phase_react_loop_uses_injected_model_resolver`

Reason recorded in the test:

`pre-existing red: run_skill 自 PR-α #91 起要求 skill_resolver kwarg; 属 run_skill 签名工作 (PR-B), 非 PR-A errors scope`

This is a historical PR-split marker. It should be re-triaged now that the integration branch has advanced, but it is not a current MVP1 functional-completion regression.

### Studio warnings: 2

- `apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py::test_golden_headless_request_only_accepts_run_results_ref_and_baseline_ref` emits two Pydantic `model_fields` deprecation warnings from test helper code.

The helper reads `model_fields` from a Pydantic model instance. Pydantic v2.11 warns that this should be read from the model class instead, for example `type(value).model_fields`.

### Follow-up recommendation

- Non-blocking but cheap before merge: remove stale XPASS markers and fix the Studio Pydantic test helper warning.
- PM decision: keep or retire the four remaining XFAIL markers (`3 Engine + 1 Gateway`) as V2.1/PR-B follow-up scope.
- Keep the real-LLM smoke skip unless a credentialed route registry is intentionally provided for a paid smoke run.

Ready for final Codex review: Yes
