---
status: Draft
created: 2026-05-27
owner: Studio
related_requirements: .kiro/specs/studio-llm-roles-frontend-cutover/requirements.md
---

# Studio LLM Roles Frontend Cutover Tasks

> Required for UI work: read `docs/development/FRONTEND_UI_SPEC.md` section 2 before each PR, and use local `apps/studio/frontend/src/components/ui/` wrappers where applicable.

## PR 1: Available Models from Backend Model Groups

- [ ] Load `modelGroups` in `SettingsPage.tsx` using `getModelGroups()`.
- [ ] Pass `modelGroups` through `SettingsPageContent.tsx` into `LlmRolesTab.tsx`.
- [ ] Change `AvailableModelsSidebar.tsx` source prop from `credentials` to `modelGroups`.
- [ ] Render card title from backend `model_groups[].display_name`.
- [ ] Render provider chips from backend `provider_models[].provider_label` and `ui_state`.
- [ ] Remove per-card second-layer count badges such as `1 Untested`.
- [ ] Use normal UI font for model titles.
- [ ] Keep progressive rendering for long lists.
- [ ] Verify search for `opus` and `deepseek v3.1 thinking`.
- [ ] Run `pnpm --dir apps/studio/frontend test src/components/studio/settings/LlmRolesTab.test.tsx -- --runInBand`.
- [ ] Run `pnpm --dir apps/studio/frontend run typecheck`.
- [ ] Run `pnpm --dir apps/studio/frontend run lint`.
- [ ] Real browser/Tauri screenshot: right sidebar with `opus` search.
- [ ] Wait for user confirmation.
- [ ] Commit only PR 1 files.

## PR 2: Drop Model Group and Save Exact Route IDs

- [ ] Add Model Group lookup map in `LlmRolesTab.tsx`.
- [ ] Ensure drag payload carries backend Model Group ID.
- [ ] Add helper that appends a Model Group to role data with exact `route_id` provider entries.
- [ ] Default provider selection includes `ready` and `untested`.
- [ ] Default provider selection excludes `needs_setup` and `off`.
- [ ] Exclude `cooling_down` by default when other usable providers exist.
- [ ] Sort official providers before third-party/custom unless role preference says otherwise.
- [ ] Keep existing role autosave behavior and stale-response protection.
- [ ] Verify outbound PUT payload contains exact route IDs and no inferred provider labels as execution IDs.
- [ ] Run focused LLM Roles frontend tests.
- [ ] Run typecheck/lint.
- [ ] Real browser/Tauri drag/drop verification.
- [ ] Wait for user confirmation.
- [ ] Commit only PR 2 files.

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

- Current PR 1 work is in progress and must not be committed until user confirms.
- Existing unrelated API Keys dirty files must not be staged with LLM Roles commits.
- If the Gateway display-name boundary spec changes backend DTO names, PR 1 must be adjusted before commit so frontend consumes Studio Backend display projection rather than Gateway-derived route display fields.

