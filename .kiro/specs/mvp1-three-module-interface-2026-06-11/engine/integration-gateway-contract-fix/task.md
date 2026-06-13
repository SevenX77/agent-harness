---
spec_id: mvp1-three-module-interface-2026-06-11
module: engine
phase: integration-gateway-contract-fix
phase_name: Engine integration Gateway Step 4 contract GREEN
role: Engine PM
status: ready-for-codex-review
created: 2026-06-11
worktree: /Users/sevenx/Documents/coding/agent-harness/.worktrees/mvp1-three-module-integration-2026-06-11
branch: codex/mvp1-three-module-integration-2026-06-11
approved_red_report: .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/integration-gateway-contract-red-report.md
---

# Engine Integration Gateway Contract Fix Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The integration RED test has already been reviewed by Codex. Do not weaken the RED test. Do not start implementation until Codex approves this `task.md` and `gemini-prompt.md`.

## Goal

Make Engine's default Predict resolver path compatible with Gateway Step 4's `ModelResolver(config_store=..., user_id=...)` contract, or require an explicitly injected resolver, so Engine no longer constructs `ModelResolver(registry_snapshot=...)`.

## Architecture

The current integration defect is isolated to Engine's `predict_skill(...)` default `model_resolver is None` branch in `packages/graph-agent/src/graph_agent/core/runner.py`. Gateway has removed the old `registry_snapshot=...` constructor from `graph_agent_gateway.resolver.ModelResolver`; Engine must stop using that constructor. The fix must keep Gateway-owned model resolution behind the new Gateway Step 4 contract or behind caller injection, without reintroducing old snapshot construction under a helper.

## Non-Goals

- Do not change Studio code.
- Do not change Gateway code.
- Do not change FROZEN docs.
- Do not change `uv.lock`.
- Do not change approved RED tests unless Codex explicitly asks for a mechanical correction.
- Do not add Gateway compatibility for `registry_snapshot=...`.
- Do not hide the old Gateway snapshot constructor in another Engine helper.
- Do not use string-building or dynamic attribute tricks to bypass the static RED test.

## Allowed Files

- Modify: `packages/graph-agent/src/graph_agent/core/runner.py`

Only if a narrow existing test expectation requires an import/export adjustment:

- Modify: `packages/graph-agent/tests/core/test_predict_internal_imports.py`

Planning artifacts:

- Create: `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/integration-gateway-contract-fix/task.md`
- Create: `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/integration-gateway-contract-fix/gemini-prompt.md`

## Forbidden Files

- `apps/studio/**`
- `packages/graph-agent-gateway/**`
- `docs/engine/**`
- `docs/graph-agent-gateway/**`
- `docs/studio/**`
- `uv.lock`
- `packages/graph-agent/src/graph_agent/core/artifacts.py`
- `packages/graph-agent/src/graph_agent/core/adapter_contracts.py`
- `packages/graph-agent/src/graph_agent/core/event_contracts.py`
- `packages/graph-agent/src/graph_agent/core/llm_provider.py`
- `packages/graph-agent/src/graph_agent/core/runtime_state.py`
- `packages/graph-agent/src/graph_agent/core/storage_contracts.py`

If a green fix appears to require any forbidden path, stop and report the blocker.

## Approved RED

Command:

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_predict_internal_imports.py \
  packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py \
  -q --tb=short
```

Expected current result before implementation:

```text
1 failed, 3 passed
```

Required failure:

```text
test_engine_default_predict_resolver_uses_gateway_step4_contract
```

The failure must point to:

```text
packages/graph-agent/src/graph_agent/core/runner.py still contains ModelResolver(registry_snapshot=snapshot)
```

## Implementation Choices

Choose one of the following. Do not mix in the removed `registry_snapshot=...` constructor.

### Option A: Prefer Explicit Resolver Injection

Remove Engine's default Gateway resolver construction from `predict_skill(...)`. When `model_resolver is None`, leave it as `None` and rely on Predict's mock/interception path and existing graph assembly behavior.

This is the smallest Engine-owned fix if existing core tests remain green.

Expected code shape:

```python
compiled = compile_skill(skill_path_obj, skill_resolver=resolver)

if model_resolver is None:
    model_resolver = None
```

The final implementation can omit the redundant branch entirely if doing so is clearer:

```python
compiled = compile_skill(skill_path_obj, skill_resolver=resolver)
```

Do not replace it with another default resolver that depends on the old Gateway snapshot contract.

### Option B: Gateway Step 4 Config Store Adapter

If tests prove Engine still needs a default Gateway resolver in this path, construct Gateway's resolver only with its Step 4 signature:

```python
ModelResolver(config_store=config_store, user_id=user_id)
```

The `config_store` must provide both Gateway truth-store records:

```python
credentials = {
    "schema_version": 4,
    "provider_endpoints": {
        "mock-endpoint": {
            "endpoint_id": "mock-endpoint",
            "protocol": "openai_compatible",
            "base_url": "http://localhost",
            "api_key": "mock-key",
        }
    },
    "provider_routes": {
        "mock-endpoint:mock-route": {
            "route_id": "mock-endpoint:mock-route",
            "endpoint_id": "mock-endpoint",
            "route_slug": "mock-route",
            "provider_model_id": "mock-model",
            "canonical_id": "mock-model",
            "status": "verified",
        }
    },
    "runtime_policy": {},
}
```

```python
roles = {
    "schema_version": 2,
    "roles": {
        phase_name: {
            "fallback_chain": [{"route_id": "mock-endpoint:mock-route"}],
        }
        for phase_name in compiled.manifest.phases
    }
    | {
        "graph_agent": {
            "fallback_chain": [{"route_id": "mock-endpoint:mock-route"}],
        }
    },
}
```

Use Gateway's real `ConfigTruthStore` contract, such as `InMemoryConfigTruthStore`, if this option is selected. Keep all Gateway imports lazy inside the default resolver branch so `import graph_agent` does not import `graph_agent_gateway`.

## Task Steps

### Task 1: Confirm RED Still Targets Engine Production Path

**Files:**

- Read: `packages/graph-agent/tests/core/test_predict_internal_imports.py`
- Read: `packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py`
- Read: `packages/graph-agent/src/graph_agent/core/runner.py`

- [ ] **Step 1: Run the approved RED**

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_predict_internal_imports.py \
  packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py \
  -q --tb=short
```

Expected:

```text
1 failed, 3 passed
```

- [ ] **Step 2: Confirm failure reason**

The only failing test must be:

```text
test_engine_default_predict_resolver_uses_gateway_step4_contract
```

The failure must mention:

```text
ModelResolver(registry_snapshot=snapshot)
```

If the failure is from test fixture construction or import errors, stop and report.

### Task 2: Remove The Old Gateway Constructor From Engine

**Files:**

- Modify: `packages/graph-agent/src/graph_agent/core/runner.py`

- [ ] **Step 1: Edit the default resolver branch**

In `predict_skill(...)`, remove the block that imports these Gateway snapshot schema classes:

```python
ProviderEndpoint
ProviderRoute
RegistrySnapshot
RoleEntry
RoleRouteEntry
```

Remove the call:

```python
ModelResolver(registry_snapshot=snapshot)
```

Apply Option A first. If Option A breaks existing tests for a real behavior reason, apply Option B.

- [ ] **Step 2: Keep resolver injection intact**

The existing function argument must remain:

```python
model_resolver: Any | None = None
```

Calls that pass a resolver must still reach `assemble_graph(..., model_resolver=model_resolver, ...)`.

- [ ] **Step 3: Static check for the removed constructor**

Run:

```bash
rg -n "ModelResolver\\(registry_snapshot|registry_snapshot=snapshot" packages/graph-agent/src/graph_agent/core/runner.py
```

Expected:

```text
no output
```

### Task 3: Prove Integration GREEN And Existing Predict Behavior

**Files:**

- Test: `packages/graph-agent/tests/core/test_predict_internal_imports.py`
- Test: `packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py`
- Test: `packages/graph-agent/tests/core/test_predict_runner_binding.py`

- [ ] **Step 1: Run the integration contract tests**

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_predict_internal_imports.py \
  packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py \
  -q --tb=short
```

Expected:

```text
4 passed
```

- [ ] **Step 2: Run existing predict resolver binding tests**

```bash
uv run pytest packages/graph-agent/tests/core/test_predict_runner_binding.py -q
```

Expected: pass.

If Option A causes a binding regression, use Option B and rerun both commands.

### Task 4: Final Verification

**Files:**

- Verify: Engine core tests and integration guards

- [ ] **Step 1: Preflight**

```bash
uv run python -c 'import graph_agent; from inspect import signature; from graph_agent_gateway.resolver import ModelResolver; missing = [name for name in ("compile_artifact", "run_artifact", "predict_artifact") if not hasattr(graph_agent, name)]; print("missing_engine_artifact_api:", missing); print("gateway_model_resolver_signature:", signature(ModelResolver))'
```

Expected:

```text
missing_engine_artifact_api: []
gateway_model_resolver_signature: (*, config_store: ...
```

- [ ] **Step 2: Engine core gate**

```bash
uv run pytest packages/graph-agent/tests/core -q
```

Expected: pass, with the same expected `xpassed` count already present in the integration worktree.

- [ ] **Step 3: Ruff**

```bash
uv run ruff check \
  packages/graph-agent/src/graph_agent/core/runner.py \
  packages/graph-agent/tests/core/test_predict_internal_imports.py \
  packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 4: Scope guard**

```bash
git diff --name-only -- \
  packages/graph-agent-gateway \
  apps/studio \
  docs/engine \
  docs/graph-agent-gateway \
  docs/studio \
  uv.lock
```

Expected: no new files from this fix. If the command shows existing integration-synced diffs, identify them as pre-existing and confirm this fix did not modify them.

- [ ] **Step 5: Whitespace check**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Status**

```bash
git status --short -uall
```

Expected: this fix modifies only `packages/graph-agent/src/graph_agent/core/runner.py` plus this approved planning directory. Existing integration aggregate changes may remain visible.

## Done Criteria

- The approved integration RED command is GREEN.
- `runner.py` no longer contains `ModelResolver(registry_snapshot`.
- Engine does not hide the removed Gateway snapshot constructor in a helper.
- Existing resolver injection behavior remains intact.
- Gateway Step 4 constructor shape remains `config_store + user_id`.
- No Studio/Gateway/FROZEN-doc/`uv.lock` files are modified by this fix.
- Gemini implementation report includes command outputs, scope guard summary, and `git status --short -uall`.
