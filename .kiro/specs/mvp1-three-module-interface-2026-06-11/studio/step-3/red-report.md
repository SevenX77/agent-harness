## Studio PM RED Report - Step 3

Worktree:
`/Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-studio-mvp1-interface-2026-06-11`

Branch:
`codex/pm-studio-mvp1-interface-2026-06-11`

Changed tests:
- `apps/studio/backend/tests/core/adapters/test_productization_http_transport_errors_red.py`
- `apps/studio/backend/tests/core/adapters/test_productization_import_boundary_red.py`
- `apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py`
- `apps/studio/backend/tests/routers/test_productization_publish_artifact_red.py`
- `apps/studio/backend/tests/services/test_productization_publish_atomicity_red.py`
- `apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py`
- `apps/studio/backend/tests/services/test_productization_golden_headless_red.py`
- `apps/studio/backend/tests/routers/test_productization_resume_adapter_red.py`
- `apps/studio/backend/tests/services/test_productization_graph_roundtrip_red.py`

Command:
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
  -q
```

Expected RED:
- HTTP 5xx must preserve `ResponseEnvelope` error payload instead of collapsing to generic `transport.http_5xx`.
- Timeout retry with the same `Idempotency-Key` must not duplicate execution.
- Event stream reconnect must resume from cursor and dedupe repeated `seq`.
- Studio services must stop importing SDK internals directly and route through Studio adapters.
- run/predict must stop passing raw source `skill_path` into SDK runtime and must run through artifact refs.
- Artifact flow must expose hash verification and dev/prod missing-hash policy.
- `/publish` must write ProductArtifactStore releases instead of zipping source.
- publish must reject duplicate release versions and roll back visible releases on partial failure.
- copilot/settings must use `GatewayAdapter`; tests allow `GatewayAdapter.materialize_role(...)` and only forbid the old Studio local materializer/projection path.
- golden diff must use the headless adapter contract instead of `final_state.json` full-run diff.
- resume endpoint must stop returning 501 and delegate to `EngineAdapter.resume`.
- GRAPH parse/serialize must use a shared roundtrip boundary, and UI metadata must not affect execution fingerprint.

Actual output summary:
- `pytest`: `18 failed in 0.27s`.
- Failure families:
  - HTTP transport: 5xx envelope collapsed to `transport.http_5xx`; timeout is not retried; `stream_events` is missing.
  - import boundary: 28 service imports still point at `graph_agent` / `graph_agent_gateway`.
  - run/predict: `EngineAdapter` artifact flow is not used; `app.services.run_artifact_flow` is missing.
  - publish: route still does not reference `ProductArtifactStore`; atomic publisher/conflict/partial-failure types are missing. Atomicity tests use artifact refs shaped as `{"artifact_id": "...", "content_hash": "sha256:..."}`.
  - gateway: LLM router/materializer do not use `GatewayAdapter` and still expose old local materializer/projection paths.
  - golden: current service still uses `final_state.json` and `_diff_value`.
  - resume: endpoint still returns 501 and router does not delegate to `EngineAdapter.resume`.
  - GRAPH: service still imports `graph_agent.core.graph_serializer`; `app.services.graph_roundtrip` is missing.
- `ruff`: `All checks passed!`
- Scope guard:
  - `git diff --name-only -- packages/graph-agent packages/graph-agent-gateway docs/studio docs/engine docs/graph-agent-gateway uv.lock`
  - Output: no files.

Why this proves the old path/interface gap:
The RED suite exercises the owner-side business paths that Step 2 intentionally left open after defining the adapter/provider contracts. The failures show Studio still depends on direct SDK calls, source zipping, file-level golden diffs, non-atomic publish behavior, missing resume delegation, and missing GRAPH roundtrip isolation. These are not interface-definition failures anymore; they are the intended Step 4 owner-side GREEN targets.

Production code changed: No

Notes:
- This Step 3 RED pass only added the new RED tests plus this report.
- Codex review corrections applied: HTTP stream fixture now uses `json.dumps`; GatewayAdapter flow tests no longer forbid `GatewayAdapter.materialize_role(...)`; publish atomicity artifact refs now use `content_hash: "sha256:..."`.
- `git status --short` still shows previously approved Step 2 production files because they remain uncommitted in the same worktree; this Step 3 pass did not edit production code.

Risks / cross-module blockers:
- No Engine/Gateway production files, FROZEN docs, or `uv.lock` were changed.
- Step 4 implementation should keep Engine/Gateway behavior behind `EngineAdapter` / `GatewayAdapter`; any true cross-module contract gap should be escalated to Codex instead of patched directly in Studio.
- The service import-boundary RED is intentionally broad and currently reports all direct SDK imports under `app/services`; Step 4 may need to keep only DTO/model compatibility imports outside runtime service paths if Codex approves that nuance.
