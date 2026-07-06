# Studio Request Audit

Status: Living

This document tracks the audit requested for every Studio frontend request and
backend route against the project rule:

**Server-authoritative state + event-driven revalidation.** Mutable truth is read
from the server-owned source on first need for a cache key, then revalidated only
after a successful canonical write, a precise backend domain event, or an
explicit user refresh/probe/test action. UI visibility or selection state is not
truth mutation.

## Decision Rules

Allowed request triggers:

- Cold load: the first consumer of a cache key may read it once and share the
  in-flight request/result.
- Successful write: the writer may use the returned canonical snapshot or
  invalidate the exact affected cache key.
- Backend event: a committed backend change may emit a precise domain event that
  invalidates the exact affected key.
- Explicit user action: refresh, test, probe, run, compile, save, delete, import,
  export, or similar commands may call the backend.
- Scoped job status: a long-running job may use its own status stream or scoped
  polling key. It must not refresh broad truth such as registry/roles/settings as
  a progress substitute.

Forbidden request triggers:

- Component mount/unmount after the cache key is already loaded.
- Opening or closing Settings, Copilot, sidebars, drawers, tabs, or panels.
- Canvas node/edge selection, hover, focus, scroll, resize, or tab switch.
- Window focus, timer polling, WebSocket connect/reconnect, or generic resync.
- Sending implicit UI state to the backend just because the user looked at or
  selected something.

## Test Strategy

Use a shared test when it protects an architectural boundary:

- Static guard tests for deleted/forbidden request channels, such as the removed
  Copilot auto-context endpoint.
- Network-silent interaction tests for UI-only actions after cold data is loaded,
  such as node selection, panel open/close, tab switch, and dialog reopen.
- API client cache tests for shared in-flight/cold-load semantics and precise
  invalidation.
- Backend route tests when an endpoint must not exist, or when a write/event must
  be the only source of a revalidation trigger.

Use per-request tests when a request has unique semantics:

- Autosave ordering and stale-response suppression.
- Job/probe lifecycle and scoped polling.
- File writes, hash conflicts, native-fs ownership, and destructive commands.
- Provider/role/registry writes that must return and project a canonical server
  snapshot.

## Audit Ledger

| Area | Request/route | Current trigger | Verdict | Guard |
| --- | --- | --- | --- | --- |
| Copilot canvas context | `POST /api/skills/{skill_id}/copilot/context` | Canvas selection/render sent selected node/edge/lint state | Removed. UI selection is not truth mutation and must not be sent implicitly. | `CopilotContext.network-side-effect.test.ts`, `test_copilot_context_endpoint_removed.py` |
| Properties node config | `GET /api/skills/{skill_id}/node-llm-params` | Properties panel cold load | OK if shared per skill and silent on node selection after load. | `PropertiesPanel.network-side-effect.test.tsx`, client cache tests |
| Properties compare candidates | `GET /api/skills/{skill_id}/compare-candidates` | Properties panel cold load | OK if shared per skill and silent on node selection after load. | `PropertiesPanel.network-side-effect.test.tsx`, client cache tests |
| Settings app settings | `GET/PUT /api/settings` | App settings initialization / user save | OK: the hook waits for authenticated API readiness before the first read, shares the cold-load request, and saves only after explicit settings edits. | `useAppSettings.test.ts` |
| LLM registry | `GET /api/llm/registry` | Settings/API Keys/roles consumers and domain events | Partial: client reads are cached/deduped; Settings open/close, tab switch, focus, and WebSocket connect/reconnect are guarded as non-triggers. Remaining audit: all registry write paths must keep returning/projecting exact canonical snapshots. | `llm.test.ts`, `SettingsPage.controller.test.tsx`, `useStudioEventStream.test.ts` |
| LLM roles | `GET/PUT /api/llm/roles` | Settings/Copilot role consumers and role writes/events | Partial: roles reads are cached/deduped; Settings open/close, tab switch, focus, and WebSocket connect/reconnect are guarded as non-triggers. Remaining audit: role write/test/job paths need route-by-route review. | `SettingsPage.controller.test.tsx`, `useStudioEventStream.test.ts` |
| Templates | `GET /api/templates` | Template UI | Pending audit: should load only when template UI is opened or a template is used. | Required if it is mounted globally |
| Studio event stream | `WS /ws/events` | App-level domain event stream | OK for the generic-resync risk: connect/reconnect do not dispatch data refresh callbacks; only precise backend events invoke the exact handlers. | `useStudioEventStream.test.ts` |
| Copilot chat | `WS /api/skills/{skill_id}/copilot/ws` | User sends a Copilot message | OK as explicit user action; future `@` mentions must travel with the message payload, not background UI state. | Required when `@` mention payload is implemented |

## Machine-Readable Inventory Ledger

The fenced block below is the static coverage contract enforced by
`apps/studio/backend/tests/docs/test_studio_request_audit_ledger.py`. It is not
a claim that every key is already OK; it guarantees every current frontend
request and backend route is explicitly present in this audit document before
more specific verdict and guard tests are added.

```studio-request-audit-ledger
BACKEND DELETE /api/llm/model-bundles/{bundle_id}
BACKEND DELETE /api/llm/model-profiles/{model_profile_id}
BACKEND DELETE /api/llm/registry/endpoints/{endpoint_id}
BACKEND DELETE /api/llm/roles/{role_name}
BACKEND DELETE /api/llm/routes/{route_id}
BACKEND DELETE /api/skills/{skill_id}
BACKEND DELETE /api/skills/{skill_id}/golden/{golden_id}
BACKEND DELETE /api/skills/{skill_id}/runs/{run_id}
BACKEND DELETE /api/skills/{skill_id}/test_inputs/{input_id}
BACKEND GET /api/_debug/value-error
BACKEND GET /api/batch/{batch_id}
BACKEND GET /api/llm/fixed-roles
BACKEND GET /api/llm/fixed-roles/{role_name}
BACKEND GET /api/llm/model-profiles
BACKEND GET /api/llm/providers/notable-models
BACKEND GET /api/llm/registry
BACKEND GET /api/llm/registry/endpoints/{endpoint_id}/secret
BACKEND GET /api/llm/role-test-jobs/{job_id}
BACKEND GET /api/llm/roles
BACKEND GET /api/llm/roles/test-results
BACKEND GET /api/llm/roles/{role_name}
BACKEND GET /api/settings
BACKEND GET /api/skills/{skill_id}
BACKEND GET /api/skills/{skill_id}/compare-candidates
BACKEND GET /api/skills/{skill_id}/golden
BACKEND GET /api/skills/{skill_id}/golden/template
BACKEND GET /api/skills/{skill_id}/golden/{golden_id}/content
BACKEND GET /api/skills/{skill_id}/history
BACKEND GET /api/skills/{skill_id}/node-llm-params
BACKEND GET /api/skills/{skill_id}/releases
BACKEND GET /api/skills/{skill_id}/releases/{release_version}
BACKEND GET /api/skills/{skill_id}/runs
BACKEND GET /api/skills/{skill_id}/runs/compare/{compare_group_id}
BACKEND GET /api/skills/{skill_id}/runs/{run_id}
BACKEND GET /api/skills/{skill_id}/runs/{run_id}/audit
BACKEND GET /api/skills/{skill_id}/runs/{run_id}/compare
BACKEND GET /api/skills/{skill_id}/runs/{run_id}/diff
BACKEND GET /api/skills/{skill_id}/subgraph
BACKEND GET /api/skills/{skill_id}/test_inputs
BACKEND GET /api/skills/{skill_id}/test_inputs/{input_id}
BACKEND GET /api/system/community-catalog-config
BACKEND GET /api/system/truth-sources
BACKEND GET /api/system/truth-sources/{source_id}/content
BACKEND GET /api/templates
BACKEND GET /health
BACKEND POST /api/copilot/roles/{role_name}/test-sdk
BACKEND POST /api/io/scan
BACKEND POST /api/llm/catalog/contribute
BACKEND POST /api/llm/catalog/repository/ensure
BACKEND POST /api/llm/catalog/share
BACKEND POST /api/llm/catalog/sync
BACKEND POST /api/llm/catalog/sync-verified
BACKEND POST /api/llm/endpoints/{endpoint_id}/models/test
BACKEND POST /api/llm/endpoints/{endpoint_id}/test
BACKEND POST /api/llm/model-bundles/{bundle_id}/test-jobs
BACKEND POST /api/llm/model-groups/test-jobs
BACKEND POST /api/llm/roles/{role_name}/apply-profile
BACKEND POST /api/llm/roles/{role_name}/test
BACKEND POST /api/llm/roles/{role_name}/test-jobs
BACKEND POST /api/llm/routes/{route_id}/probe
BACKEND POST /api/llm/routes/{route_id}/probe-multimodal
BACKEND POST /api/skills
BACKEND POST /api/skills/{skill_id}/compile
BACKEND POST /api/skills/{skill_id}/copilot/dispatch
BACKEND POST /api/skills/{skill_id}/copilot/interrupt
BACKEND POST /api/skills/{skill_id}/copilot/judge
BACKEND POST /api/skills/{skill_id}/copilot/tool-approval
BACKEND POST /api/skills/{skill_id}/files/{file_path:path}
BACKEND POST /api/skills/{skill_id}/fork
BACKEND POST /api/skills/{skill_id}/golden
BACKEND POST /api/skills/{skill_id}/golden/manual/plan
BACKEND POST /api/skills/{skill_id}/golden/plan
BACKEND POST /api/skills/{skill_id}/graph/serialize
BACKEND POST /api/skills/{skill_id}/io/import
BACKEND POST /api/skills/{skill_id}/lint
BACKEND POST /api/skills/{skill_id}/publish
BACKEND POST /api/skills/{skill_id}/releases/{release_version}/runs
BACKEND POST /api/skills/{skill_id}/revert
BACKEND POST /api/skills/{skill_id}/runs
BACKEND POST /api/skills/{skill_id}/runs/batch-run
BACKEND POST /api/skills/{skill_id}/runs/predict
BACKEND POST /api/skills/{skill_id}/runs/{base_run_id}/compare
BACKEND POST /api/skills/{skill_id}/runs/{run_id}/compare
BACKEND POST /api/skills/{skill_id}/runs/{run_id}/resume
BACKEND POST /api/skills/{skill_id}/runs/{run_id}/resume/validity
BACKEND POST /api/skills/{skill_id}/sync
BACKEND POST /api/skills/{skill_id}/terminal
BACKEND POST /api/skills/{skill_id}/test_inputs
BACKEND POST /api/skills/{skill_id}/validate_input
BACKEND POST /engine/compile
BACKEND POST /engine/predict_artifact
BACKEND POST /engine/resume
BACKEND POST /engine/resume_validity
BACKEND POST /engine/run_artifact
BACKEND POST /gateway/decide_fallback
BACKEND POST /gateway/materialize_model_bundle
BACKEND POST /gateway/materialize_role
BACKEND POST /gateway/project_route_state
BACKEND POST /gateway/resolve_credential
BACKEND POST /gateway/resolve_routes
BACKEND POST /shutdown
BACKEND PUT /api/llm/model-profiles
BACKEND PUT /api/llm/registry/endpoints
BACKEND PUT /api/llm/roles
BACKEND PUT /api/llm/roles/{role_name}
BACKEND PUT /api/llm/routes/{route_id}
BACKEND PUT /api/settings
BACKEND PUT /api/skills/{skill_id}
BACKEND PUT /api/skills/{skill_id}/nodes/{node_id}/compare-candidates
BACKEND PUT /api/skills/{skill_id}/nodes/{node_id}/node-llm-params
BACKEND WS /api/skills/{skill_id}/copilot/ws
BACKEND WS /ws/events
BACKEND WS /ws/runs/{run_id}
BACKEND WS /ws/terminal/{term_id}
FRONTEND DELETE /api/llm/model-bundles/{bundle_id}
FRONTEND DELETE /api/llm/registry/endpoints/{endpoint_id}
FRONTEND DELETE /api/llm/roles/{role_name}
FRONTEND DELETE /api/llm/routes/{route_id}
FRONTEND DELETE /api/skills/{skill_id}/runs/{run_id}
FRONTEND DELETE /api/skills/{skill_id}/test_inputs/{input_id}
FRONTEND GET /api/llm/fixed-roles
FRONTEND GET /api/llm/fixed-roles/{role_name}
FRONTEND GET /api/llm/providers/notable-models
FRONTEND GET /api/llm/registry
FRONTEND GET /api/llm/registry/endpoints/{endpoint_id}/secret
FRONTEND GET /api/llm/role-test-jobs/{job_id}
FRONTEND GET /api/llm/roles
FRONTEND GET /api/llm/roles/test-results
FRONTEND GET /api/llm/roles/{role_name}
FRONTEND GET /api/settings
FRONTEND GET /api/skills/{skill_id}
FRONTEND GET /api/skills/{skill_id}/compare-candidates
FRONTEND GET /api/skills/{skill_id}/golden
FRONTEND GET /api/skills/{skill_id}/golden/template
FRONTEND GET /api/skills/{skill_id}/golden/{golden_id}/content
FRONTEND GET /api/skills/{skill_id}/history
FRONTEND GET /api/skills/{skill_id}/node-llm-params
FRONTEND GET /api/skills/{skill_id}/releases
FRONTEND GET /api/skills/{skill_id}/releases/{release_version}
FRONTEND GET /api/skills/{skill_id}/runs/compare/{compare_group_id}
FRONTEND GET /api/skills/{skill_id}/runs/{run_id}
FRONTEND GET /api/skills/{skill_id}/runs/{run_id}/compare
FRONTEND GET /api/skills/{skill_id}/subgraph
FRONTEND GET /api/skills/{skill_id}/test_inputs/{input_id}
FRONTEND GET /api/system/community-catalog-config
FRONTEND GET /api/system/truth-sources
FRONTEND GET /api/system/truth-sources/{source_id}/content
FRONTEND POST /api/io/scan
FRONTEND POST /api/llm/catalog/sync-verified
FRONTEND POST /api/llm/endpoints/{endpoint_id}/models/test
FRONTEND POST /api/llm/endpoints/{endpoint_id}/test
FRONTEND POST /api/llm/model-bundles/{bundle_id}/test-jobs
FRONTEND POST /api/llm/model-groups/test-jobs
FRONTEND POST /api/llm/roles/{role_name}/test
FRONTEND POST /api/llm/roles/{role_name}/test-jobs
FRONTEND POST /api/llm/routes/{route_id}/probe
FRONTEND POST /api/llm/routes/{route_id}/probe-multimodal
FRONTEND POST /api/skills/{skill_id}/compile
FRONTEND POST /api/skills/{skill_id}/copilot/interrupt
FRONTEND POST /api/skills/{skill_id}/copilot/judge
FRONTEND POST /api/skills/{skill_id}/copilot/tool-approval
FRONTEND POST /api/skills/{skill_id}/files/{file_path:path}
FRONTEND POST /api/skills/{skill_id}/golden
FRONTEND POST /api/skills/{skill_id}/golden/manual/plan
FRONTEND POST /api/skills/{skill_id}/golden/plan
FRONTEND POST /api/skills/{skill_id}/graph/serialize
FRONTEND POST /api/skills/{skill_id}/io/import
FRONTEND POST /api/skills/{skill_id}/lint
FRONTEND POST /api/skills/{skill_id}/publish
FRONTEND POST /api/skills/{skill_id}/revert
FRONTEND POST /api/skills/{skill_id}/runs
FRONTEND POST /api/skills/{skill_id}/runs/predict
FRONTEND POST /api/skills/{skill_id}/runs/{base_run_id}/compare
FRONTEND POST /api/skills/{skill_id}/runs/{run_id}/resume
FRONTEND POST /api/skills/{skill_id}/runs/{run_id}/resume/validity
FRONTEND POST /api/skills/{skill_id}/sync
FRONTEND POST /api/skills/{skill_id}/test_inputs
FRONTEND POST /api/skills/{skill_id}/validate_input
FRONTEND PUT /api/llm/registry/endpoints
FRONTEND PUT /api/llm/roles
FRONTEND PUT /api/settings
FRONTEND PUT /api/skills/{skill_id}/nodes/{node_id}/compare-candidates
FRONTEND PUT /api/skills/{skill_id}/nodes/{node_id}/node-llm-params
FRONTEND WS /api/skills/{skill_id}/copilot/ws
FRONTEND WS /ws/events
FRONTEND WS /ws/runs/{run_id}
```

## Audit Procedure

1. Inventory requests with:
   `rg -n "api\\.(get|post|put|delete|patch)|useSWR\\(|new WebSocket|wsUrl\\(" apps/studio/frontend/src`
2. Inventory backend routes with:
   `rg -n "@(router|app)\\.(get|post|put|delete|patch|websocket)" apps/studio/backend/app/routers`
3. For each request, record the trigger, server-owned truth key, invalidation
   source, and whether it needs a shared or per-request test.
4. Any request triggered by UI visibility, selection, focus, timer, reconnect, or
   generic resync is a defect until redesigned or proven scoped to an explicit
   user command/job.
