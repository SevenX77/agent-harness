---
status: Draft
created: 2026-05-26
owner: Studio
related_requirements: .kiro/specs/studio-llm-roles-model-groups/requirements.md
related_design: .kiro/specs/studio-llm-roles-model-groups/design.md
---

# Studio LLM Roles Model Groups Tasks

> Required for UI work: before modifying `apps/studio/frontend`, read `docs/development/FRONTEND_UI_SPEC.md` section 2 and search `apps/studio/frontend/src/components/ui/` for existing shadcn/Radix wrappers.

## Phase 0: Final Contract Lock

- [ ] 0.1 Lock the final state vocabulary in requirements and design.
  - Source domains: `Identity`, `Capability`, `Health`.
  - Gateway admission: `admit`, `temporary_skip`, `block`.
  - Provider UI states: `Ready`, `Untested`, `Cooling Down`, `Needs Setup`, `Off`.
  - Role Fit states: `Using`, `Downgraded`, `Needs Test`, `Not Fit`.
  - Reject top-level provider states such as `Recent Issue`, `Runnable`, `Unavailable`, or `failed_last_test`.

- [ ] 0.2 Lock execution boundaries.
  - Studio materializer owns Model Groups, Role intent, Role Fit, resolved runtime settings, and generated gateway `fallback_chain`.
  - Gateway does not consume Model Groups or Studio Role intent.
  - Gateway consumes concrete candidates and computes admission only.
  - Provider fallback is always on; one candidate failure does not stop the chain.

- [ ] 0.3 Lock compatibility policy.
  - Keep existing `RouteStatus` in the first implementation pass.
  - Treat `verified`, `unverified_manual`, `failed`, and `disabled` as compatibility projections only.
  - New code must prefer Identity + Capability + Health projections over direct UI branching on `RouteStatus`.

- [ ] 0.4 Lock cross-cutting data fields and fixed algorithms.
  - `ProviderEndpoint.provider_kind: "official" | "third_party" | "custom"`.
  - `ProviderEndpoint.rate_limit_bucket?: string`; effective default is `endpoint_id`.
  - Studio authoring `RoleEntry.role_kind: "graph_agent" | "copilot"`.
  - Curated provider-kind map seeds new endpoints only; user-edited `provider_kind` is authoritative.
  - State projection priority is `Off > Needs Setup > Cooling Down > Ready/Untested`.
  - Circuit aggregation uses farthest future `retry_at`; tied messages prefer route scope, then endpoint scope, then bucket scope.
  - `Test Now` uses `POST /api/llm/routes/{route_id}/probe?force=true`.

## Phase 1: Gateway State Contracts and Admission

- [ ] 1.1 Add gateway schema contracts.
  - Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`.
  - Add config validity, capability confidence, runtime health reference, and gateway admission DTOs.
  - Add `provider_kind` and `rate_limit_bucket` on provider endpoint schema where gateway consumes endpoint facts.
  - Keep `RouteStatus` for migration compatibility.
  - Do not add Studio Model Group or Role intent concepts to gateway schema.

- [ ] 1.2 Add pure admission module.
  - Create: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/admission.py`.
  - Inputs: endpoint enabled, route enabled, endpoint/route config validity, credential presence, runtime health, known runtime setting errors.
  - Outputs: `admit`, `temporary_skip`, or `block` with reason codes and optional `retry_at`.

- [ ] 1.3 Add gateway admission tests.
  - Test disabled endpoint/route -> `block`.
  - Test missing credential -> `block`.
  - Test invalid route config -> `block`.
  - Test open circuit with future `retry_at` -> `temporary_skip`.
  - Test unknown capability is not an admission input and does not block.
  - Test valid or unknown config without active circuit -> `admit`.
  - Test endpoint-level disable blocks all child routes.
  - Test route, endpoint, and bucket circuits each produce `temporary_skip`.

- [ ] 1.4 Narrow gateway lint.
  - Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py`.
  - Block only definite execution impossibilities and known-illegal runtime settings.
  - Do not block solely because capability is unknown.
  - Do not implement Studio Role intent semantics in gateway lint.

## Phase 2: Gateway Runtime Events, Health Store, and Fallback

- [ ] 2.1 Add runtime event model.
  - Create: `packages/graph-agent-gateway/src/graph_agent_gateway/runtime_events.py`.
  - Events include role, route, endpoint, phase, outcome, reason code, provider status code, retry time, and message.
  - Outcomes: `success`, `transient_failure`, `hard_failure`, `blocked`, `temporary_skipped`.
  - Phases: `admission`, `probe`, `dispatch`.

- [ ] 2.2 Add gateway health store interface.
  - Create: `packages/graph-agent-gateway/src/graph_agent_gateway/health_store.py`.
  - Define `RuntimeHealthStore` protocol and in-memory implementation.
  - Treat in-memory implementation as tests/dev only; production Studio integration supplies durable app-local storage.
  - Support recording runtime events, reading route health, and clearing route circuits.

- [ ] 2.3 Update `GatewayChatModel`.
  - Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`.
  - Compute admission before probe/dispatch.
  - Emit `temporary_skipped` when admission says temporary skip.
  - Emit `blocked` when admission blocks.
  - Emit `transient_failure` for timeout/network/429/5xx-style failures.
  - Emit `hard_failure` for invalid key/model/config-style failures.
  - Emit `success` on successful dispatch.
  - Continue to the next candidate after any candidate failure.

- [ ] 2.4 Complete runtime probe coverage.
  - Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py`.
  - Add real one-token probe for `google_genai`.
  - Add real minimal probe for `ark_runtime`.
  - Keep OpenAI-compatible and Anthropic-compatible behavior.

- [ ] 2.5 Add gateway tests.
  - Test hard failure on first candidate records event and falls back to second candidate.
  - Test transient failure opens circuit and falls back.
  - Test active circuit causes `temporary_skip`.
  - Test Google and Ark probes call minimal generation paths.
  - Run: `pytest packages/graph-agent-gateway/tests -q`.

## Phase 3: Studio Health Store and Projection Service

- [ ] 3.1 Add Studio runtime health store.
  - Create: `apps/studio/backend/app/services/llm_health_store.py`.
  - Store circuit records with scope, scope ID, state, opened time, retry time, TTL, reason code, failure count, and message.
  - Prefer SQLite or durable app-local KV for runtime health.
  - Use in-memory store only in tests.

- [ ] 3.2 Add state projection service.
  - Create: `apps/studio/backend/app/services/llm_state_projection.py`.
  - Project provider facts to one of `ready`, `untested`, `cooling_down`, `needs_setup`, `off`.
  - Project Role Fit to one of `using`, `downgraded`, `needs_test`, `not_fit`.
  - Missing key, invalid key, invalid model, invalid base URL, and invalid protocol all project to `needs_setup`.
  - User-disabled options project to `off`.
  - Active circuit projects to `cooling_down`.
  - Callable success projects to `ready` even if capability detail is partial.
  - Endpoint disabled projects every child provider model option to `off`.
  - When several inputs apply, projection uses `Off > Needs Setup > Cooling Down > Ready/Untested`.
  - When several circuits apply, projection uses the farthest future `retry_at`.

- [ ] 3.3 Extend backend DTOs.
  - Modify: `apps/studio/backend/app/models/llm_config.py`.
  - Add `provider_kind` and `rate_limit_bucket` to provider endpoint persistence/DTOs.
  - Add curated provider-kind defaults for new endpoints only; preserve user edits on existing endpoints.
  - Add provider state projection DTO with label, detail, reason code, retry time, and raw diagnostic fields.
  - Add Role Fit projection DTO with label and warnings.
  - Preserve raw exact `route_id` for persistence.

- [ ] 3.4 Add projection tests.
  - Missing key -> `needs_setup`.
  - Invalid model -> `needs_setup`.
  - Disabled by user -> `off`.
  - Circuit open -> `cooling_down` with retry time.
  - Callable success + partial capability -> `ready`.
  - Required unknown capability -> Role Fit `needs_test`.
  - Proven unsupported required capability -> Role Fit `not_fit`.
  - Endpoint disabled overrides active circuit and projects child options to `off`.
  - Needs Setup overrides active circuit.
  - Route plus endpoint circuit displays the farthest retry time.
  - Rate-limit bucket circuit affects every route in the same bucket.
  - Persisted `provider_kind` drives official/third-party/custom classification.

## Phase 4: Real Capability Test

- [ ] 4.1 Rewrite route probe behavior.
  - Modify: `apps/studio/backend/app/routers/llm.py`.
  - `POST /api/llm/routes/{route_id}/probe` becomes the backend Capability Test.
  - It must call the real provider when capability cannot be established from trusted metadata.
  - It must not treat request-supplied capability metadata as `probed_verified` proof.

- [ ] 4.2 Reuse concrete model probe.
  - Modify or reuse: `apps/studio/backend/app/services/copilot_test.py`.
  - Use real minimal generation for supported providers.
  - Successful minimal generation proves callable status, not necessarily complete capability knowledge.

- [ ] 4.3 Write Capability Test outcomes.
  - Success: record callable success, close route circuit, update capability confidence to `callable_only`, `partial`, or `known`, and compatibility-project to `verified`.
  - Transient failure: open/update circuit, do not mark provider as failed, project UI as `Cooling Down`.
  - Hard setup failure: update config validity, compatibility-project to `failed`, project UI as `Needs Setup`.

- [ ] 4.4 Add backend tests.
  - Successful probe makes a real provider-model call.
  - Timeout opens circuit and does not mark route failed.
  - Invalid model projects to `Needs Setup`.
  - Invalid key projects affected provider options to `Needs Setup`.

- [ ] 4.5 Add Test Now force behavior.
  - `POST /api/llm/routes/{route_id}/probe?force=true` bypasses the active route circuit for that one probe attempt.
  - Success closes the route circuit in the same transaction as capability/callable-state update.
  - Transient failure refreshes or extends the circuit.
  - Hard setup failure updates config validity and projects to `Needs Setup`.
  - Add tests for success clear, transient refresh, and hard setup projection.

## Phase 5: Role Materializer and Schema v3

- [ ] 5.1 Add role authoring schema.
  - Modify: `apps/studio/backend/app/models/llm_config.py`.
  - Add `schema_version: 3` authoring support.
  - Add `role_kind`, Role intent, Model Group entries, provider route selections, `model_fallback_enabled`, and materialization report.
  - Preserve generated gateway-compatible `fallback_chain`.

- [ ] 5.2 Add materializer module.
  - Create: `apps/studio/backend/app/services/llm_role_materializer.py`.
  - Input: Role authoring, registry facts, capability facts, health projections.
  - Output: generated `fallback_chain`, Role Fit results, resolved runtime settings, warnings, skipped provider details.

- [ ] 5.3 Implement materializer rules.
  - Preserve Model Group order.
  - Preserve provider order inside each Model Group.
  - Provider fallback always remains enabled.
  - If `model_fallback_enabled=false`, only the first Model Group contributes providers.
  - `Needs Setup` and `Off` do not enter generated `fallback_chain`.
  - Existing selected `Cooling Down` providers may remain in authoring and generated chain; gateway admission may temporary-skip them.
  - `Not Fit` does not enter this Role's generated chain.
  - `Downgraded` enters chain with warning.
  - `Needs Test` blocks required capability usage for this Role, not global provider availability.
  - If `model_fallback_enabled=true`, append provider fallback lists from all Model Groups in order.
  - If `provider_preference=manual_order`, preserve user provider order without automatic official/ready reordering.

- [ ] 5.4 Migrate v2 roles.
  - Existing flat `fallback_chain` converts to Model Groups grouped by backend model group/canonical ID while preserving order.
  - Existing `model_profiles` migrate to `model_bundles` or temporary compatibility alias.
  - Old `disabled` projects to user-enabled false.
  - Old `failed` with a clear hard setup reason remains a hard setup projection.
  - Old `failed` without a clear hard setup reason migrates to `unverified_manual` plus `migration_warning`.
  - Existing roles receive `role_kind`; known Copilot roles become `copilot`, others default to `graph_agent`.

- [ ] 5.5 Add materializer tests.
  - Provider fallback remains when model fallback disabled.
  - Second Model Group is excluded when model fallback disabled.
  - With `model_fallback_enabled=true`, generated chain includes all Model Groups in order.
  - Missing key route is skipped and warning produced.
  - Cooling Down selected route remains represented and gets warning.
  - Thinking preferred unknown downgrades/warns.
  - Thinking required unknown produces `Needs Test`.
  - Thinking required unsupported produces `Not Fit`.
  - Manual provider order is preserved.
  - Migration converts ambiguous old `failed` to `unverified_manual` with warning.

## Phase 6: Role APIs and Role Test

- [ ] 6.1 Update role save API.
  - Modify: `apps/studio/backend/app/routers/llm.py`.
  - `PUT /api/llm/roles/{role_name}` saves authoring truth, runs materializer, rewrites generated `fallback_chain`, stores materialization report, and returns projections/warnings.

- [ ] 6.2 Add Role Test API.
  - Create: `POST /api/llm/roles/{role_name}/test`.
  - Test the persisted role only; draft test flow is frontend `PUT` then `POST /test`.
  - Reuse the same materializer.
  - Use the same admission logic as runtime.
  - Execute real minimal provider calls.
  - Default per rate-limit bucket concurrency is 3.
  - Provider fallback remains on.

- [ ] 6.3 Add Role Test response shape.
  - Include provider label, raw `route_id`, provider UI state, Role Fit, admission decision, status, warnings, retry time, and message.
  - Distinguish materialization warnings, admission skips, transient provider failures, hard setup failures, and aggregate failure.

- [ ] 6.4 Add backend tests.
  - PUT role regenerates `fallback_chain` atomically.
  - Role Test reads the saved role and does not accept ad hoc draft role payloads.
  - Role Test reports downgrade warnings.
  - Cooling Down provider reports retry time.
  - Hard invalid provider reports `Needs Setup` but fallback continues.
  - All providers failing returns aggregate failure.

## Phase 7: Copilot Uses Real Gateway Fallback

- [ ] 7.1 Update Copilot execution path.
  - Modify: `apps/studio/backend/app/services/copilot.py`.
  - Stop executing only `fallback_chain[0]`.
  - Use `GatewayChatModel` or an equivalent gateway-backed fallback loop for `copilot_chat`.

- [ ] 7.2 Preserve Copilot streaming contract.
  - Existing websocket events and Copilot UI contract must remain stable.
  - Model override still resolves to a concrete provider when explicitly selected.

- [ ] 7.3 Add Copilot fallback tests.
  - First provider transient failure falls back to second.
  - First provider hard failure records health event and falls back.
  - All providers failing returns a clear Copilot error event.
  - Existing Copilot route registry tests remain valid.

## Phase 8: Frontend API Types

- [ ] 8.1 Update LLM API types.
  - Modify: `apps/studio/frontend/src/api/llm.ts`.
  - Add `ProviderUiState = 'ready' | 'untested' | 'cooling_down' | 'needs_setup' | 'off'`.
  - Add `RoleFitState = 'using' | 'downgraded' | 'needs_test' | 'not_fit'`.
  - Add provider state projection and Role Fit projection DTOs.
  - Add `provider_kind`, `rate_limit_bucket`, `role_kind`, `retry_at`, and `capability_state` fields.

- [ ] 8.2 Stop deriving user-visible status from raw `RouteStatus`.
  - Raw `RouteStatus` may remain for compatibility.
  - UI status comes from backend projection.
  - Raw IDs remain only in save payloads and debug diagnostics.

- [ ] 8.3 Add frontend API tests.
  - Missing key and invalid model both render top-level `Needs Setup`.
  - Cooling Down keeps retry time.
  - Legacy registry without projection maps through compatibility fallback.

## Phase 9: Frontend LLM Roles UI

- [ ] 9.1 Add state components.
  - Split existing LLM Roles code into `apps/studio/frontend/src/components/studio/settings/llm-roles/` before adding new UI components.
  - Keep the existing `LlmRolesTab.tsx` entry point as a thin compatibility wrapper until routing/imports are switched.
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/provider-state-badge.tsx`.
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/role-fit-badge.tsx`.
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/cooling-down-countdown.tsx`.
  - Use local shadcn/Radix wrappers such as `Badge`, `Tooltip`, `Button`, and `Item`.

- [ ] 9.2 Provider state badge renders only five labels.
  - `Ready`
  - `Untested`
  - `Cooling Down`
  - `Needs Setup`
  - `Off`
  - Reason codes appear only in tooltip/detail, not as separate top-level badges.

- [ ] 9.3 Role Fit badge renders only four labels.
  - `Using`
  - `Downgraded`
  - `Needs Test`
  - `Not Fit`

- [ ] 9.4 Cooling Down UI.
  - Countdown derives from `retry_at`.
  - Countdown updates once per second.
  - `Test Now` calls `POST /api/llm/routes/{route_id}/probe?force=true` once.
  - Visible copy must not expose route/endpoint/canonical wording.

- [ ] 9.5 Restore Model Group-first Roles UX.
  - Right panel title is `Available Models`.
  - Right panel shows Model Group cards as the main list.
  - Valid/tested Model Bundles appear only in a visually distinct `Pinned Model Bundles` slot above Model Groups.
  - Singleton ungrouped provider model options appear as singleton Model Groups.
  - Dragging a Model Group into a Role creates a Role Model Group block.
  - Provider rows appear under the Role Model Group.
  - Default provider selection excludes `Needs Setup`, `Off`, and new `Cooling Down` when alternatives exist.

- [ ] 9.6 Preserve Studio UI guardrails.
  - Use `CatalogAccordion` for Graph Agent Roles and Copilot Roles sections.
  - Use local `Dialog`, `DropdownMenu`, `DeleteConfirmDialog`, `Tooltip`, and `Field` wrappers.
  - Keep pointer-based drag fallback for Tauri/WebKit.
  - Avoid visible primary `route`, `endpoint`, or `canonical` copy.
  - Keep exact `route_id` only in payloads or debug tooltips.

- [ ] 9.7 Add frontend tests.
  - Available Models does not render route/endpoint/canonical as primary visible labels.
  - Default provider selection follows persisted `provider_kind`, `RoleIntent.provider_preference`, official-only filter, state priority, and Cooling Down exclusion rules.
  - Model Group drag creates provider rows.
  - Needs Setup reason appears only in tooltip/detail.
  - Cooling Down row shows countdown and Test Now.
  - Cooling Down countdown updates once per second.
  - Pinned Model Bundle cards remain visually distinct from Model Group cards.
  - Autosave ignores superseded stale responses.

- [ ] 9.8 Update shared frontend UI spec.
  - Modify: `docs/development/FRONTEND_UI_SPEC.md` section 2.
  - Add durable rules for provider state badge labels, Role Fit labels, Cooling Down countdown/Test Now, and `Available Models` Model Group plus pinned bundle layout.

## Phase 10: Advanced Model Bundles

- [ ] 10.1 Add `model_bundles` backend API.
  - Existing `model_profiles` are migration/compatibility input only.
  - New product API and UI use `Advanced Model Bundles`.

- [ ] 10.2 Add Advanced Model Bundles UI.
  - Place below main Role sections.
  - Bundle authoring reuses Model Group and Provider rows.
  - Bundle provider states use the same five provider UI states.

- [ ] 10.3 Add pinned bundle display.
  - Valid/tested bundles appear pinned in `Available Models`.
  - Bundle cards remain visually distinct from regular Model Group cards.
  - Normal Role flow must not require bundle creation.

- [ ] 10.4 Add bundle tests.
  - Old model profile migrates to model bundle.
  - Bundle appears pinned after save/test.
  - Dragging bundle into Role uses same materializer.

## Phase 11: Verification

- [ ] 11.1 Run gateway tests.
  - `pytest packages/graph-agent-gateway/tests -q`

- [ ] 11.2 Run Studio backend tests.
  - `pytest apps/studio/backend/tests -q`

- [ ] 11.3 Run frontend checks.
  - `pnpm --dir apps/studio/frontend run typecheck`
  - `pnpm --dir apps/studio/frontend run lint`
  - `pnpm --dir apps/studio/frontend run test`
  - `pnpm --dir apps/studio/frontend run build`

- [ ] 11.4 Manual Studio verification.
  - Start Studio with `cd apps/studio/tauri && cargo tauri dev`.
  - Open Settings -> LLM Roles.
  - Verify no primary visible `route`, `endpoint`, or `canonical` wording.
  - Missing key and invalid model both show `Needs Setup`.
  - User-disabled option shows `Off`.
  - Simulated transient runtime failure shows `Cooling Down · retry in Ns`.
  - `Test Now` clears Cooling Down on success.
  - Drag Model Group into Role.
  - Reorder Model Groups and provider rows.
  - Verify Role Fit labels: `Using`, `Downgraded`, `Needs Test`, `Not Fit`.
  - Run Capability Test and Role Test.
  - Verify Copilot fallback.
  - Verify narrow-width layout does not overflow.

- [ ] 11.5 Record verification.
  - Commands run.
  - Manual workflows checked.
  - Any skipped verification and reason.
