---
status: Draft
created: 2026-05-26
owner: Studio
supersedes:
  - .kiro/specs/llm-roles-setting/
amends:
  - .kiro/specs/llm-provider-intelligence-v2/
  - .kiro/specs/studio-api-keys-regression-hardening/
related_code_paths:
  - apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx
  - apps/studio/frontend/src/components/studio/settings/llm-roles/
  - apps/studio/frontend/src/components/studio/settings/role-utils.ts
  - apps/studio/frontend/src/api/llm.ts
  - apps/studio/backend/app/routers/llm.py
  - apps/studio/backend/app/services/llm_roles.py
  - packages/graph-agent-gateway/src/graph_agent_gateway/registry/
---

# Studio LLM Roles Model Groups Requirements

## Context

Studio LLM Roles is being restored to the earlier user-facing UX while the backend remains on the new endpoint/route registry core. The restored UI must keep user language centered on models, providers, roles, fallbacks, and model groups. Backend terms such as `route`, `endpoint`, and `canonical` are valid in APIs, storage, tests, and engineering documentation, but they must not appear as primary visible copy in the user interface.

The new backend fact model is still route-backed: a concrete callable target is a `ProviderRoute` tied to exactly one `ProviderEndpoint`. The user should not have to reason about that directly. The UI should show normalized Model Groups, each containing provider-specific model options. When a user adds a Model Group to a Role, the Role stores the selected concrete route IDs under that Model Group.

This spec supersedes the older `llm-roles-setting` UX that exposed `models/providers` short-code state. It amends `llm-provider-intelligence-v2` by introducing a user-facing Model Group role schema and by clarifying that flat route chains are an internal execution expansion, not the main Studio Roles authoring UX.

### Amendments to upstream specs

- `.kiro/specs/llm-provider-intelligence-v2/requirements.md` REQ-02A and `.kiro/specs/llm-provider-intelligence-v2/design.md` sections 3.3, 3.4, 8.4, 8.5, and 10: this spec overrides any Role authoring UI that presents flat route chains, `model_profiles`, or direct route selection as the main Studio Roles path. V2 route facts, provider route identity, capability facts, and gateway-compatible fallback chains remain valid backend primitives, but Studio LLM Roles authoring is Model Group -> Provider.
- `.kiro/specs/studio-api-keys-regression-hardening/design.md` sections `Phase 2: v4 API Integration`, `Provider Test Result`, and `.kiro/specs/studio-api-keys-regression-hardening/tasks.md` tasks 7-9: provider chips, provider ownership, model availability, and provider status shown in LLM Roles must come from backend Model Group DTOs and state projections. API Keys settings may seed `provider_kind` for provider endpoints, but the LLM Roles frontend must not infer provider kind, ownership, canonical grouping, or status from raw model strings.

## Glossary

| Engineering term | User-facing term | Meaning |
|---|---|---|
| `canonical_id` / canonical group | Model Group | A normalized model identity shown as one card, for example "Claude Sonnet 4.7". |
| `ProviderEndpoint` | Provider | One configured provider account/API entry, for example "Anthropic Official" or "OpenRouter". |
| `ProviderRoute` / `route_id` | Provider model option | One concrete model on one provider. The UI can show the provider label and model name, but not the word route. |
| `route_chain` | Provider fallback order | Ordered provider-specific model options inside one Model Group. |
| role model chain | Model fallback order | Ordered Model Groups inside a Role. |
| route capability probe | Capability Test | Test that discovers what one provider model option supports. |
| role fallback execution test | Role Test | Test that verifies the whole Role fallback plan and reports warnings. |

## Requirement 1: UI copy must preserve model/provider language

**Goal:** As a Studio user, I want to configure roles using model and provider language, not backend registry terminology.

### Acceptance Criteria

1. LLM Roles UI must not use `route`, `endpoint`, or `canonical` as visible primary labels, section titles, action labels, empty states, or user instructions.
2. Visible copy must use terms such as `Available Models`, `Model Group`, `Provider`, `Official Provider`, `Third-party Provider`, `Model Bundle`, `Fallback`, `Capability`, and `Test`.
3. Engineering terms may remain in DTO field names, API paths, tests, logs, debug details, and hidden diagnostics.
4. Tooltips may include precise IDs only when useful for debugging, but the normal label must remain model/provider-oriented.

## Requirement 2: Available Models is Model Group-first

**Goal:** As a Studio user, I want the right-side library to show clean normalized model names instead of a mixed list of raw provider model IDs and pretty names.

### Acceptance Criteria

1. The right-side library is titled `Available Models`.
2. The primary cards in the library are Model Groups, not individual provider routes.
3. A Model Group card displays a normalized model name, provider count, status summary, and capability summary when known.
4. Individual provider model options are visible only inside a Model Group expansion or detail surface.
5. If the backend cannot confidently group one provider model option with any known group, it must still be presented as a singleton Model Group with the same visual format.
6. The UI must not mix raw strings such as `anthropic/sonnet-4-7-latest` with names such as `Claude Opus 4.7 Thinking` as peer card titles.
7. Search must match normalized model name, provider label, provider model ID, and exact internal IDs, with case-insensitive and punctuation-insensitive matching.
8. Model Group cards must support progressive rendering for long lists and must not horizontally overflow in narrow Settings panes.
9. Valid/tested Model Bundles may appear above Model Groups in a visually distinct `Pinned Model Bundles` slot, but they must not be mixed into the normal Model Group card list.

## Requirement 3: Dragging into a Role always adds a Model Group

**Goal:** As a Studio user, I want one consistent add flow: drag a model group into a role and then manage its providers inside the role.

### Acceptance Criteria

1. Dragging from `Available Models` into a Role must always add a Model Group card to that Role.
2. The UI must not provide a main-path action to drag a single provider model option directly into a Role.
3. The UI must not interrupt a drag/drop action with a create-bundle dialog or hidden "default bundle" decision.
4. After drop, the Role card shows the added Model Group with its selected provider model options.
5. The selected provider model options must be stored as exact backend `route_id` values, even though the UI labels them as Providers or provider model options.
6. A Model Group already present in a Role must not be duplicated; the drop should select/focus the existing card or merge newly available provider model options according to the default selection policy.

## Requirement 4: Default provider model selection must be predictable

**Goal:** As a Studio user, I expect the system to pick sensible provider options when I add a model group without forcing me into low-level configuration.

### Acceptance Criteria

1. When a Model Group is added to a Role, all available provider model options in usable states are candidates.
2. `Ready` and `Untested` provider model options are both valid default candidates. `Untested` means not verified yet, not unusable.
3. Official providers, when available, are ordered before third-party providers by default.
4. If an `Official only` filter is active in the right-side library, only official provider model options are added by default.
5. `Cooling Down` provider model options are not selected by default when alternatives exist, but already-selected Cooling Down options may remain in Role authoring so gateway admission can temporary-skip them at runtime.
6. `Needs Setup` and `Off` provider model options must not be selected by default.
7. If no usable provider model option exists, the drop must either be blocked or create a clearly invalid Model Group card that says no available provider; it must not silently create an executable fallback.
8. Provider ordering must use persisted `provider_kind`, not frontend string guessing.
9. `provider_kind` must support `official`, `third_party`, and `custom`; curated backend defaults may seed new endpoints, but user edits are authoritative.
10. If Role intent sets `provider_preference`, default provider ordering must honor it: `official_first` uses provider kind, `ready_first` uses UI state, and `manual_order` preserves registry/user order.

## Requirement 4A: Provider states are simple user-action labels

**Goal:** As a Studio user, I need each provider row to tell me what to do next without exposing backend reason-code complexity.

### Acceptance Criteria

1. Provider rows must expose only these top-level UI states: `Ready`, `Untested`, `Cooling Down`, `Needs Setup`, and `Off`.
2. Missing API key, invalid API key, invalid model, invalid base URL, invalid protocol, and equivalent hard setup errors must all project to `Needs Setup`.
3. `Off` must be user-driven only; tests and runtime failures must not silently turn a provider option off.
4. `Cooling Down` must appear only while a runtime circuit is open and must include a countdown or retry time.
5. A previous transient failure that no longer affects the next user action must not create a top-level `Recent Issue` state; it may appear only in tooltip, details, test report, or logs.
6. Backend reason codes may be returned for diagnostics, but they must not become separate top-level provider row badges.

## Requirement 4B: Role Fit is separate from provider health

**Goal:** As a Studio user, I need to understand whether a provider can serve this specific Role without confusing that with global provider availability.

### Acceptance Criteria

1. Role provider rows may expose only these Role Fit labels: `Using`, `Downgraded`, `Needs Test`, and `Not Fit`.
2. `Downgraded` means the provider enters the Role execution chain with reduced settings and visible warning.
3. `Needs Test` means a required capability is unknown and Capability Test is needed before the Role can safely use it.
4. `Not Fit` means the provider is proven incompatible with this Role's required intent.
5. Role Fit must never mark the global provider option as failed or unavailable for other Roles.

## Requirement 5: Role authoring is Model Group first

**Goal:** As a Studio user, I want each Role to show model fallback first and provider fallback second, matching the old UX while using exact backend provider model options.

### Acceptance Criteria

1. A Role card displays ordered Model Group cards.
2. Each Model Group card displays an ordered provider fallback list.
3. Reordering Model Group cards changes the role model fallback order.
4. Reordering providers inside one Model Group changes only that group's provider fallback order.
5. Removing a provider option removes only that provider model option from the group.
6. Removing a Model Group removes the whole group from the Role.
7. Role-level add/edit/delete actions must use the existing local shadcn/Radix wrappers, including `Dialog`, `DropdownMenu`, and `DeleteConfirmDialog`.
8. The Role-level model fallback switch controls only whether execution may continue from one Model Group to the next.
9. Provider fallback inside the active Model Group is always enabled; disabling model fallback must not disable provider fallback.

## Requirement 5A: Role taxonomy is explicit in storage

**Goal:** As a Studio maintainer, I need Graph Agent and Copilot roles to share the same schema while remaining clearly separated in the UI.

### Acceptance Criteria

1. Each role entry must store `role_kind: "graph_agent" | "copilot"`.
2. The frontend must split `Graph Agent Roles` and `Copilot Roles` by `role_kind`, not by role name convention.
3. The materializer must accept both role kinds through the same Model Group authoring schema.
4. Copilot roles must use the generated gateway fallback chain after the Copilot fallback implementation lands.
5. Migration must assign existing known Copilot role entries to `copilot` and existing graph agent role entries to `graph_agent`.

## Requirement 6: Users configure intent, not per-route parameters by default

**Goal:** As a Studio user, I want to say what a role needs, and have the system translate that intent into provider-specific runtime settings.

### Acceptance Criteria

1. Role-level settings must express user intent, such as provider preference, reasoning/thinking preference, target context budget, target output budget, and downgrade policy.
2. Model Group-level settings may override role-level intent for that model group only.
3. Provider model option-level runtime overrides are advanced controls and must not be the default authoring path.
4. The system must translate role/model-group intent into concrete provider runtime settings using backend capability facts.
5. If a target value cannot be satisfied, the system may downgrade only when the user's downgrade policy allows it.
6. Downgrades and unsupported preferences must be reported by materialization and Role Test; they must not be silent or delayed until only after Role Test.
7. The frontend must render configurable fields from backend descriptors rather than hardcoding provider-specific capability rules.

## Requirement 7: Capability Test and Role Test are separate concepts

**Goal:** As a Studio user, I need to know both what each provider model option can do and whether my whole role fallback plan works.

### Acceptance Criteria

1. Capability Test probes one provider model option and records its real capabilities.
2. Capability Test results are stored on the backend provider route record, not only in frontend state.
3. Capability Test must discover or validate facts such as callable status, max context, max output, thinking/reasoning support, tools support, structured output support, JSON mode support, stop sequence behavior, and relevant provider-specific runtime mappings when feasible.
4. Role Test expands the Role's Model Groups and provider fallback lists into a concrete execution plan.
5. Role Test resolves role-level and Model Group-level intent into per-provider runtime settings.
6. Role Test returns warnings for downgrades, unknown capabilities, skipped provider options, Cooling Down provider options, Needs Setup provider options, runtime failures, and unsupported required settings.
7. Role Test must surface warning details in the UI after completion. Examples include "requested 128k output, using 64k" or "thinking requested but capability is unknown".
8. Capability Test can run before or during Role Test, but the UI must distinguish capability discovery from role fallback verification.
9. `POST /api/llm/roles/{role_name}/test` must test the persisted Role only; draft testing is implemented by saving with `PUT /api/llm/roles/{role_name}` first.
10. Capability Test and Role Test concurrency must be limited by effective `rate_limit_bucket`; unset bucket means the provider endpoint ID.

## Requirement 7A: Gateway runtime health is visible and actionable

**Goal:** As a Studio user, I want to know when a provider is temporarily skipped by runtime health and be able to retry it deliberately.

### Acceptance Criteria

1. Gateway runtime must emit structured events for admission skip, probe success/failure, dispatch success/failure, hard failure, and transient failure.
2. Runtime health must be stored in a Health Store or equivalent durable runtime state, not only in a hidden in-memory cache.
3. A runtime circuit must include scope, reason code, opened time, retry time, TTL, failure count, and message when available.
4. Provider rows in `Cooling Down` must show a countdown or retry time derived from the circuit record.
5. `Test Now` must allow a user to force a probe or Capability Test for a Cooling Down provider option.
6. If `Test Now` succeeds, the circuit must close early and the UI must leave `Cooling Down`.
7. If `Test Now` fails transiently, the circuit must reopen or extend and refresh the countdown.
8. If `Test Now` detects hard setup failure, the provider row must project to `Needs Setup`.
9. `Test Now` must call `POST /api/llm/routes/{route_id}/probe?force=true`; success closes the route circuit in the same transaction as capability/callable-state update.
10. Runtime health must be persisted in durable app-local state, such as SQLite or equivalent local KV. In-memory health storage is allowed only in tests.
11. If route, endpoint, and rate-limit-bucket circuits all apply, the UI countdown must use the farthest future `retry_at`.

## Requirement 7B: Gateway admission is admit, temporary skip, or block

**Goal:** As a gateway maintainer, I need a clean execution gate that does not depend on Studio UI labels.

### Acceptance Criteria

1. Gateway admission must produce one of `admit`, `temporary_skip`, or `block`.
2. User-disabled endpoint/route, missing credential, hard invalid endpoint/route config, and known-illegal runtime settings must produce `block`.
3. Open runtime circuit before `retry_at` must produce `temporary_skip`.
4. Unknown capability, never-tested provider model options, healthy providers, and expired circuits must produce `admit`.
5. Provider fallback must remain on: a candidate failure records an event and continues to the next candidate.
6. Hard failures affect future admission but must not stop the current chain from trying later candidates.
7. Gateway must not consume Model Groups or Studio Role intent; Studio materializer owns Role Fit and generated fallback_chain.
8. Gateway lint must filter only `block` cases: disabled target, missing credential, hard invalid config, and known-illegal runtime settings.
9. Gateway lint must not block unknown capability or never-tested provider model options.

## Requirement 8: Model Bundle is advanced and not the default path

**Goal:** As a power user, I can create reusable model bundles with explicit provider-level configuration without making that complexity the normal Role flow.

### Acceptance Criteria

1. Advanced bundles are labeled `Model Bundle` or `Advanced Model Bundles`, not `Routes Bundle`.
2. The Model Bundle area appears below the main Role sections.
3. A Model Bundle can contain one or more Model Groups and provider model options.
4. A Model Bundle can define explicit provider fallback order and advanced runtime overrides.
5. A Model Bundle can be tested independently.
6. Tested/valid bundles must appear as pinned bundle cards in the right-side `Available Models` area and must remain visually distinct from regular Model Group cards.
7. The normal user path must not require creating a bundle before adding a model group to a Role.

## Requirement 9: Persistence must remain route-backed

**Goal:** As a maintainer, I need the restored UX to keep deterministic route execution in the backend.

### Acceptance Criteria

1. Role storage must persist exact `route_id` values for selected provider model options.
2. Role storage must preserve the Model Group layer so the UI can reconstruct model fallback order without guessing.
3. Studio Backend must materialize Model Groups into a flat ordered gateway `fallback_chain` before runtime resolution; the gateway resolver must continue consuming concrete route-chain roles.
4. Frontend code must not infer provider ownership from raw model strings.
5. Frontend code must not canonicalize model IDs for execution decisions; canonical grouping comes from backend DTOs.
6. Backend validation must reject Role entries referencing unknown route IDs.
7. Backend validation must reject or report Model Group entries whose selected provider model options no longer belong to that group, unless a migration or explicit repair path handles the mismatch.

## Requirement 10: Studio frontend guardrails apply

**Goal:** As a Studio maintainer, I want the updated LLM Roles page to follow the shared UI system and manual verification rules.

### Acceptance Criteria

1. Before implementation, workers must read `docs/development/FRONTEND_UI_SPEC.md`, especially section 2.
2. Interactions must use local `@/components/ui/*` wrappers where available.
3. Collapsible, modal, dropdown, select, tooltip, tabs, alert, and confirmation interactions must use local wrappers.
4. New visible UI must use semantic design tokens, not hardcoded hex values or one-off Tailwind palette colors.
5. Settings layout must preserve stable responsive widths and avoid horizontal overflow.
6. Before finishing user-visible frontend changes, workers must run the app and manually inspect Settings -> LLM Roles, including the main success path, obvious cancel/error states, and narrow width.
