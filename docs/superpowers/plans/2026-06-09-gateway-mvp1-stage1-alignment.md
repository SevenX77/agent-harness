# Gateway MVP1 Stage 1 Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the confirmed hard-conflict slice of Gateway MVP1 code and docs back into alignment.

**Architecture:** Keep changes narrow: registry canonicalization stays in `graph_agent_gateway.registry`, route handoff APIs continue to surface through the package boundary, and Studio callers use `ModelResolver.resolve_routes` instead of directly calling pure registry helpers. Docs are updated only where they contradict implemented code or this Stage 1 fix.

**Tech Stack:** Python, pytest, FastAPI service modules, Gateway registry/resolver package, Markdown docs.

---

### Task 1: Endpoint-Scoped Model Alias

**Files:**
- Modify: `packages/graph-agent-gateway/tests/test_registry_canonical.py`
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py`
- Docs: `docs/graph-agent-gateway/mvp1/04-orch-registry-schema/mvp1-alignment.md`

- [ ] **Step 1: Write the failing test**

Add a test proving two endpoints can map the same provider model id to different canonical ids through explicit aliases:

```python
def test_canonicalize_model_uses_endpoint_scoped_explicit_aliases() -> None:
    aliases = {
        "endpoint-a:vendor/model": "alpha-model",
        "endpoint-b:vendor/model": "beta-model",
    }

    assert canonicalize_model("endpoint-a", "vendor/model", explicit_aliases=aliases).canonical_id == "alpha-model"
    assert canonicalize_model("endpoint-b", "vendor/model", explicit_aliases=aliases).canonical_id == "beta-model"
```

- [ ] **Step 2: Run red test**

Run: `uv run pytest packages/graph-agent-gateway/tests/test_registry_canonical.py::test_canonicalize_model_uses_endpoint_scoped_explicit_aliases -q`

Expected: FAIL because current code ignores `endpoint_id`.

- [ ] **Step 3: Implement minimal fix**

Teach `canonicalize_model` to prefer `"{endpoint_id}:{provider_model_id}"` aliases and fall back to legacy provider-model aliases.

- [ ] **Step 4: Run green test**

Run: `uv run pytest packages/graph-agent-gateway/tests/test_registry_canonical.py -q`

Expected: PASS.

### Task 2: Route Handoff Public Exports

**Files:**
- Modify: `packages/graph-agent-gateway/tests/test_gateway_package_boundary.py`
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py`
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py`
- Docs: `docs/graph-agent-gateway/mvp1/01-handoff-interface/mvp1-alignment.md`
- Docs: `docs/graph-agent-gateway/mvp1/04-orch-registry-schema/mvp1-alignment.md`

- [ ] **Step 1: Write the failing tests**

Add tests proving `ResolvedRole` and `ResolvedRoute` are importable from package root, and `SkippedRoute` is importable from `graph_agent_gateway.registry`.

- [ ] **Step 2: Run red tests**

Run: `uv run pytest packages/graph-agent-gateway/tests/test_gateway_package_boundary.py -q`

Expected: FAIL on missing public exports.

- [ ] **Step 3: Implement minimal exports**

Import and list the handoff DTOs in the package `__all__` values without exporting factory internals.

- [ ] **Step 4: Run green tests**

Run: `uv run pytest packages/graph-agent-gateway/tests/test_gateway_package_boundary.py -q`

Expected: PASS.

### Task 3: Studio Registry Callers Use ModelResolver

**Files:**
- Modify: `apps/studio/backend/tests/services/test_copilot_event_translator.py` or add a focused service test file
- Modify: `apps/studio/backend/tests/routers/test_llm_registry_api.py` or add a focused router test file
- Modify: `apps/studio/backend/app/services/copilot.py`
- Modify: `apps/studio/backend/app/routers/llm.py`
- Docs: `docs/graph-agent-gateway/mvp1/02-orch-role-resolution/mvp1-alignment.md`
- Docs: `docs/graph-agent-gateway/mvp1/01-handoff-interface/mvp1-alignment.md`

- [ ] **Step 1: Write failing tests**

Add focused tests that monkeypatch `ModelResolver.resolve_routes` and prove `_resolve_copilot_runtime` plus `_role_effective_runtime_settings` go through that method.

- [ ] **Step 2: Run red tests**

Run the exact new tests with `uv run pytest ... -q`.

Expected: FAIL because current Studio callers directly use `resolve_role`.

- [ ] **Step 3: Implement minimal wiring**

Instantiate `ModelResolver` with the same snapshot and credential provider context and call `resolve_routes` for the runtime/registry handoff.

- [ ] **Step 4: Run green tests**

Run the new focused Studio tests and the Gateway resolver/package tests.

Expected: PASS for the touched behavior.

### Task 4: Documentation Sync

**Files:**
- Modify: `docs/graph-agent-gateway/mvp1/03-orch-credentials-endpoints/mvp1-alignment.md`
- Modify: `docs/graph-agent-gateway/mvp1/05-orch-capabilities-and-models/mvp1-alignment.md`
- Modify: `docs/graph-agent-gateway/mvp1/06-orch-error-classification/baseline.md`
- Modify: `docs/graph-agent-gateway/mvp1/06-orch-error-classification/mvp1-alignment.md`
- Modify the docs from Tasks 1-3 as needed

- [ ] **Step 1: Patch stale claims**

Replace stale "待补" statements where code/tests already satisfy MVP1: base URL canonicalization, four-state capability projection, ChatX A' fallback/non-capability tests, route handoff exports, and endpoint-scoped alias handling.

- [ ] **Step 2: Scan for recurring stale phrases**

Run: `rg -n "待补|尚未|未完成|TODO|resolve_routes|四态|canonicalize_base_url|ChatX" docs/graph-agent-gateway/mvp1`

Expected: Any remaining "not done" language should describe real Stage 2 work, not Stage 1 contradictions.

### Task 5: Verification

**Files:**
- No new files beyond tests/docs/code listed above.

- [ ] **Step 1: Run focused package tests**

Run: `uv run pytest packages/graph-agent-gateway/tests/test_registry_canonical.py packages/graph-agent-gateway/tests/test_gateway_package_boundary.py -q`

- [ ] **Step 2: Run focused Studio tests**

Run the exact new Studio tests added in Task 3.

- [ ] **Step 3: Run doc lock tests**

Run: `uv run pytest packages/graph-agent-gateway/tests/test_gateway_doc_locks.py -q`

- [ ] **Step 4: Report Stage 2 residuals**

Summarize only confirmed remaining design-decision conflicts that require larger migrations, without claiming they are fixed.
