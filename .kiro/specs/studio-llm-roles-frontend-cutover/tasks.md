---
status: Draft
created: 2026-05-27
owner: Studio
related_requirements: .kiro/specs/studio-llm-roles-frontend-cutover/requirements.md
---

# Studio LLM Roles Frontend Cutover Tasks

> Required for UI work: read `docs/development/FRONTEND_UI_SPEC.md` section 2 before each PR, and use local `apps/studio/frontend/src/components/ui/` wrappers where applicable.

## PR 1: Available Models from Backend Model Groups

- [x] Load `modelGroups` in `SettingsPage.tsx` using `getModelGroups()`.
- [x] Pass `modelGroups` through `SettingsPageContent.tsx` into `LlmRolesTab.tsx`.
- [x] Change `AvailableModelsSidebar.tsx` source prop from `credentials` to `modelGroups`.
- [x] Render card title from backend `model_groups[].display_name`.
- [x] Render provider chips from backend `provider_models[].provider_label` and `ui_state`.
- [x] Remove per-card second-layer count badges such as `1 Untested`.
- [x] Use normal UI font for model titles.
- [x] Keep progressive rendering for long lists.
- [x] Verify search for `opus` and `deepseek v3.1 thinking`.
- [x] Run `pnpm --dir apps/studio/frontend test src/components/studio/settings/LlmRolesTab.test.tsx -- --runInBand`.
- [x] Run `pnpm --dir apps/studio/frontend run typecheck`.
- [x] Run `pnpm --dir apps/studio/frontend run lint`.
- [x] Real browser/Tauri screenshot: right sidebar with `opus` search.
- [x] Wait for user confirmation.
- [x] Commit only PR 1 files.

## PR 2: Drop Model Group and Save Exact Route IDs

- [x] Add Model Group lookup map in `LlmRolesTab.tsx`.
- [x] Ensure drag payload carries backend Model Group ID.
- [x] Add helper that appends a Model Group to role data with exact `route_id` provider entries.
- [x] Default provider selection preserves every backend route in the dragged Model Group.
- [x] Keep `needs_setup`, `cooling_down`, and `off` routes visible after drag/drop so users can decide whether to remove them.
- [x] Sort selected routes ready-first, then by provider kind/name.
- [x] Route-backed providers are not pruned by legacy available-model ownership heuristics.
- [x] Keep existing role autosave behavior and stale-response protection.
- [x] Verify outbound PUT payload contains exact route IDs and no inferred provider labels as execution IDs.
- [x] Run focused LLM Roles frontend tests.
- [x] Run typecheck/lint.
- [x] Real browser/Tauri drag/drop verification.
- [x] Wait for user confirmation.
- [x] Commit only PR 2 files.

## PR 3: Role Card Model Group and Provider Rows

- [ ] Replace visible legacy model short-code labels with Model Group labels.
- [ ] Replace visible provider short-code labels with provider labels.
- [ ] Render provider rows under each Model Group.
- [ ] Keep provider row add/remove/reorder controls aligned with current style.
- [ ] Keep role action menu, edit dialog, delete dialog, and model fallback switch behavior.
- [ ] Verify model-group reorder changes model fallback order.
- [ ] Verify provider reorder changes only provider fallback order inside one Model Group.
- [ ] Verify remove provider and remove Model Group.
- [ ] Run focused LLM Roles frontend tests.
- [ ] Run typecheck/lint.
- [ ] Real browser/Tauri verification including narrow viewport.
- [ ] Wait for user confirmation.
- [ ] Commit only PR 3 files.

## PR 4: Provider State, Role Fit, Cooling Down

- [ ] Add provider state rendering for `Ready`, `Untested`, `Cooling Down`, `Needs Setup`, `Off`.
- [ ] Add Role Fit rendering for `Using`, `Downgraded`, `Needs Test`, `Not Fit`.
- [ ] Add `CoolingDownCountdown` using backend `retry_at`.
- [ ] Wire `Test Now` to `POST /api/llm/routes/{route_id}/probe?force=true`.
- [ ] Keep reason codes in tooltip/detail only.
- [ ] Remove frontend branching on raw `RouteStatus` when projection fields exist.
- [ ] Add frontend tests for five provider states and four Role Fit labels.
- [ ] Run focused tests.
- [ ] Run typecheck/lint.
- [ ] Real browser/Tauri verification for state rendering and Test Now.
- [ ] Wait for user confirmation.
- [ ] Commit only PR 4 files.

## PR 5: Capability Test and Role Test Result Surfaces

- [ ] Add frontend API call for Role Test if missing.
- [ ] Save draft Role before Role Test.
- [ ] Render Role Test result with provider label, status, role fit, warnings, retry time, and aggregate result.
- [ ] Keep Capability Test separate from Role Test in visible copy.
- [ ] Show downgrade and needs-test warnings after materialization/test result.
- [ ] Verify all-provider-failed aggregate state.
- [ ] Run focused tests.
- [ ] Run typecheck/lint.
- [ ] Real browser/Tauri Role Test verification.
- [ ] Wait for user confirmation.
- [ ] Commit only PR 5 files.

## PR 6: Advanced Model Bundles and Final Pass

- [ ] Add `Advanced Model Bundles` section below role sections.
- [ ] Add bundle authoring surface using the same Model Group and provider row components.
- [ ] Add pinned bundle slot above normal Model Groups in Available Models.
- [ ] Ensure normal Model Group drag/drop does not require bundle creation.
- [ ] Wire bundle drag/drop through the same backend materializer route path.
- [ ] Run focused bundle tests.
- [ ] Run full frontend test/typecheck/lint.
- [ ] Run final browser/Tauri verification across desktop and narrow widths.
- [ ] Wait for user confirmation.
- [ ] Commit only PR 6 files.

## Tracking Notes

- PR 1 was confirmed and committed as `91accd5 Split Studio LLM display projection from gateway runtime`.
- PR 2 route/drop exact route-id work is implemented, verified, and accepted for local commit.
- Route provider credential/test state must map through owning `endpoint_id`; `route_id` remains the execution target only.
- Role card provider-row Test is provider-level and runs different provider routes concurrently; runtime fallback/aggregate Role Test remains PR 5 scope.
