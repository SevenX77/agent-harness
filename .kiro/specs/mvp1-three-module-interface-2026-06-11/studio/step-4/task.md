# Studio Step 4: Contract Repair GREEN Task

## Status

Step 4 RED contract fix has passed Codex review. This task is the repair-preparation document for turning those contract RED tests GREEN.

Do not hand implementation to Gemini until Codex reviews this `task.md` and the paired `gemini-prompt.md`.

## Goal

Close the two remaining three-module contract gaps in Studio owner paths:

1. Studio Gateway owner path must use Gateway Step 4 resolver contract: `ModelResolver(config_store=..., user_id=...)`.
2. Studio `EngineAdapter.run_artifact(...)` and `EngineAdapter.predict_artifact(...)` must call Engine artifact runtime APIs, not the old source-skill runtime APIs.

The fix must be design-facing and contract-facing. Do not hide old paths behind adapters.

## Non-Goals

- Do not modify `packages/graph-agent/**`.
- Do not modify `packages/graph-agent-gateway/**`.
- Do not modify `docs/studio/**`, `docs/engine/**`, `docs/graph-agent-gateway/**`, or FROZEN docs.
- Do not modify `uv.lock`.
- Do not modify frontend code.
- Do not weaken, skip, or rewrite the approved RED tests to match the current implementation.
- Do not add fixed fake returns in production code.
- Do not keep compatibility fallbacks to `ModelResolver(registry_snapshot=...)` in Studio owner paths.
- Do not keep compatibility fallbacks from artifact runtime to `run_skill(...)` or `predict_skill(...)`.

If the required Engine or Gateway public API is not available in this worktree, stop and report a blocker instead of falling back to old source/runtime contracts.

## Dependency Preflight Gate

Before running RED tests or changing implementation code, prove that this Studio worktree already contains the Engine and Gateway Step 4 public APIs.

Run:

```bash
uv run python - <<'PY'
import graph_agent
from inspect import signature
from graph_agent_gateway.resolver import ModelResolver

missing = [
    name for name in ("compile_artifact", "run_artifact", "predict_artifact")
    if not hasattr(graph_agent, name)
]
print("missing_engine_artifact_api:", missing)
print("gateway_model_resolver_signature:", signature(ModelResolver))
PY
```

Required output shape before implementation may start:

```text
missing_engine_artifact_api: []
gateway_model_resolver_signature: (*, config_store=..., user_id=..., ...)
```

Hard gate:

- If `missing_engine_artifact_api` is not empty, do not implement Studio GREEN. Report a dependency blocker.
- If `ModelResolver` does not accept `config_store` and `user_id`, do not implement Studio GREEN. Report a dependency blocker.
- Do not work around the missing APIs inside Studio by modifying `packages/graph-agent/**`, modifying `packages/graph-agent-gateway/**`, or falling back to old Studio/source-runtime contracts.

Dependency coordination question to resolve before implementation when the gate fails:

- Should this Studio worktree first sync the already-approved Engine + Gateway Step 4 changes, then rerun this gate and proceed?
- Or should Studio stop at dependency blocker and wait for a three-module integration worktree?

Known current blocker from the local preflight probe:

```text
missing_engine_artifact_api: ['compile_artifact', 'run_artifact', 'predict_artifact']
gateway_model_resolver_signature: (*, registry_snapshot: 'RegistrySnapshot | None' = None, credentials_path: 'str | Path | None' = None, roles_path: 'str | Path | None' = None, client_manager: 'Any' = None, credential_provider: 'CredentialProviderProtocol | None' = None) -> 'None'
```

This means the current dependency state is not implementable within Studio scope. Do not hand to Gemini for GREEN implementation until the dependency strategy is confirmed and the preflight gate passes.

## Required Context

Read these before implementation:

- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md`
- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md`
- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-studio-work-order.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-4/red-contract-fix-report.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-4/gemini-prompt.md`

## Approved RED Tests

The contract RED command is:

```bash
uv run pytest \
  apps/studio/backend/tests/services/test_gateway_resolver_bridge.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py \
  -q --tb=short
```

Expected current RED shape before implementation:

- `test_gateway_resolver_bridge_uses_config_truth_store_instead_of_registry_snapshot`
- `test_gateway_resolver_bridge_allows_missing_credentials_first_run`
- `test_gateway_owner_paths_do_not_use_registry_snapshot_model_resolver_contract`
- `test_engine_adapter_artifact_runtime_uses_new_artifact_apis_not_source_skill_runtime`

The failures must point to:

- Studio still calling `ModelResolver(registry_snapshot=...)`.
- `EngineAdapter.run_artifact(...)` or `EngineAdapter.predict_artifact(...)` still calling `run_skill(...)` or `predict_skill(...)`.

## Allowed Files

Keep changes as narrow as possible. The expected implementation files are:

- `apps/studio/backend/app/core/adapters/gateway.py`
- `apps/studio/backend/app/core/adapters/engine.py`
- `apps/studio/backend/app/services/gateway_resolver.py`

Only touch additional Studio backend files if a real call site must be updated to preserve the same owner-path contract. Do not touch Engine/Gateway package code.

## Contract 1: Gateway Resolver Truth Store

### Required Behavior

Studio owner paths must construct Gateway resolver through:

```python
ModelResolver(config_store=..., user_id=...)
```

Studio owner paths must not construct Gateway resolver through:

```python
ModelResolver(registry_snapshot=...)
```

This applies at minimum to:

- `apps/studio/backend/app/core/adapters/gateway.py`
- `apps/studio/backend/app/core/adapters/engine.py`
- `apps/studio/backend/app/services/gateway_resolver.py`

### Design Intent

Gateway owns route resolution semantics. Studio owns user config persistence and passes a config truth store plus user id into Gateway. Studio must not materialize a registry snapshot and treat it as the resolver contract.

### Implementation Notes

- Use the existing Studio-owned local config store where possible, such as `LocalGatewayConfigStore`.
- Persist or expose credentials and role config through the config store under the active Studio user id.
- Use `config.DEFAULT_USER_ID` where the existing Studio owner path has no explicit user id.
- Existing tests should be able to assert that the resolver received:
  - a `config_store`
  - the expected `user_id`
  - readable credentials and roles from the store
- Do not depend on `resolver.registry_snapshot` in Studio tests or production flow.
- Do not hide `registry_snapshot` usage behind a helper name.

## Contract 2: Engine Artifact Runtime

### Required Behavior

`EngineAdapter.run_artifact(payload)` must call the Engine artifact runtime API:

- `graph_agent.run_artifact(...)`, or
- the equivalent adapter-private re-export of the same public artifact API.

`EngineAdapter.predict_artifact(payload)` must call the Engine artifact prediction API:

- `graph_agent.predict_artifact(...)`, or
- the equivalent adapter-private re-export of the same public artifact API.

They must not call:

- `run_skill(...)`
- `predict_skill(...)`

### Required Payload Semantics

The call into Engine artifact APIs must carry artifact semantics, including:

- `artifact_ref`
- `inputs`
- `execution_context` or equivalent context object
- `idempotency_key`

Return values must remain JSON-serializable dictionaries at the Studio adapter boundary.

### Design Intent

Studio Step 4 closes the owner path from source-skill execution to product artifact execution. Calling old source runtime inside `EngineAdapter` violates the three-module boundary even if services no longer import SDK internals.

### Implementation Notes

- Keep SDK imports isolated inside `apps/studio/backend/app/core/adapters/engine.py`.
- Preserve existing `StudioAdapterError` wrapping and error codes where possible.
- Keep HTTP loopback behavior intact.
- If the local `graph_agent` package does not expose artifact APIs, stop and report a blocker. Do not emulate artifact runtime by compiling to a temporary skill dir and calling `run_skill(...)`.

## Verification

### 1. Contract GREEN

Run:

```bash
uv run pytest \
  apps/studio/backend/tests/services/test_gateway_resolver_bridge.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py \
  -q --tb=short
```

Expected after implementation: all tests pass.

### 2. Step 4 Target Regression

Run:

```bash
uv run pytest \
  apps/studio/backend/tests/core/adapters/test_productization_http_transport_errors_red.py \
  apps/studio/backend/tests/core/adapters/test_productization_import_boundary_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py \
  apps/studio/backend/tests/routers/test_productization_publish_artifact_red.py \
  apps/studio/backend/tests/services/test_productization_publish_atomicity_red.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_golden_headless_red.py \
  apps/studio/backend/tests/routers/test_productization_resume_adapter_red.py \
  apps/studio/backend/tests/services/test_productization_graph_roundtrip_red.py \
  -q --tb=short
```

Expected after implementation: all tests pass.

### 3. Step 1/2 Regression

Run:

```bash
uv run pytest \
  apps/studio/backend/tests/core/adapters/test_productization_adapters.py \
  apps/studio/backend/tests/core/adapters/test_productization_local_providers.py \
  apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py \
  apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py \
  -q --tb=short
```

Expected after implementation: all tests pass.

### 4. Ruff

Run:

```bash
uv run ruff check \
  apps/studio/backend/app/core/adapters/gateway.py \
  apps/studio/backend/app/core/adapters/engine.py \
  apps/studio/backend/app/services/gateway_resolver.py \
  apps/studio/backend/tests/services/test_gateway_resolver_bridge.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py
```

Expected after implementation: `All checks passed!`

### 5. Scope Guard

Run:

```bash
git diff --name-only -- \
  packages/graph-agent \
  packages/graph-agent-gateway \
  docs/studio \
  docs/engine \
  docs/graph-agent-gateway \
  uv.lock
```

Expected: no output.

### 6. Status

Run:

```bash
git status --short
```

Use this to report the final modified file list. Pre-existing Step 4 dirty files may already exist in this worktree; do not revert unrelated work.

## Required Self-Review Report

After implementation, report to Studio PM:

- Modified file list.
- Which changes are interface/protocol boundary fixes.
- Which changes are Studio owner-side production path fixes.
- Contract GREEN pytest output summary.
- Step 4 target pytest output summary.
- Step 1/2 regression pytest output summary.
- Ruff output summary.
- Scope guard output summary.
- `git status --short` summary.
- Confirmation that `packages/graph-agent/**`, `packages/graph-agent-gateway/**`, frozen docs, and `uv.lock` were not modified.
- Risks and unresolved items.
- `Ready for Studio PM self-review: Yes/No`.

## Ready for Codex Review

Yes.
