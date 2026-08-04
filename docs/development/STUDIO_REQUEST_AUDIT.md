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
- Static guard tests for shared request-policy helpers, such as requiring every
  production `useSWR(...)` truth read to opt into `STUDIO_TRUTH_SWR_CONFIG`.
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
| Canvas node selection | left-panel reads such as `GET /api/skills/{skill_id}/node-llm-params`, `GET /api/skills/{skill_id}/runs`, `GET /api/skills/{skill_id}/test_inputs` | Repeated click on an already-selected phase node previously reopened the recorded side panel | Removed. Phase-node clicks are selection only; opening Properties/I/O/Timeline must be a toolbar action or an already-mounted panel projection. | `GraphCanvas.test.tsx` |
| Properties node config | `GET /api/skills/{skill_id}/node-llm-params` | Properties panel cold load | OK if shared per skill and silent on node selection after load. | `GraphCanvas.test.tsx`, `PropertiesPanel.network-side-effect.test.tsx`, client cache tests |
| Properties compare candidates | `GET /api/skills/{skill_id}/compare-candidates` | Properties panel cold load | OK if shared per skill and silent on node selection after load. | `GraphCanvas.test.tsx`, `PropertiesPanel.network-side-effect.test.tsx`, client cache tests |
| Runtime config | `GET /api/skills/{skill_id}/runtime-config`; `PUT /api/skills/{skill_id}/runtime-config/artifacts` | Workspace cold load/import-file events; explicit output artifact save | OK: runtime config is server-owned truth derived from `.workspace/import_files/` plus explicit runtime settings; frontend revalidates only after import file changes or artifact save. | Backend runtime-config/router tests, `Workspace.test.tsx`, `io-config.test.ts` |
| Settings app settings | `GET/PUT /api/settings` | App settings initialization / user save | OK: the hook waits for authenticated API readiness before the first read, shares the cold-load request, and saves only after explicit settings edits. | `useAppSettings.test.ts` |
| Settings truth sources | `GET /api/system/truth-sources`, `GET /api/system/community-catalog-config`, `GET /api/system/truth-sources/{source_id}/content` | General settings cold load / explicit source open preview fallback | OK: General cold-loads metadata once and the API client dedupes/cache-shares it; source content is only loaded after the user explicitly opens a source and native open falls back to preview. | `GeneralTab.lifecycle.test.tsx`, `client.test.ts` |
| Settings tab mounting | hidden tab reads such as `GET /api/llm/roles/test-results` | Settings rendered every tab while only one was visible | Fixed. Tabs are lazy-mounted on first visit and kept mounted afterward; opening API Keys no longer mounts LLM Roles/Copilot seed effects. | `SettingsPageContent.shell.test.tsx`, `SettingsPageContent.lazy-tabs.test.tsx` |
| Remote community catalog sync | `POST /api/llm/catalog/sync-verified` | Settings controller automatically synced after app settings loaded when the flag was enabled | Removed. Remote catalog sync is not a lifecycle side effect; any future sync must be an explicit user command or precise backend event path. | `SettingsPage.controller.test.tsx` |
| API key endpoint secrets | `GET /api/llm/registry/endpoints/{endpoint_id}/secret` | Explicit API Keys reveal/copy for one provider endpoint | OK: Settings/App/API Keys cold loads use the redacted registry snapshot only; no mount/open/tab switch/event refresh hydrates secrets. A single endpoint secret is read only after the user explicitly shows or copies that API key. | `llm.test.ts`, `SettingsPage.controller.test.tsx`, `ProviderCard.secret-reveal.test.tsx` |
| LLM fixed role metadata | `GET /api/llm/fixed-roles`, `GET /api/llm/fixed-roles/{role_name}` | First visible LLM Roles/Copilot consumer | OK: fixed-role names and recommended-model metadata are immutable backend projections; frontend lazy tab mounting prevents hidden Settings pages from reading them, and the API client dedupes/caches repeated consumers. | `test_llm_fixed_roles.py`, `llm.test.ts`, `SettingsPageContent.lazy-tabs.test.tsx` |
| Manual model suggestions | `GET /api/llm/providers/notable-models` | Explicitly opening the API Keys manual model probing accordion | OK: notable models are suggestion-only placeholder metadata, not runtime truth; the collapsed panel is silent, and candidates are cached per provider until explicit force refresh. | `test_llm_registry_api.py`, `ManualModelTestPanel.test.tsx`, `llm.test.ts` |
| LLM role test jobs | `POST /api/llm/roles/{role_name}/test-jobs`, `POST /api/llm/model-bundles/{bundle_id}/test-jobs`, `POST /api/llm/model-groups/test-jobs`, `GET /api/llm/role-test-jobs/{job_id}` | Explicit Test button / compare-candidate test action, then scoped job polling | OK: test jobs are explicit commands; polling is confined to the returned job id and never refreshes broad registry/roles/settings truth as a progress substitute. | `test_llm_registry_api.py`, `role-test-store.test.ts`, `copilot-role-test.test.ts`, `PropertiesPanel.network-side-effect.test.tsx`, `llm.test.ts` |
| LLM registry | `GET /api/llm/registry`, endpoint/route registry writes and probes | Settings/API Keys/roles consumers, explicit endpoint/route commands, and precise domain events | OK: reads are cached/deduped; Settings open/close, tab switch, focus, and WebSocket connect/reconnect are guarded as non-triggers. Registry write paths return canonical registry projections, and frontend projects those responses without a follow-up broad GET. | `llm.test.ts`, `test_llm_registry_api.py`, `SettingsPage.controller.test.tsx`, `useStudioEventStream.test.ts` |
| LLM roles | `GET/PUT /api/llm/roles`, `DELETE /api/llm/roles/{role_name}`, `DELETE /api/llm/model-bundles/{bundle_id}` | Settings/Copilot role consumers, role writes/events, explicit delete commands | OK for aggregate role reads/writes/deletes: roles reads are cached/deduped; Settings open/close, tab switch, focus, WebSocket connect/reconnect, and hidden API Keys tab mounts are guarded as non-triggers. Aggregate role mutations return `roles_data + registry` projection snapshots, so the client never follows writes with a broad `/llm/registry` read. Single-role and role-test command paths remain separately inventoried below. | `SettingsPage.controller.test.tsx`, `SettingsPageContent.lazy-tabs.test.tsx`, `useStudioEventStream.test.ts`, `llm.test.ts`, `test_llm_registry_api.py` |
| Templates | `GET /api/templates` | Create-skill Copilot empty-state template UI | OK: templates are disabled while the template UI is hidden and cold-load only when the create-skill template UI becomes visible. | `useTemplates.test.tsx`, `copilot-panel.test.ts` |
| Run history | `GET /api/skills/{skill_id}/runs` | Timeline panel cold load / explicit refresh / run mutation projection | OK: Timeline owns the list subscription, Workspace projects start/resume metadata without subscribing or cold-loading the list, and delete/start/resume update the shared snapshot without write-after-read refresh. | `studio-swr-policy.usage.test.ts`, `GraphCanvas.test.tsx`, `useRunHistory.revalidation.test.tsx`, `Workspace.test.tsx` |
| Local History | `GET /api/skills/{skill_id}/history` | History panel cold load / explicit refresh / run-ended exact revalidation / revert exact revalidation | OK: History UI owns the list subscription; Workspace holds only a revalidator for the run-ended event and does not cold-load `/history` when a skill opens. | `useRunHistory.revalidation.test.tsx`, `Workspace.test.tsx` |
| Test inputs | `GET /api/skills/{skill_id}/test_inputs` | I/O panel cold load / create-delete projection | OK: all SWR reads use the Studio truth policy, phase-node clicks no longer reopen I/O implicitly, and create/delete project local list snapshots without write-after-read refresh. | `studio-swr-policy.usage.test.ts`, `GraphCanvas.test.tsx`, `TestInputsSection.revalidation.test.tsx` |
| Studio event stream | `WS /ws/events` | App-level domain event stream | OK for the generic-resync risk: connect/reconnect do not dispatch data refresh callbacks; only precise backend events invoke the exact handlers. Settings, Copilot, LLM role cache, and Workspace file/runtime watchers share the same hub; Workspace must not open a second `/ws/events` socket or reconnect it on editor state changes. | `useStudioEventStream.test.ts`, `Workspace.test.tsx` |
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
BACKEND GET /api/skills/{skill_id}/golden/{golden_id}/content
BACKEND GET /api/skills/{skill_id}/history
BACKEND GET /api/skills/{skill_id}/node-llm-params
BACKEND GET /api/skills/{skill_id}/releases
BACKEND GET /api/skills/{skill_id}/releases/{release_version}
BACKEND GET /api/skills/{skill_id}/runtime-config
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
BACKEND POST /api/skills/{skill_id}/golden/plan
BACKEND POST /api/skills/{skill_id}/graph/serialize
BACKEND POST /api/skills/{skill_id}/io/import
BACKEND POST /api/skills/{skill_id}/lint
BACKEND POST /api/skills/{skill_id}/publish
BACKEND POST /api/skills/{skill_id}/releases/{release_version}/runs
BACKEND POST /api/skills/{skill_id}/revert
BACKEND POST /api/skills/{skill_id}/runtime-config/inputs/remove
BACKEND POST /api/skills/{skill_id}/runtime-config/inputs/restore
BACKEND POST /api/skills/{skill_id}/runs
BACKEND POST /api/skills/{skill_id}/runs/batch-run
BACKEND POST /api/skills/{skill_id}/runs/predict
BACKEND POST /api/skills/{skill_id}/runs/{base_run_id}/compare
BACKEND POST /api/skills/{skill_id}/runs/{run_id}/compare
BACKEND POST /api/skills/{skill_id}/runs/{run_id}/cancel
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
BACKEND PUT /api/skills/{skill_id}/runtime-config/artifacts
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
FRONTEND GET /api/settings
FRONTEND GET /api/skills/{skill_id}
FRONTEND GET /api/skills/{skill_id}/compare-candidates
FRONTEND GET /api/skills/{skill_id}/golden
FRONTEND GET /api/skills/{skill_id}/golden/{golden_id}/content
FRONTEND GET /api/skills/{skill_id}/history
FRONTEND GET /api/skills/{skill_id}/node-llm-params
FRONTEND GET /api/skills/{skill_id}/releases
FRONTEND GET /api/skills/{skill_id}/releases/{release_version}
FRONTEND GET /api/skills/{skill_id}/runtime-config
FRONTEND GET /api/skills/{skill_id}/runs
FRONTEND GET /api/skills/{skill_id}/runs/compare/{compare_group_id}
FRONTEND GET /api/skills/{skill_id}/runs/{run_id}
FRONTEND GET /api/skills/{skill_id}/runs/{run_id}/compare
FRONTEND GET /api/skills/{skill_id}/subgraph
FRONTEND GET /api/skills/{skill_id}/test_inputs
FRONTEND GET /api/skills/{skill_id}/test_inputs/{input_id}
FRONTEND GET /api/system/community-catalog-config
FRONTEND GET /api/system/truth-sources
FRONTEND GET /api/system/truth-sources/{source_id}/content
FRONTEND GET /api/templates
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
FRONTEND POST /api/skills/{skill_id}/golden/plan
FRONTEND POST /api/skills/{skill_id}/graph/serialize
FRONTEND POST /api/skills/{skill_id}/io/import
FRONTEND POST /api/skills/{skill_id}/lint
FRONTEND POST /api/skills/{skill_id}/publish
FRONTEND POST /api/skills/{skill_id}/revert
FRONTEND POST /api/skills/{skill_id}/runs
FRONTEND POST /api/skills/{skill_id}/runs/predict
FRONTEND POST /api/skills/{skill_id}/runs/{base_run_id}/compare
FRONTEND POST /api/skills/{skill_id}/runs/{run_id}/cancel
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
FRONTEND PUT /api/skills/{skill_id}/runtime-config/artifacts
FRONTEND WS /api/skills/{skill_id}/copilot/ws
FRONTEND WS /ws/events
FRONTEND WS /ws/runs/{run_id}
```

## Machine-Readable Verdict Ledger

The fenced block below is the per-request policy audit ledger. Format:

`request key | status | guard | rationale`

Statuses:

- `ok`: audited and currently aligned with the request policy.
- `partial`: known safe boundary exists, but some route-specific projection,
  lifecycle, or write semantics still need audit.
- `bad`: known violation that must be redesigned.
- `internal`: backend-owned infrastructure route that is not a UI revalidation
  trigger.
- `review`: inventoried but not yet fully audited.

Guard:

- `shared`: covered by a shared architectural guard test, or should be.
- `specific`: needs a route/component-specific behavior test before being marked
  `ok`.
- `none`: no UI-side request trigger guard applies.

```studio-request-audit-verdicts
BACKEND DELETE /api/llm/model-bundles/{bundle_id} | ok | specific | Explicit model-bundle delete command; backend emits roles_changed and returns a roles_data + registry projection snapshot built from the saved roles truth.
BACKEND DELETE /api/llm/model-profiles/{model_profile_id} | ok | specific | Explicit model-profile delete command; backend emits roles_changed, cascades role source snapshots, and returns a roles_data + registry projection snapshot.
BACKEND DELETE /api/llm/registry/endpoints/{endpoint_id} | ok | specific | Explicit endpoint delete command; backend returns the joined canonical RegistryResponse after cascading route references.
BACKEND DELETE /api/llm/roles/{role_name} | ok | specific | Explicit role delete command; backend rejects fixed roles, emits roles_changed, and returns a roles_data + registry projection snapshot.
BACKEND DELETE /api/llm/routes/{route_id} | ok | specific | Explicit route delete command; backend rejects referenced routes and otherwise returns the joined canonical RegistryResponse.
BACKEND DELETE /api/skills/{skill_id} | ok | specific | Explicit skill delete command; service tests cover index removal/path safety and it is not a lifecycle refresh path.
BACKEND DELETE /api/skills/{skill_id}/golden/{golden_id} | ok | specific | Explicit golden baseline delete command; guarded by browser-fallback/native-writer boundary tests and returns no broad truth refresh.
BACKEND DELETE /api/skills/{skill_id}/runs/{run_id} | ok | specific | Explicit Timeline delete command; route deletes one run id and the frontend projects that deletion without refetching run history.
BACKEND DELETE /api/skills/{skill_id}/test_inputs/{input_id} | ok | specific | Explicit Test Inputs delete command; route removes one input id and frontend projection clears only the affected cached list/selection.
BACKEND GET /api/_debug/value-error | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND GET /api/batch/{batch_id} | ok | specific | Scoped batch-run status read keyed by batch_id; allowed as job status polling and never refreshes broad skill/settings truth.
BACKEND GET /api/llm/fixed-roles | ok | specific | Immutable fixed-role metadata projection; route has response tests and emits no revalidation event.
BACKEND GET /api/llm/fixed-roles/{role_name} | ok | specific | Immutable fixed-role recommendation projection; route has response/404 tests and emits no revalidation event.
BACKEND GET /api/llm/model-profiles | ok | specific | Scoped model-profile projection read; backend test covers direct projection and it emits no broad revalidation event.
BACKEND GET /api/llm/providers/notable-models | ok | specific | Suggestion-only provider note projection for manual model probing; route has response tests and is not runtime truth.
BACKEND GET /api/llm/registry | ok | specific | Canonical joined registry projection; route tests cover redaction, role/model-group joins, setup_required, and registry projection fields.
BACKEND GET /api/llm/registry/endpoints/{endpoint_id}/secret | ok | specific | Explicit local secret reveal/copy for one API Keys endpoint; Settings/App/API Keys lifecycle reads use redacted registry snapshots and must not call this route.
BACKEND GET /api/llm/role-test-jobs/{job_id} | ok | specific | Scoped in-memory role-test job status read; backend tests cover start/read/progress and it emits no broad truth refresh.
BACKEND GET /api/llm/roles | ok | specific | Aggregate roles cold-load projection; backend returns roles_data plus the joined registry snapshot from the same roles/credentials state.
BACKEND GET /api/llm/roles/test-results | ok | specific | Persisted last-known role-test result projection; backend read is scoped, emits no revalidation event, and tests cover empty/result re-projection.
BACKEND GET /api/llm/roles/{role_name} | ok | specific | Scoped backend role read; frontend no longer exposes a caller, and backend tests cover materialized single-role response behavior.
BACKEND GET /api/settings | ok | specific | Scoped app-settings read; backend tests cover effective defaults and persisted snapshot roundtrip, and the route emits no revalidation event.
BACKEND GET /api/skills/{skill_id} | ok | shared | Canonical SkillDetail projection for one skill; consumers cold-load by skill id or revalidate from precise skill/file events.
BACKEND GET /api/skills/{skill_id}/compare-candidates | ok | specific | Scoped runtime_config projection read for Properties; backend tests cover canonical node map response and it emits no revalidation event.
BACKEND GET /api/skills/{skill_id}/golden | ok | shared | Per-skill golden metadata projection; used for cold-load node badges and explicit golden flows, not focus/reconnect refresh.
BACKEND GET /api/skills/{skill_id}/golden/{golden_id}/content | ok | specific | Explicit read of one golden content ref; list responses do not hydrate content implicitly.
BACKEND GET /api/skills/{skill_id}/history | ok | shared | Local history list read scoped to a skill; frontend owns it in the History UI and uses precise run-ended/revert revalidation.
BACKEND GET /api/skills/{skill_id}/node-llm-params | ok | specific | Scoped runtime_config projection read for Properties; backend tests cover canonical node map response and it emits no revalidation event.
BACKEND GET /api/skills/{skill_id}/releases | ok | specific | Release-management read scoped to one skill; no production UI lifecycle subscriber polls this route.
BACKEND GET /api/skills/{skill_id}/releases/{release_version} | ok | specific | Explicit release manifest read scoped by release_version; not a broad refresh trigger.
BACKEND GET /api/skills/{skill_id}/runtime-config | ok | shared | Runtime config is server-owned truth; reads are cold load or precise import-file/runtime-config revalidation.
BACKEND GET /api/skills/{skill_id}/runs | ok | shared | Run-history list read scoped to one skill; writes return/project RunMetadata and do not require write-after-read list refresh.
BACKEND GET /api/skills/{skill_id}/runs/compare/{compare_group_id} | ok | specific | Scoped compare-group read after an explicit compare run; polling/refresh stays keyed to compare_group_id.
BACKEND GET /api/skills/{skill_id}/runs/{run_id} | ok | specific | Scoped run detail read for trace/run-ended flows; it never refreshes the run list or skill detail.
BACKEND GET /api/skills/{skill_id}/runs/{run_id}/audit | ok | specific | Explicit audit detail read for one run id; route is observational and emits no domain refresh.
BACKEND GET /api/skills/{skill_id}/runs/{run_id}/compare | ok | specific | Explicit Golden Compare read for one run/baseline pair; response is scoped compare data only.
BACKEND GET /api/skills/{skill_id}/runs/{run_id}/diff | ok | specific | Explicit diff read alias for one run/baseline pair; response is scoped compare data only.
BACKEND GET /api/skills/{skill_id}/subgraph | ok | specific | Explicit child-subgraph topology resolution by path; normal node selection does not invoke this route.
BACKEND GET /api/skills/{skill_id}/test_inputs | ok | shared | Test input metadata list for the I/O panel; frontend uses Studio truth policy and projects create/delete changes.
BACKEND GET /api/skills/{skill_id}/test_inputs/{input_id} | ok | specific | Explicit Predict/Run preflight reads one selected test input content; selection alone does not hydrate content.
BACKEND GET /api/system/community-catalog-config | ok | shared | Settings General metadata read; client cache dedupes and it emits no revalidation event.
BACKEND GET /api/system/truth-sources | ok | shared | Settings General truth-source metadata read; client cache dedupes and it emits no revalidation event.
BACKEND GET /api/system/truth-sources/{source_id}/content | ok | specific | Explicit source preview fallback read keyed by source_id; source list loading does not hydrate content.
BACKEND GET /api/templates | ok | specific | Static built-in template projection; backend test covers canonical template ids and verifies the read emits no revalidation event.
BACKEND GET /health | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /api/copilot/roles/{role_name}/test-sdk | ok | specific | Explicit Copilot role SDK test command; returns scoped diagnostics/job state and does not mutate broad registry truth.
BACKEND POST /api/io/scan | ok | specific | Explicit I/O import scan for a chosen file/folder; scanning is not tied to panel mount or selection.
BACKEND POST /api/llm/catalog/contribute | ok | specific | Explicit community-catalog contribution command; repository/catalog side effects are command-scoped and do not refresh runtime roles/settings.
BACKEND POST /api/llm/catalog/repository/ensure | ok | specific | Explicit catalog repository setup command; result is catalog-scoped setup metadata.
BACKEND POST /api/llm/catalog/share | ok | specific | Explicit share command for selected local catalog content; no lifecycle caller remains.
BACKEND POST /api/llm/catalog/sync | ok | specific | Explicit remote catalog sync command; current Settings lifecycle auto-sync path is removed.
BACKEND POST /api/llm/catalog/sync-verified | ok | specific | Explicit verified-catalog sync command; controller tests guard that Settings load does not call it automatically.
BACKEND POST /api/llm/endpoints/{endpoint_id}/models/test | ok | specific | Explicit manual model probe command; backend returns EndpointModelTestResponse with canonical registry projection and scoped results.
BACKEND POST /api/llm/endpoints/{endpoint_id}/test | ok | specific | Explicit endpoint Test command; backend returns EndpointTestResponse with canonical registry projection and scoped endpoint metadata.
BACKEND POST /api/llm/model-bundles/{bundle_id}/test-jobs | ok | specific | Explicit bundle Test command; returns a scoped job id and does not mutate broad registry/roles truth.
BACKEND POST /api/llm/model-groups/test-jobs | ok | specific | Explicit compare-candidate Test command; returns a scoped transient job id and does not persist role truth.
BACKEND POST /api/llm/roles/{role_name}/apply-profile | ok | specific | Explicit profile-apply command; backend writes roles truth, emits roles_changed, and tests cover conflict/runtime-setting projection.
BACKEND POST /api/llm/roles/{role_name}/test | ok | specific | Explicit role test command; backend probes only the persisted role targets and returns scoped diagnostics without refreshing broad roles/registry truth.
BACKEND POST /api/llm/roles/{role_name}/test-jobs | ok | specific | Explicit role Test command; returns a scoped job id and progress is read only through /role-test-jobs/{job_id}.
BACKEND POST /api/llm/routes/{route_id}/probe | ok | specific | Explicit route probe command; backend returns the joined canonical RegistryResponse so route-derived model groups stay in sync.
BACKEND POST /api/llm/routes/{route_id}/probe-multimodal | ok | specific | Explicit multimodal route probe command; backend returns the joined canonical RegistryResponse so route-derived model groups stay in sync.
BACKEND POST /api/skills | ok | specific | Explicit create/import skill command; returns one SkillSummary and does not act as a background refresh.
BACKEND POST /api/skills/{skill_id}/compile | ok | specific | Explicit manual Compile command; success returns CompileSuccess with canonical SkillDetail detail built from the same compile/lint result, and failure returns structured CompileFailure.errors.
BACKEND POST /api/skills/{skill_id}/copilot/dispatch | ok | specific | Unimplemented dispatch scaffold returns 501 and does not store view context or trigger revalidation.
BACKEND POST /api/skills/{skill_id}/copilot/interrupt | ok | specific | Explicit stop command for one skill's active Copilot stream; idempotent when no stream is active.
BACKEND POST /api/skills/{skill_id}/copilot/judge | ok | specific | Explicit judge-context preparation for one compare result; returns refs only and does not start a background sync.
BACKEND POST /api/skills/{skill_id}/copilot/tool-approval | ok | specific | Explicit approval resolution for one held Copilot tool_use_id; no broad truth cache is invalidated.
BACKEND POST /api/skills/{skill_id}/files/{file_path:path} | ok | specific | Browser fallback for explicit file save with expected-hash semantics; Tauri native-fs remains the normal sole writer.
BACKEND POST /api/skills/{skill_id}/fork | ok | specific | Explicit fork command; returns the new SkillSummary and does not re-read all skills as a side effect.
BACKEND POST /api/skills/{skill_id}/golden | ok | specific | Browser fallback for explicit Promote to Golden; native-fs plan path is preferred in desktop and tests guard fallback header use.
BACKEND POST /api/skills/{skill_id}/golden/plan | ok | specific | Explicit promote-to-golden planner for native-fs; backend returns planned files plus baseline projection.
BACKEND POST /api/skills/{skill_id}/graph/serialize | ok | specific | Explicit canvas topology save; response is canonical hash/update metadata for the edited GRAPH.md.
BACKEND POST /api/skills/{skill_id}/io/import | ok | specific | Explicit import command for selected I/O material; not run from panel visibility or focus.
BACKEND POST /api/skills/{skill_id}/lint | ok | specific | Explicit/debounced diagnostics SSOT endpoint; caller chooses disk or changed-markdown body and receives the full lint result.
BACKEND POST /api/skills/{skill_id}/publish | ok | specific | Explicit publish command; productization tests cover package payload/native-writer boundary and remote-sync skip states.
BACKEND POST /api/skills/{skill_id}/releases/{release_version}/runs | ok | specific | Explicit run-from-release command; returns RunMetadata for the launched release run.
BACKEND POST /api/skills/{skill_id}/revert | ok | specific | Explicit Local History revert command; returns canonical SkillDetail and frontend projects it without a broad follow-up read.
BACKEND POST /api/skills/{skill_id}/runtime-config/inputs/remove | ok | specific | Explicit runtime input intent write; returns the canonical runtime_config snapshot with the removed tombstone persisted.
BACKEND POST /api/skills/{skill_id}/runtime-config/inputs/restore | ok | specific | Explicit runtime input intent restore; returns the canonical runtime_config snapshot after removed intent is cleared and active bindings are reconciled.
BACKEND POST /api/skills/{skill_id}/runs | ok | specific | Explicit Run command; returns RunMetadata and does not require a run-list refetch.
BACKEND POST /api/skills/{skill_id}/runs/batch-run | ok | specific | Explicit batch run over selected test inputs; subsequent status reads are scoped to batch_id.
BACKEND POST /api/skills/{skill_id}/runs/predict | ok | specific | Explicit Predict command; returns diagnostic export used for local projection, not broad refresh.
BACKEND POST /api/skills/{skill_id}/runs/{base_run_id}/compare | ok | specific | Explicit node-compare command keyed by base_run_id; returns compare group metadata.
BACKEND POST /api/skills/{skill_id}/runs/{run_id}/compare | ok | specific | Explicit compare command alias for one run id; response is scoped compare result.
BACKEND POST /api/skills/{skill_id}/runs/{run_id}/cancel | ok | specific | Explicit stop command; returns the cancelled RunMetadata and broadcasts the run/stopped gate outcome, so no surface polls to learn the run ended.
BACKEND POST /api/skills/{skill_id}/runs/{run_id}/resume | ok | specific | Explicit resume command; returns RunMetadata for the resumed run and emits scoped run stream events.
BACKEND POST /api/skills/{skill_id}/runs/{run_id}/resume/validity | ok | specific | Scoped resume-validity/dirty-downstream probe for one run and resume target; not a broad truth refresh.
BACKEND POST /api/skills/{skill_id}/sync | ok | specific | Explicit collaboration sync command; no background sync runs on focus/reconnect.
BACKEND POST /api/skills/{skill_id}/terminal | ok | specific | Explicit terminal session creation; returns one ws_url and subsequent traffic is isolated to that terminal id.
BACKEND POST /api/skills/{skill_id}/test_inputs | ok | specific | Browser fallback for explicit Test Input create; desktop path writes through native-fs and frontend projects returned metadata.
BACKEND POST /api/skills/{skill_id}/validate_input | ok | specific | Explicit validation command for a submitted payload; returns scoped validation diagnostics.
BACKEND POST /engine/compile | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /engine/predict_artifact | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /engine/resume | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /engine/resume_validity | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /engine/run_artifact | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /gateway/decide_fallback | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /gateway/materialize_model_bundle | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /gateway/materialize_role | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /gateway/project_route_state | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /gateway/resolve_credential | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /gateway/resolve_routes | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND POST /shutdown | internal | none | Backend-owned infrastructure endpoint; not a UI revalidation trigger.
BACKEND PUT /api/llm/model-profiles | ok | specific | Explicit model-profile replace command; backend emits roles_changed and returns a roles_data + registry projection snapshot instead of requiring write-after-read refresh.
BACKEND PUT /api/llm/registry/endpoints | ok | specific | Explicit endpoint save command; backend returns the joined canonical RegistryResponse so callers do not perform write-after-read refresh.
BACKEND PUT /api/llm/roles | ok | specific | Explicit aggregate roles save; backend emits roles_changed and returns a roles_data + registry projection snapshot instead of requiring write-after-read refresh.
BACKEND PUT /api/llm/roles/{role_name} | ok | specific | Explicit scoped role replace used by backend/materializer tests; backend writes roles truth, emits roles_changed, and returns the materialized role.
BACKEND PUT /api/llm/routes/{route_id} | ok | specific | Explicit route metadata update command; backend returns the joined canonical RegistryResponse.
BACKEND PUT /api/settings | ok | specific | Explicit app-settings save command; unchanged snapshots are side-effect-free, changed snapshots return the canonical AppSettings response and publish a precise settings_changed event.
BACKEND PUT /api/skills/{skill_id} | ok | specific | Explicit skill metadata update; returns canonical SkillDetail for the edited skill.
BACKEND PUT /api/skills/{skill_id}/runtime-config/artifacts | ok | specific | Runtime artifact writes are explicit output-config saves and return the canonical runtime_config snapshot.
BACKEND PUT /api/skills/{skill_id}/nodes/{node_id}/compare-candidates | ok | specific | Explicit Properties compare-candidates save; no-op writes are side-effect-free, changed writes return the node snapshot and publish precise runtime_config_changed(dataset=compare_candidates, node_id).
BACKEND PUT /api/skills/{skill_id}/nodes/{node_id}/node-llm-params | ok | specific | Explicit Properties node-LLM-params save; no-op writes are side-effect-free, changed writes return the node snapshot and publish precise runtime_config_changed(dataset=node_llm_params, node_id).
BACKEND WS /api/skills/{skill_id}/copilot/ws | ok | specific | Scoped Copilot user-message stream; future @mentions must travel in this message payload, not via background context POST.
BACKEND WS /ws/events | ok | shared | Domain event stream; connect and reconnect must not refresh broad truth.
BACKEND WS /ws/runs/{run_id} | ok | specific | Scoped run event stream keyed by run_id; it observes one execution and does not refresh registry/settings truth.
BACKEND WS /ws/terminal/{term_id} | ok | specific | Scoped terminal stream keyed by term_id; lifecycle is tied to an explicit terminal session.
FRONTEND DELETE /api/llm/model-bundles/{bundle_id} | ok | specific | Explicit model-bundle delete command; client projects the returned roles_data + registry snapshot and performs no follow-up /llm/registry GET.
FRONTEND DELETE /api/llm/registry/endpoints/{endpoint_id} | ok | specific | Explicit provider delete command; client projects the returned canonical registry snapshot without a follow-up /llm/registry GET.
FRONTEND DELETE /api/llm/roles/{role_name} | ok | specific | Explicit role delete command; client projects the returned roles_data + registry snapshot and performs no follow-up /llm/registry GET.
FRONTEND DELETE /api/llm/routes/{route_id} | ok | specific | Explicit route delete command; client projects the returned canonical registry without a follow-up /llm/registry GET.
FRONTEND DELETE /api/skills/{skill_id}/runs/{run_id} | ok | specific | Explicit Timeline delete command; client removes the known run id from the local list snapshot without a follow-up /runs GET.
FRONTEND DELETE /api/skills/{skill_id}/test_inputs/{input_id} | ok | specific | Explicit Test Inputs delete command; client removes the known id from the local list snapshot without a follow-up /test_inputs GET and clears selection when needed.
FRONTEND GET /api/llm/fixed-roles | ok | shared | First visible LLM Roles/Copilot consumer reads immutable metadata once; lazy Settings tabs and client cache/dedupe block hidden-page and repeated fetches.
FRONTEND GET /api/llm/fixed-roles/{role_name} | ok | shared | First visible role card reads immutable per-role recommendations once; client cache/dedupe shares repeated consumers.
FRONTEND GET /api/llm/providers/notable-models | ok | shared | Manual model candidates load only when the probing accordion is explicitly opened; collapsed API Keys is network-silent and client cache is provider-scoped.
FRONTEND GET /api/llm/registry | ok | shared | Cached read path is guarded against mount, focus, reconnect, and Settings tab switches; current registry mutations project returned canonical snapshots instead of refetching broad truth.
FRONTEND GET /api/llm/registry/endpoints/{endpoint_id}/secret | ok | specific | Explicit per-endpoint API key reveal/copy only; Settings/App/API Keys mount, open/close, tab switch, focus, WebSocket reconnect, and registry_changed summary refresh must not hydrate secrets.
FRONTEND GET /api/llm/role-test-jobs/{job_id} | ok | specific | Scoped polling starts only after an explicit Test command returns a job id; pollers do not refresh registry/roles/settings truth.
FRONTEND GET /api/llm/roles | ok | shared | Cached read path is guarded against mount, focus, and reconnect refetch; roles response carries registry projection data, so cold loads do not perform a second broad registry read.
FRONTEND GET /api/llm/roles/test-results | ok | shared | Shared persisted role-test badge read; API Keys does not mount LLM Roles/Copilot seed effects, and first visible LLM Roles/Copilot use shares the cached read.
FRONTEND GET /api/settings | ok | shared | Cold load waits for API readiness and dialog open or close must not refetch.
FRONTEND GET /api/skills/{skill_id} | ok | shared | Shared per-skill SkillDetail cold load uses Studio truth SWR policy; manual Compile, Local History revert, and source-write/file events project canonical snapshots or revalidate only the exact skill key.
FRONTEND GET /api/skills/{skill_id}/compare-candidates | ok | shared | Shared per-skill cold load; node selection must remain network-silent after load.
FRONTEND GET /api/skills/{skill_id}/golden | ok | shared | Workspace cold-loads per-skill golden metadata once for canvas node badges through Studio truth SWR policy; per-node promote projects the returned baseline into the loaded list without broad refresh.
FRONTEND GET /api/skills/{skill_id}/golden/{golden_id}/content | ok | specific | Explicit open/edit of one golden baseline content ref; list metadata does not hydrate content implicitly.
FRONTEND GET /api/skills/{skill_id}/history | ok | shared | Local History list is owned by the History UI cold-load key; Workspace uses a revalidator-only hook for run-ended refreshes, so skill open does not subscribe to or cold-load the list.
FRONTEND GET /api/skills/{skill_id}/node-llm-params | ok | shared | Shared per-skill cold load; node selection must remain network-silent after load.
FRONTEND GET /api/skills/{skill_id}/releases | ok | specific | API client helper is only used by explicit release-management reads/tests; the main workspace/header does not poll releases during normal authoring.
FRONTEND GET /api/skills/{skill_id}/releases/{release_version} | ok | specific | API client helper reads one release manifest by explicit release-version request; no lifecycle subscriber exists in the production UI.
FRONTEND GET /api/skills/{skill_id}/runtime-config | ok | shared | Runtime config is shared per-skill truth, revalidated only after import-file events, runtime_config file events, or artifact save.
FRONTEND GET /api/skills/{skill_id}/runs | ok | shared | Run-history list is a Timeline-owned SWR cold-load key with Studio truth policy; Workspace uses a projection-only hook so skill open/start/resume do not subscribe to or cold-load the list, and writes project returned metadata without a follow-up GET.
FRONTEND GET /api/skills/{skill_id}/runs/compare/{compare_group_id} | ok | specific | Scoped compare-group read starts only after an explicit node compare run returns a group id; refresh is confined to that compare_group_id.
FRONTEND GET /api/skills/{skill_id}/runs/{run_id} | ok | specific | Scoped run detail read is driven by an explicit trace/run-ended target run id and does not refresh run lists or skill truth.
FRONTEND GET /api/skills/{skill_id}/runs/{run_id}/compare | ok | specific | Explicit Golden Compare/Judge action reads the selected run's compare payload; replay stays scoped to the chosen run id and baseline.
FRONTEND GET /api/skills/{skill_id}/subgraph | ok | specific | Explicit subgraph expand/drill action resolves one child graph topology by path; ordinary node selection and panel open do not resolve subgraphs.
FRONTEND GET /api/skills/{skill_id}/test_inputs | ok | shared | Test input list is a SWR cold-load key with Studio truth policy; phase-node clicks no longer reopen I/O implicitly, and create/delete project list changes without write-after-read refresh.
FRONTEND GET /api/skills/{skill_id}/test_inputs/{input_id} | ok | specific | Explicit Predict/Run preflight resolves the selected test input content; missing selection fails locally and no input content is hydrated by selection alone.
FRONTEND GET /api/system/community-catalog-config | ok | shared | Settings General cold-loads once; client cache dedupes concurrent/repeated consumers.
FRONTEND GET /api/system/truth-sources | ok | shared | Settings General cold-loads once; client cache dedupes concurrent/repeated consumers.
FRONTEND GET /api/system/truth-sources/{source_id}/content | ok | shared | Explicit source-open preview fallback only; no mount, tab switch, focus, or selection trigger.
FRONTEND GET /api/templates | ok | shared | Disabled until the create-skill template UI is visible; no Copilot skill chat mount fetch.
FRONTEND POST /api/io/scan | ok | specific | Explicit I/O import dialog action scans a chosen file/folder and returns scoped field candidates; no panel mount or node selection scans disk.
FRONTEND POST /api/llm/catalog/sync-verified | ok | specific | No lifecycle trigger remains in Settings; future use must be an explicit command or precise backend event path.
FRONTEND POST /api/llm/endpoints/{endpoint_id}/models/test | ok | specific | Explicit manual model probe command; client projects returned registry/results and does not perform a follow-up registry GET.
FRONTEND POST /api/llm/endpoints/{endpoint_id}/test | ok | specific | Explicit endpoint Test/re-probe command; client projects returned registry and controller tests guard against a second getCredentials round trip.
FRONTEND POST /api/llm/model-bundles/{bundle_id}/test-jobs | ok | specific | Explicit bundle Test button command; lifecycle tests cover start/poll/settle through the scoped job mirror.
FRONTEND POST /api/llm/model-groups/test-jobs | ok | specific | Explicit compare-candidate Test command from Properties; node selection tests cover that selection itself does not start test jobs, and returned jobs are polled by id.
FRONTEND POST /api/llm/roles/{role_name}/test | ok | specific | Explicit legacy role Test command; client sends only the command and consumes scoped diagnostics with no follow-up registry/roles read.
FRONTEND POST /api/llm/roles/{role_name}/test-jobs | ok | specific | Explicit role/Copilot Test button command; tests cover validation gating, start/poll/settle, and no job start when validation fails.
FRONTEND POST /api/llm/routes/{route_id}/probe | ok | specific | Explicit route probe command; client projects returned registry and returns the updated route to the caller.
FRONTEND POST /api/llm/routes/{route_id}/probe-multimodal | ok | specific | Explicit multimodal route probe command; client projects returned registry and returns the updated route to the caller.
FRONTEND POST /api/skills/{skill_id}/compile | ok | specific | Explicit manual Compile command; client projects CompileSuccess.detail into the shared skill-detail cache with revalidate:false and performs no broad /skills/{skill_id} follow-up read.
FRONTEND POST /api/skills/{skill_id}/copilot/interrupt | ok | specific | Explicit Copilot Stop button command; it interrupts only the active skill stream and never revalidates registry/roles/settings/skill truth.
FRONTEND POST /api/skills/{skill_id}/copilot/judge | ok | specific | Explicit Copilot Judge preparation from a compare result; it returns scoped refs for the next Copilot message and is not a background context sync.
FRONTEND POST /api/skills/{skill_id}/copilot/tool-approval | ok | specific | Explicit approve/reject action for one held Copilot tool call; result is scoped to that tool_use_id.
FRONTEND POST /api/skills/{skill_id}/files/{file_path:path} | ok | specific | Browser-only explicit file-save fallback; Tauri uses native-fs as sole writer, and editor/panel saves are user edits with expected-hash conflict handling.
FRONTEND POST /api/skills/{skill_id}/golden | ok | specific | Browser-only explicit Promote to Golden fallback; Tauri uses the plan endpoint plus native-fs writes, and callers project the returned baseline.
FRONTEND POST /api/skills/{skill_id}/golden/plan | ok | specific | Explicit promote-to-golden in Tauri asks for a write plan and projects the returned baseline after native-fs writes.
FRONTEND POST /api/skills/{skill_id}/graph/serialize | ok | specific | Explicit canvas topology mutation persists GRAPH.md with expected_hash and returns the canonical hash/update metadata; selection alone never serializes.
FRONTEND POST /api/skills/{skill_id}/io/import | ok | specific | Explicit I/O import command writes the chosen import mapping/runtime files; create/delete projections or precise runtime events handle follow-up state.
FRONTEND POST /api/skills/{skill_id}/lint | ok | specific | Explicit/debounced lint after user source edits or settled file writes; it is the diagnostics SSOT path and not a focus, reconnect, or selection refresh.
FRONTEND POST /api/skills/{skill_id}/publish | ok | specific | Explicit Header Publish command; success/failure is local command state and does not poll release or registry truth.
FRONTEND POST /api/skills/{skill_id}/revert | ok | specific | Explicit Local History revert command; client projects the returned SkillDetail into the skill-detail cache without a follow-up /skills/{skill_id} GET and revalidates only the history list.
FRONTEND POST /api/skills/{skill_id}/runs | ok | specific | Explicit Run command; backend returns RunMetadata and Workspace projects it into the shared run-history cache without subscribing to or refetching the list.
FRONTEND POST /api/skills/{skill_id}/runs/predict | ok | specific | Explicit Predict button command; input content is resolved from the selected test input and the returned diagnostic export is projected locally.
FRONTEND POST /api/skills/{skill_id}/runs/{base_run_id}/compare | ok | specific | Explicit node Compare LLMs command from Properties; node selection itself is covered as network-silent and never starts compare jobs.
FRONTEND POST /api/skills/{skill_id}/runs/{run_id}/cancel | ok | specific | Fired only by the Stop button on the run in flight; the toolbar and panel follow the broadcast gate outcome rather than refetching run state.
FRONTEND POST /api/skills/{skill_id}/runs/{run_id}/resume | ok | specific | Explicit resume commands return RunMetadata and Workspace projects the resumed run into the shared run-history cache without a follow-up /runs GET.
FRONTEND POST /api/skills/{skill_id}/runs/{run_id}/resume/validity | ok | specific | Scoped dirty-downstream probe runs for a failed run after skill content changes or resume UI needs validity; it is not triggered by selecting arbitrary nodes.
FRONTEND POST /api/skills/{skill_id}/sync | ok | specific | Explicit collaboration Sync command from the publish/collaboration UI; no background sync runs on skill open, focus, or reconnect.
FRONTEND POST /api/skills/{skill_id}/test_inputs | ok | specific | Explicit Test Inputs create command; client inserts the returned TestInputMetadata into the local list snapshot without a follow-up /test_inputs GET.
FRONTEND POST /api/skills/{skill_id}/validate_input | ok | specific | Explicit playground/input validation command; it validates a submitted payload and does not revalidate broad skill or runtime truth.
FRONTEND PUT /api/llm/registry/endpoints | ok | specific | Explicit API Keys save/upsert command; client uses the returned canonical registry snapshot and no longer follows with a broad /llm/registry GET.
FRONTEND PUT /api/llm/roles | ok | specific | Explicit aggregate roles save; client projects the returned roles_data + registry snapshot and performs no follow-up /llm/registry GET.
FRONTEND PUT /api/settings | ok | specific | Settings autosave only follows explicit field edits; debounce/in-flight semantics keep the latest payload and suppress stale response projection.
FRONTEND PUT /api/skills/{skill_id}/runtime-config/artifacts | ok | specific | Output artifact config save is an explicit command and projects the returned runtime_config snapshot.
FRONTEND PUT /api/skills/{skill_id}/nodes/{node_id}/compare-candidates | ok | specific | Explicit Properties compare-candidates autosave for one node; client updates the skill-scoped cache entry and clears in-flight stale reads.
FRONTEND PUT /api/skills/{skill_id}/nodes/{node_id}/node-llm-params | ok | specific | Explicit Properties node-LLM-params autosave for one node; debounced saves project the returned node config without broad refetch.
FRONTEND WS /api/skills/{skill_id}/copilot/ws | ok | specific | Scoped Copilot user-message stream; it opens for the active skill conversation and future @mentions must travel in the message payload, with no background context POST.
FRONTEND WS /ws/events | ok | shared | Domain event stream; only precise events may invalidate exact cache keys. Consumers must share the singleton hub; Workspace file/runtime watchers are covered and must not create a workspace-local events socket.
FRONTEND WS /ws/runs/{run_id} | ok | specific | Scoped run event stream keyed by run_id; it observes a single execution and does not refresh registry/settings/skill-list truth.
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
