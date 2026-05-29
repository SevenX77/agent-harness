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

- [x] Replace visible legacy model short-code labels with Model Group labels.
- [x] Replace visible provider short-code labels with provider labels.
- [x] Render provider rows under each Model Group.
- [x] Keep provider row add/remove/reorder controls aligned with current style.
- [x] Keep role action menu, edit dialog, delete dialog, and model fallback switch behavior.
- [x] Verify model-group reorder changes model fallback order.
- [x] Verify provider reorder changes only provider fallback order inside one Model Group.
- [x] Verify remove provider and remove Model Group.
- [x] Run focused LLM Roles frontend tests.
- [x] Run typecheck/lint.
- [x] Real browser/Tauri verification including narrow viewport.
- [x] Wait for user confirmation.
- [x] Commit only PR 3 files.

## PR 4: Provider State, Role Fit, Cooling Down

- [x] Keep Available Models provider state rendering for `Ready`, `Untested`, `Cooling Down`, `Needs Setup`, `Off`.
- [x] Map backend provider state, Role Fit, and latest row test result into role-row statuses: `Can Run`, `Limited`, `Blocked`.
- [x] Use role-row status for provider row border color and compact status light; do not render role-row text status badges.
- [x] Keep detailed reason/capability diagnostics, including `Cooling Down`, in the status light tooltip/detail only.
- [x] Remove raw `Provider state` / `Role fit` labels from role cards.
- [x] Remove role-card `Cooling Down` `Test Now`; route/global availability remains owned by API Keys/registry testing.
- [x] Add frontend tests for five provider states and role-row three-state status lights.
- [x] Run focused tests.
- [x] Run typecheck/lint.
- [x] Real browser/Tauri verification for Available Models state rendering and role-row three-state rendering.
- [ ] Wait for user confirmation.
- [ ] Commit only PR 4 files.

## PR 5: Capability Test and Role Test Result Surfaces

- [x] Add frontend API call for Role Test if missing.
- [x] Save draft Role before Role Test, including pending debounce snapshots.
- [x] Render Role Test result with provider label, status, role fit, warnings, retry time, and aggregate result.
- [x] Keep Capability Test separate from Role Test in visible copy.
- [x] Show downgrade and needs-test warnings after materialization/test result.
- [x] Verify all-provider-failed aggregate state.
- [x] Run focused tests.
- [x] Run typecheck.
- [x] Run lint.
- [x] Real browser/Tauri Role Test verification.
- [ ] Wait for user confirmation.
- [ ] Commit only PR 5 files.

## PR 6: Advanced Model Bundles and Final Pass

- [x] Add `Advanced Model Bundles` section below role sections.
- [x] Add bundle authoring surface backed by exact route-id fallback chains.
- [x] Add pinned bundle slot above normal Model Groups in Available Models.
- [x] Ensure normal Model Group drag/drop does not require bundle creation.
- [x] Wire bundle drag/drop through the same Model Group drop path.
- [x] Preserve `model_bundles` in backend roles PUT.
- [x] Run focused bundle tests.
- [x] Run full frontend test/typecheck/lint.
- [x] Run final browser/Tauri verification across desktop and narrow widths.
- [ ] Wait for user confirmation.
- [ ] Commit only PR 6 files.

## Tracking Notes

- PR 1 was confirmed and committed as `91accd5 Split Studio LLM display projection from gateway runtime`.
- PR 2 was confirmed and committed as `ae0dc11 Preserve exact LLM role provider routes`.
- PR 3 role-card Model Group/provider-row work was confirmed and committed as `7f337cd Complete LLM role provider rows`.
- Route provider credential/test state must map through owning `endpoint_id`; `route_id` remains the execution target only.
- Role card top-level Test is the persisted Role Test; global route/provider availability remains owned by API Keys testing.
- Role card provider rows collapse backend provider state, Role Fit, and latest row test result into `Can Run` / `Limited` / `Blocked` border/light states; raw provider state labels stay in Available Models / API Keys surfaces, and exact capability/cooling-down diagnostics live in the status-light tooltip.
- PR 5 Role Test saves pending role drafts first, then calls persisted `/api/llm/roles/{role_name}/test`; the result surface shows provider-level role fit diagnostics and keeps raw route IDs out of visible copy.
- PR 5 backend Role Test probes eligible provider routes concurrently when live provider checks are needed.
- Role Test must not trust old API Keys results as proof of current role executability; when role capability fit is unknown and marked `needs_test`, it re-probes the selected route at click time using the resolved role runtime settings. Known unsupported required capability (`not_fit`) remains blocked without provider traffic.
- PR 6 Advanced Model Bundles are pinned above normal Available Models and persist as `model_bundles` with exact `route_id` fallback chains.
- Role-level preference authoring UI now lives on the Role header settings dialog. Model Group rows no longer expose aggregate Connected/Failed badges or per-model settings; role settings write `role.intent.provider_preference`, `role.intent.thinking`, and optional `role.intent.target_output_tokens`.
