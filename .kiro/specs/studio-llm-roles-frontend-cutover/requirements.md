---
status: Draft
created: 2026-05-27
owner: Studio
supersedes_scope:
  - .kiro/specs/studio-llm-roles-model-groups/tasks.md Phase 8
  - .kiro/specs/studio-llm-roles-model-groups/tasks.md Phase 9
related_specs:
  - .kiro/specs/studio-llm-roles-model-groups/
  - .kiro/specs/studio-gateway-runtime-schema-boundary/
related_code_paths:
  - apps/studio/frontend/src/api/llm.ts
  - apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx
  - apps/studio/frontend/src/components/studio/settings/llm-roles/
  - apps/studio/frontend/src/components/studio/settings/role-utils.ts
  - docs/development/FRONTEND_UI_SPEC.md
---

# Studio LLM Roles Frontend Cutover Requirements

## Context

This spec persists the LLM Roles frontend cutover as six small PR-sized units. The goal is to keep maximum revert space while replacing the old short-code model/provider frontend logic with the route-backed Studio Backend DTOs defined by `studio-llm-roles-model-groups`.

The visual UI is already largely locked. Implementation must keep the current Settings -> LLM Roles layout, component hierarchy, and interaction feel. Changes are primarily data wiring, state projection, drag/drop payloads, and testing/result surfaces.

Frontend development for this cutover does not require TDD. Each PR still requires existing tests, typecheck/lint, and real browser/Tauri verification with screenshots or clear manual evidence before asking for user confirmation. A PR is committed only after the user confirms that phase.

## Global Rules

1. Frontend visible copy must use user-facing terms: `Available Models`, `Model Group`, `Provider`, `Model Bundle`, `Fallback`, `Capability`, and `Test`.
2. Frontend primary UI must not display `route`, `endpoint`, or `canonical`.
3. Exact execution identity is always the backend `route_id`; frontend must never infer it from display name or provider label.
4. Model display name, grouping, provider state, role fit, and capability summaries are Studio Backend projections. Frontend displays those projections directly.
5. Frontend may keep minimal defensive fallback for missing optional fields, but fallback must not become the authoritative model identity implementation.
6. Each PR must be independently reviewable and revertable.
7. Each PR must avoid unrelated API Keys changes and unrelated Settings refactors.
8. Each PR must update `docs/development/FRONTEND_UI_SPEC.md` when it creates a reusable UI rule.

## PR 1: Available Models Reads Backend Model Groups

**Goal:** Replace credential-derived available model cards with backend `model_groups` cards while keeping the current right sidebar layout.

Acceptance criteria:

1. `SettingsPage` loads roles and model groups for LLM Roles.
2. `AvailableModelsSidebar` accepts `ModelGroup[]`, not `CredentialsState`, as its source of cards.
3. Card title uses backend-projected `model_groups[].display_name`.
4. Section label uses backend-projected model family/provider family metadata once provided by backend; until then it may use a temporary frontend grouping fallback only for section placement.
5. Provider chips use provider labels from backend DTOs and color from provider `ui_state`.
6. The old second-layer count badge such as `1 Untested` is not rendered on each card.
7. Model titles use normal UI font, not mono/code style.
8. Search matches display name, provider label, provider model ID, exact route ID, and canonical/model group ID without exposing internal IDs as visible card labels.
9. Long lists keep progressive rendering and do not overflow the right sidebar.
10. Real browser verification must include searching `opus` and `deepseek v3.1 thinking`.

## PR 2: Drag/Drop Saves Exact Route-Backed Model Group Selection

**Goal:** Dragging a Model Group into a Role writes exact backend route IDs while preserving the old mental model: role -> model -> providers.

Acceptance criteria:

1. Available Model drag payload is the Model Group ID supplied by backend.
2. Drop target resolves the current Model Group DTO and uses selected provider model options from that DTO.
3. Default provider selection includes `ready` and `untested`.
4. Default provider selection excludes `needs_setup` and `off`.
5. `cooling_down` is not selected by default when non-cooling candidates exist.
6. Official providers sort before third-party/custom when no role-specific provider preference overrides it.
7. Saved role data contains exact `route_id` values for selected providers.
8. Frontend does not create hidden default bundles or prompt for bundle creation during normal drop.
9. Autosave must not let stale failed saves override newer successful saves.
10. Manual verification must drag one Model Group into a Role and inspect the outbound PUT payload.

## PR 3: Role Cards Render Model Group and Provider Rows From Backend Shape

**Goal:** Replace legacy visible model/provider short-code rows with Model Group blocks and provider rows that match the agreed UX.

Acceptance criteria:

1. Role card shows ordered Model Group blocks.
2. Each Model Group block shows ordered provider rows.
3. Provider row label is provider display label, not route ID or provider model ID.
4. Model Group label is backend display name.
5. Existing role edit/delete/menu interactions remain in the current shadcn/Radix wrappers.
6. Reordering Model Groups changes model fallback order.
7. Reordering providers inside one Model Group changes only provider fallback order.
8. Removing a provider removes only that provider model option.
9. Removing a Model Group removes the whole group.
10. Manual verification must cover add, reorder, remove provider, remove model group, and narrow-width layout.

## PR 4: Provider State, Role Fit, Cooling Down, and Test Now

**Goal:** Wire user-actionable state labels without exposing raw gateway status or low-level reason codes as top-level UI states.

Acceptance criteria:

1. Provider UI state labels are exactly `Ready`, `Untested`, `Cooling Down`, `Needs Setup`, and `Off`.
2. Role Fit labels are exactly `Using`, `Downgraded`, `Needs Test`, and `Not Fit`.
3. Missing key, invalid key, invalid model, invalid base URL, invalid protocol, and equivalent hard setup failures all display as `Needs Setup`.
4. `Cooling Down` shows countdown or retry time from backend `retry_at`.
5. `Test Now` for Cooling Down calls `POST /api/llm/routes/{route_id}/probe?force=true`.
6. Reason codes remain in tooltip/detail/test report, not as separate top-level labels.
7. `Off` is user-driven only.
8. Frontend never branches on raw `RouteStatus` when a backend projection is available.
9. Manual verification must cover all five provider UI states and at least one Role Fit warning state with mocked or real backend state.

## PR 5: Capability Test and Role Test UI Wiring

**Goal:** Make tests explain two different things: what a provider model can do, and whether a full Role fallback plan works.

Acceptance criteria:

1. Capability Test is scoped to one provider model option.
2. Role Test is scoped to one persisted role.
3. Draft Role Test flow is save first, then `POST /api/llm/roles/{role_name}/test`.
4. Role Test result shows provider label, provider state, Role Fit, admission/skip/failure, retry time, warning messages, and aggregate result.
5. Downgrades such as "requested 128k output, using 64k" are visible immediately after materialization or Role Test.
6. Runtime failures in one provider do not hide later fallback attempts.
7. Test buttons use current page styling and do not introduce a landing-page or wizard pattern.
8. Manual verification must run a Role Test and confirm warnings/results render without route/endpoint/canonical primary copy.

## PR 6: Advanced Model Bundles and Final Visual Pass

**Goal:** Add the advanced bundle surface after normal Model Group authoring works.

Acceptance criteria:

1. UI label is `Advanced Model Bundles`.
2. Bundle authoring appears below Role sections.
3. Valid/tested bundles appear in a visually distinct pinned slot above normal Model Groups in `Available Models`.
4. Normal users are not required to create a bundle before adding a Model Group to a Role.
5. Bundle cards use model/provider language and exact backend route IDs internally.
6. Dragging a bundle into a Role uses the same materializer path as normal Model Groups.
7. Manual verification must cover creating a bundle, testing it, seeing it pinned, and dragging it into a Role.
8. Final PR must run the full frontend verification set and a Tauri or equivalent real browser pass.

## Commit and Confirmation Policy

1. Do not commit a PR phase until the user confirms the phase output.
2. Each commit must stage only files belonging to that PR phase.
3. If unrelated dirty files exist, use partial staging or delay commit.
4. Each phase report must include changed files, verification commands, browser/Tauri checks, and any known carry-forward items.

