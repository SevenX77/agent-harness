---
status: Draft
created: 2026-05-26
owner: Studio
related_requirements: .kiro/specs/studio-llm-roles-model-groups/requirements.md
---

# Studio LLM Roles Model Groups Design

## Overview

This design restores LLM Roles to the user-facing model/provider UX while preserving the new route-backed backend core. Users author Roles by dragging normalized Model Groups into Role cards, then adjusting provider fallback order inside each Model Group. The UI does not ask users to understand routes, endpoints, canonical IDs, or gateway fallback chains.

The backend still stores deterministic executable identities. A selected provider model option is saved by exact `route_id`. A Model Group is backed by backend canonical grouping metadata. Studio Backend materializes the authored Model Group structure into the gateway-compatible `RoleEntry.fallback_chain` format before runtime resolution. The gateway resolver remains a lower-level execution component; it does not understand or expand Studio product concepts such as Model Groups or Model Bundles.

## Design Principles

1. **UI language stays human:** show Models, Providers, Model Groups, Model Bundles, Fallback, Capability, and Test.
2. **Backend identity stays exact:** route IDs remain the execution identity and persistence reference.
3. **Right sidebar is normalized:** Available Models displays Model Group cards as the main list and may show visually distinct Pinned Model Bundle cards in a separate top slot. Singleton unknown models are still Model Groups.
4. **Role authoring is two-level:** Role -> Model Group fallback -> Provider fallback.
5. **Intent beats per-route knobs:** users set role/model-group intent; the system translates intent into provider-specific settings.
6. **Tests are explicit:** Capability Test discovers provider model facts; Role Test verifies full fallback behavior and reports warnings.
7. **Bundles are advanced:** Model Bundles provide reusable explicit configurations but are not required for normal role authoring.
8. **Gateway contract is not a UI contract:** `fallback_chain` is the gateway execution format. Studio may generate it, store a generated copy, or pass an in-memory generated snapshot, but the frontend authoring model is Model Groups.

## Execution Boundary

`fallback_chain` belongs to `graph_agent_gateway.registry.RoleEntry`. It is the ordered list of exact `route_id` entries that the gateway resolver can execute. It is not a user-facing concept and it should not shape the LLM Roles UI.

The runtime boundary is:

```text
Studio Frontend
  edits Role -> Model Groups -> Providers

Studio Backend
  validates selected provider model options
  resolves user intent against route capabilities
  materializes an ordered gateway fallback_chain

Graph Agent Gateway
  consumes RoleEntry.fallback_chain
  joins route_id -> ProviderRoute -> ProviderEndpoint
  lints runtime settings
  executes provider fallback and returns the LLM result
```

The gateway resolver should not be changed to understand `model_groups`. The correct integration point is a Studio backend materializer that produces the existing gateway shape:

```python
RoleEntry(
    system_prompt_prefix=...,
    fallback_chain=[
        RoleRouteEntry(route_id="anthropic-official:claude-opus-4-7", runtime_settings=...),
        RoleRouteEntry(route_id="onechats:claude-opus-4-7", runtime_settings=...),
    ],
)
```

For path-based runtime integration, Studio can write a generated gateway roles file that remains schema-compatible with the current gateway loader. For in-process integration, Studio can pass a generated `RegistrySnapshot` directly to `ModelResolver(registry_snapshot=...)`. In both cases, the generated gateway shape is derived from Studio authoring data; it is not edited directly by the user.

## Open Questions Resolved by this Revision

The following decisions are part of the executable design and must be reflected in schema, DTOs, tasks, and tests:

- `Available Models` uses Model Group cards as the main list. Valid Model Bundle cards may appear in a visually distinct `Pinned Model Bundles` slot above the Model Groups list.
- `ProviderEndpoint.provider_kind` is persisted as `"official" | "third_party" | "custom"`. A curated backend map seeds defaults for new endpoints only; user edits remain the source of truth.
- `ProviderEndpoint.rate_limit_bucket` is persisted as an optional string. If empty, the effective bucket is `endpoint_id`.
- Runtime circuit aggregation uses the explicit priority `Off > Needs Setup > Cooling Down > Ready/Untested`. If multiple circuits apply, `retry_at` is the farthest future retry time. The displayed reason uses the circuit with that farthest retry time, with message specificity ordered route scope, endpoint scope, then bucket scope when retry times tie.
- Disabling a provider endpoint projects all child provider model options to `Off`.
- Role entries include `role_kind: "graph_agent" | "copilot"` so UI sections do not rely on naming conventions.
- `POST /api/llm/roles/{role_name}/test` tests the persisted Role only. To test a draft, the frontend first saves it with `PUT /api/llm/roles/{role_name}` and then calls Role Test.
- `Test Now` for Cooling Down calls `POST /api/llm/routes/{route_id}/probe?force=true`.
- V2 migration of old `failed` route status without a clear hard setup reason converts to `unverified_manual` plus a `migration_warning`; it is not silently kept as a hard failure.
- Runtime health is durable app-local state, preferably SQLite or an equivalent local KV store. In-memory health stores are allowed only in tests.

## User-Facing Information Architecture

Settings -> LLM Roles contains one primary workspace:

```text
LLM Roles

Graph Agent Roles
  analyst
  planner
  reviewer

Copilot Roles
  copilot_chat

Advanced Model Bundles
  Claude Strict Thinking
  Budget DeepSeek Chain
```

The right side is `Available Models`:

Pinned Model Bundles are a secondary slot above Model Groups. They make explicitly configured bundles easy to reuse, but they do not change the main Model Group-first selection model.

```text
Available Models

Pinned Model Bundles
  Claude Strict Thinking

Model Groups
  Claude Sonnet 4.7
    3 providers · 2 Ready · 1 Cooling Down

  DeepSeek V4 Pro
    1 provider · Ready

  My Company Special Model
    1 provider · Untested
```

The visible UI labels providers, not endpoints:

```text
Claude Sonnet 4.7
Providers
  Anthropic Official
  OpenRouter
  Custom Proxy
```

The exact backend `route_id` can appear in debug tooltips or copied diagnostics, but it is not the primary label.

## Backend Data Model

### Existing Source Facts

`llm_credentials.json` remains the source for provider credentials and provider model options:

```json
{
  "schema_version": 4,
  "provider_endpoints": {
    "anthropic-official": {
      "endpoint_id": "anthropic-official",
      "display_name": "Anthropic Official",
      "provider_kind": "official",
      "protocol": "anthropic_compatible",
      "base_url": "https://api.anthropic.com",
      "rate_limit_bucket": "anthropic-official",
      "status": "verified"
    }
  },
  "provider_routes": {
    "anthropic-official:claude-sonnet-4-7": {
      "route_id": "anthropic-official:claude-sonnet-4-7",
      "endpoint_id": "anthropic-official",
      "route_slug": "claude-sonnet-4-7",
      "provider_model_id": "claude-sonnet-4-7",
      "canonical_id": "claude-sonnet-4-7",
      "display_name": "Claude Sonnet 4.7",
      "status": "unverified_manual",
      "capabilities": {}
    }
  }
}
```

### Studio Role Authoring Schema

Studio role authoring must preserve Model Group structure for UI round-tripping. This can be a new `llm_roles.yaml` schema version or a Studio-owned authoring file that is materialized into the existing gateway role schema. The important boundary is that the authored schema and the generated gateway schema are separate responsibilities.

```yaml
schema_version: 3
roles:
  analyst:
    role_kind: graph_agent
    system_prompt_prefix: ""
    model_fallback_enabled: true
    intent:
      provider_preference: official_first
      thinking: preferred
      target_context_tokens:
        mode: maximum_available
      target_output_tokens:
        mode: target
        value: 128000
        downgrade: allow_with_warning
      cost_priority: balanced
    model_groups:
      - canonical_id: claude-sonnet-4-7
        display_name: Claude Sonnet 4.7
        intent:
          thinking: inherit
          target_output_tokens:
            mode: inherit
        provider_models:
          - route_id: anthropic-official:claude-sonnet-4-7
          - route_id: openrouter-prod:anthropic.claude-sonnet-4-7
      - canonical_id: deepseek-v4-pro
        display_name: DeepSeek V4 Pro
        provider_models:
          - route_id: deepseek-official:deepseek-v4-pro
    lint_requirements:
      thinking: warn
  copilot_chat:
    role_kind: copilot
    system_prompt_prefix: ""
    model_fallback_enabled: true
    intent:
      provider_preference: official_first
    model_groups: []
```

Studio Backend materializes this into a gateway route execution plan:

```text
1. anthropic-official:claude-sonnet-4-7
2. openrouter-prod:anthropic.claude-sonnet-4-7
3. deepseek-official:deepseek-v4-pro
```

If `model_fallback_enabled` is `false`, the materializer includes only the provider fallback list from the first Model Group. Provider fallback inside that Model Group remains enabled. If `model_fallback_enabled` is `true`, the materializer appends provider fallback lists from all Model Groups in order.

This design deliberately keeps provider fallback always on. The role-level fallback switch controls only whether the system may fall through from one Model Group to the next.

### Compatibility With V2 Route Chains

Current V2 `RoleEntry.fallback_chain[*].route_id` is still valid as an internal execution representation, but it is insufficient for the restored UI because it loses the authored Model Group layer. Migration should convert flat route chains to model groups by grouping each route under its backend `canonical_id`, preserving order.

Migration example:

```yaml
fallback_chain:
  - route_id: anthropic-official:claude-sonnet-4-7
  - route_id: openrouter-prod:anthropic.claude-sonnet-4-7
```

becomes:

```yaml
model_groups:
  - canonical_id: claude-sonnet-4-7
    display_name: Claude Sonnet 4.7
    provider_models:
      - route_id: anthropic-official:claude-sonnet-4-7
      - route_id: openrouter-prod:anthropic.claude-sonnet-4-7
```

If adjacent routes have different canonical IDs, they become separate Model Groups in order. If identical canonical IDs are non-adjacent, migration should preserve user fallback order and create multiple blocks or use a stable conflict note rather than reordering silently.

### Model Profiles and Model Bundles

The existing gateway `ModelProfile` type should not be treated as a product requirement. It was introduced as an authoring-time reusable route bundle before the Studio app UX was finalized. It is close to the new `Advanced Model Bundles` concept, but the product model should be redesigned around Studio needs rather than inherited mechanically from gateway schema.

Decision:

- New UI label: `Advanced Model Bundles`.
- New Studio backend concept: `model_bundles` or `route_bundles`; prefer `model_bundles` in product-facing Studio APIs because the UI is model/provider-oriented.
- Gateway runtime input: generated role `fallback_chain` only.
- Existing `model_profiles`: migration/compatibility input only. Existing records can be converted into `model_bundles`, or the old API can be temporarily aliased, but new UI and new docs should not expose `model_profile`.
- Generated `RegistrySnapshot.model_profiles` may be empty unless another internal caller still needs it. Runtime must not resolve by bundle/profile ID.

This means a Model Bundle is not a gateway execution target. Applying or dragging a bundle into a Role copies or references the authored bundle in Studio state, then Studio Backend materializes the Role's final `fallback_chain` for gateway execution.

## Model Group DTOs

The registry API should return display-ready Model Groups so the frontend does not canonicalize or infer provider ownership.

```ts
interface ModelGroup {
  canonical_id: string
  display_name: string
  provider_models: ProviderModelOption[]
  status_summary: {
    ready: number
    untested: number
    cooling_down: number
    needs_setup: number
    off: number
  }
  capability_summary: {
    capability_known_count: number
    thinking: "supported" | "unsupported" | "mixed" | "unknown"
    tools: "supported" | "unsupported" | "mixed" | "unknown"
    structured_output: "supported" | "unsupported" | "mixed" | "unknown"
    max_context_tokens?: number | null
    max_output_tokens?: number | null
  }
}

interface ProviderModelOption {
  route_id: string
  provider_label: string
  provider_kind: "official" | "third_party" | "custom"
  provider_model_id: string
  ui_state: "ready" | "untested" | "cooling_down" | "needs_setup" | "off"
  ui_detail?: string | null
  retry_at?: string | null
  reason_code?: string | null
  capability_state: "unknown" | "callable_only" | "partial" | "known"
  capabilities: Record<string, CapabilityValue>
}
```

The backend derives these DTOs from route identity, endpoint configuration, capability facts, runtime health, and Model Group grouping rules. The frontend must not derive user-facing state from raw gateway `status`.

`capability_summary.* = "mixed"` means at least one provider model option differs from the common capability state for that Model Group. When no common state can be established because facts are missing, the summary remains `"unknown"`.

Singleton Model Groups use `provider_routes[*].canonical_id` when present. If a route has no canonical ID, the backend creates a singleton Model Group keyed by that route's `route_slug`; execution still uses the exact `route_id`.

## State Architecture

### Source Domains

The state model has three source domains. A single `status` enum must not be used as the source of truth for UI, testing, admission, and runtime health.

| Domain | Question | Owner | Volatility |
| --- | --- | --- | --- |
| Identity | Does this endpoint/route exist, is it user-enabled, and is its configuration hard-valid? | Studio registry/materializer | Low |
| Capability | What does this provider model support? | Capability Test/provider metadata/manual facts | Medium |
| Health | Can this provider model run right now, and is a circuit open? | Gateway runtime + Studio health store | High |

Role Fit is derived, not stored as global provider state. Studio materializer computes Role Fit from Role intent, Model Group intent, Identity, and Capability.

### Provider UI States

Provider rows expose only five top-level user states:

| UI state | Meaning | User action |
| --- | --- | --- |
| `Ready` | Can be used now. Capability may still have details in the tooltip, but the model is callable. | Use it. |
| `Untested` | Not verified yet, but can be tried. | Use or run Capability Test. |
| `Cooling Down` | Gateway has opened a runtime circuit and is temporarily skipping it. | Wait for countdown or click Test Now. |
| `Needs Setup` | Configuration is missing or invalid, such as missing key, invalid key, invalid model, invalid base URL, or invalid protocol. | Fix provider/model setup. |
| `Off` | User turned this provider model option or provider off. | Turn on. |

Backend reason codes such as `missing_key`, `invalid_key`, `invalid_model`, `invalid_base_url`, `rate_limited`, and `unsupported_parameter` are details. They may appear in tooltips, diagnostics, test reports, and logs, but not as top-level provider row states.

Live `RouteStatus.failed` projects to `Needs Setup` because it represents a hard identity/configuration block. Legacy migration of old ambiguous `failed` statuses still follows the v2 migration rule below: convert to `unverified_manual` plus `migration_warning` unless a clear hard setup reason exists.

Do not add `Recent Issue` as a top-level UI state. If an issue no longer affects the next user action, show it only in details. If it affects execution, the state is `Cooling Down`.

### Role Fit States

Inside a Role card, provider rows may also show one Role Fit label:

| Role Fit | Meaning |
| --- | --- |
| `Using` | This provider model option enters the generated fallback chain. |
| `Downgraded` | It enters the chain, but settings are reduced with a warning. |
| `Needs Test` | Required capability is unknown and needs Capability Test before the Role can safely use it. |
| `Not Fit` | It is proven incompatible with this Role's required intent. |

Role Fit never changes global provider health. For example, a provider model can be globally `Ready` and still be `Not Fit` for a Role that requires thinking.

### Gateway Admission

Gateway consumes concrete generated candidates and computes an admission decision:

```ts
type AdmissionDecision = "admit" | "temporary_skip" | "block"
```

Admission rules:

| Condition | Admission |
| --- | --- |
| user-disabled endpoint or route | `block` |
| missing credential | `block` |
| hard-invalid endpoint or route configuration | `block` |
| known-illegal runtime settings | `block` |
| circuit open and `retry_at` is in the future | `temporary_skip` |
| capability unknown | `admit` |
| never tested | `admit` |
| healthy or circuit expired | `admit` |

Provider fallback is always on. A candidate failure records a runtime event and falls through to the next candidate. Hard failures affect future admission, not the current chain's right to try the next provider.

The existing `RouteStatus` enum may remain during migration as a compatibility projection:

| Existing status | Compatibility meaning |
| --- | --- |
| `verified` | Callable success exists and no hard block. |
| `unverified_manual` | No callable success yet or verification is stale, but there is no hard block. |
| `failed` | Hard identity/configuration block. |
| `disabled` | User-enabled false. |

New Studio and gateway code should prefer Identity + Capability + Health projections over raw `RouteStatus` checks.

### Runtime Health and Circuit UX

Gateway emits structured runtime events instead of writing UI labels:

```ts
interface LlmRuntimeEvent {
  event_id: string
  occurred_at: string
  role_name: string
  route_id: string
  endpoint_id: string
  phase: "admission" | "probe" | "dispatch"
  outcome: "success" | "transient_failure" | "hard_failure" | "blocked" | "temporary_skipped"
  reason_code?: string | null
  provider_status_code?: number | null
  retry_at?: string | null
  message?: string | null
}
```

Studio projects runtime events into a Health Store. A circuit record contains scope, reason, `retry_at`, failure count, and optional message. Circuit scope may be route, provider endpoint, or rate-limit bucket. The UI derives `Cooling Down · retry in Ns` from `retry_at`.

When multiple state inputs apply to one provider model option, projection uses this explicit order:

| Priority | Input | Projected UI state |
| --- | --- | --- |
| 1 | user-disabled route or endpoint | `Off` |
| 2 | missing key, invalid key, invalid model, invalid base URL, invalid protocol, or equivalent hard setup issue | `Needs Setup` |
| 3 | active route, endpoint, or rate-limit-bucket circuit with future `retry_at` | `Cooling Down` |
| 4 | callable success exists | `Ready` |
| 5 | no callable success and no hard block | `Untested` |

Priorities 4 and 5 are sibling labels distinguished by whether a callable success exists; there is no strict ordering between them.

If multiple active circuits apply, the displayed countdown uses the farthest future `retry_at`. The displayed reason uses the circuit that produced that retry time; if retry times tie, prefer route-scope message, then endpoint-scope message, then rate-limit-bucket message.

`Test Now` runs a forced probe or Capability Test via `POST /api/llm/routes/{route_id}/probe?force=true`:

- success closes the circuit immediately and returns the provider row to `Ready` or `Untested`;
- transient failure opens or extends the circuit and refreshes the countdown;
- hard failure projects to `Needs Setup`.

Runtime health must not be written through the same autosave path as Role authoring.

## Default Provider Model Selection

When a user drops a Model Group into a Role, the frontend creates a Model Group entry with selected provider model options using backend DTO data.

Default algorithm:

1. Start with all provider model options in the group.
2. Exclude `Needs Setup` and `Off` options from default selection.
3. Exclude new `Cooling Down` options from default selection when alternatives exist; keep existing selected `Cooling Down` options in authoring so runtime admission can temporary-skip them.
4. If the UI filter `Official only` is active, keep only official providers.
5. Sort by `RoleIntent.provider_preference`. If unset or `official_first`, sort official providers first. If `ready_first`, sort by UI state with `Ready` before `Untested`. If `manual_order`, preserve the order returned by the registry.
6. Treat `Ready` and `Untested` as usable candidates. Do not push `Untested` options behind `Ready` options solely because capability is unknown unless `provider_preference` explicitly requests `ready_first`.
7. If no usable option remains, block the drop or create a clearly invalid Model Group card with `Needs Setup`; do not silently create an executable fallback.

## Intent and Runtime Setting Resolution

### Intent Schema

Role and Model Group settings store user intent, not raw provider payload fields:

```ts
interface RoleIntent {
  provider_preference?: "official_first" | "ready_first" | "manual_order"
  thinking?: "off" | "preferred" | "required"
  target_context_tokens?: TokenIntent
  target_output_tokens?: TokenIntent
  cost_priority?: "quality" | "balanced" | "low_cost"
}

interface TokenIntent {
  mode: "inherit" | "default" | "maximum_available" | "target" | "required_minimum"
  value?: number | null
  downgrade?: "allow" | "allow_with_warning" | "block"
}
```

Model Group intent inherits from Role intent by default. Model Group intent can override role settings for that group only.
`inherit` is valid only inside Model Group or provider-level override intent. Role-level intent must use a concrete mode such as `default`, `maximum_available`, `target`, or `required_minimum`.

`provider_preference: "manual_order"` means the user-controlled provider order is authoritative after the initial/default selection. The materializer must not reorder providers automatically for official-first or ready-first behavior once manual order is set.

### Materialization and Resolution

Studio backend materialization applies this order:

1. Provider model capability facts from `provider_routes[*].capabilities`.
2. Role-level intent.
3. Model Group-level intent override.
4. Advanced Model Bundle or provider-model override, when explicitly configured.

The materializer produces a concrete gateway call plan:

```json
{
  "role_name": "analyst",
  "entries": [
    {
      "canonical_id": "deepseek-v4-pro",
      "route_id": "deepseek-official:deepseek-v4-pro",
      "requested": {
        "target_output_tokens": 128000,
        "thinking": "preferred"
      },
      "resolved_settings": {
        "max_output_tokens": 65536
      },
      "warnings": [
        {
          "code": "token_downgraded",
          "message": "Requested 128k output, but DeepSeek V4 Pro supports 64k. Using 64k."
        },
        {
          "code": "thinking_not_enabled",
          "message": "Thinking was preferred but this provider model does not expose a known thinking capability."
        }
      ]
    }
  ]
}
```

Downgrades must be reported. Required settings that cannot be satisfied produce Role Fit `Needs Test` when capability is unknown, or `Not Fit` when the provider model is proven incompatible. This is Role-local and must not mark the provider model globally unavailable.

After materialization, gateway `resolve_role()` still performs its own deterministic validation and linting over the concrete route chain. That gateway lint is a runtime safety filter, not a frontend mapping mechanism. Studio may map lint results back to visible Model Group/provider rows for diagnostics, but lint exists to prevent unsupported or invalid runtime calls.

## Capability Descriptors

The backend must provide descriptors for dynamic UI fields. The frontend should render these descriptors instead of hardcoding provider-specific setting rules.

```ts
interface RuntimeSettingDescriptor {
  key: string
  label: string
  type: "boolean" | "integer" | "number" | "enum" | "string"
  available: boolean
  default?: unknown
  min?: number | null
  max?: number | null
  allowed_values?: string[]
  source: "probed_verified" | "provider_doc" | "agent_draft" | "manual" | "unknown"
  message?: string | null
}
```

Descriptor examples:

- `thinking.enabled` -> Switch.
- `thinking.budget_tokens` -> numeric input with min/max.
- `target_output_tokens` -> token intent control.
- `provider_preference` -> segmented control or select.

Unsupported fields are disabled with a visible reason. Unknown fields can show "Capability unknown" and suggest Capability Test.

## Test Design

### Capability Test

Capability Test answers: "What does this provider model option actually support?"

API target:

```text
POST /api/llm/routes/{route_id}/probe
```

The UI label should be `Capability Test` or `Test Capabilities`.

When called as `POST /api/llm/routes/{route_id}/probe?force=true`, the backend bypasses any active route circuit for that single test attempt. Success closes the route circuit in the same transaction as capability/callable-state update. Transient failure refreshes the circuit. Hard setup failure projects the provider model option to `Needs Setup`.

The backend stores results on `provider_routes[route_id].capabilities`. It should test or classify:

- callable status;
- provider model existence;
- max context tokens;
- max output tokens;
- thinking/reasoning support and parameter mapping;
- tools/function-calling support;
- structured output / JSON mode support;
- streaming support when relevant;
- stop sequence behavior;
- provider-specific error classification.

Capability Test must call the real provider when a capability cannot be established from trusted metadata. It should not use a `dry_run` mode as the primary capability mechanism; a dry run cannot prove model existence, credential validity, token limits, or thinking/tool behavior.

### Role Test

Role Test answers: "Does this Role's complete fallback plan work, and what will the system actually send?"

API target:

```text
POST /api/llm/roles/{role_name}/test
```

Role Test always reads the persisted Role. Draft testing is implemented by saving first with `PUT /api/llm/roles/{role_name}`, then calling this endpoint. The API must not accept a second ad hoc draft role shape that bypasses normal persistence and materialization.

Response shape:

```ts
interface RoleTestResponse {
  role_name: string
  status: "ok" | "warning" | "blocked" | "failed"
  model_groups: RoleTestModelGroupResult[]
  warnings: RoleTestWarning[]
}

interface RoleTestModelGroupResult {
  canonical_id: string
  display_name: string
  provider_results: RoleTestProviderResult[]
}

interface RoleTestProviderResult {
  route_id: string
  provider_label: string
  status: "ok" | "skipped" | "failed" | "blocked" | "untested"
  resolved_settings: Record<string, unknown>
  warnings: RoleTestWarning[]
  message?: string | null
}
```

Role Test may run Capability Tests for stale or unknown provider model options, but it must still report which part was capability discovery and which part was fallback execution.

Role Test should execute real calls using safe minimal prompts and token budgets. It should test configured fallback candidates instead of stopping after the first success when the user's goal is to verify the whole chain.

Concurrency is allowed across independent provider rate-limit buckets. The default bucket is the configured provider entry, because one entry usually represents one API key and base URL. If multiple provider entries share an API key or known quota pool, backend metadata can assign them the same `rate_limit_bucket`. Role Test and Capability Test may run different buckets in parallel, but calls in the same bucket should respect the configured concurrency limit.

Definitions:

- Provider entry: one configured credential/base URL/protocol boundary.
- API key bucket: the rate-limit/quota boundary, which may be shared by multiple provider entries.
- Provider family: display/vendor grouping such as Anthropic, OpenAI, Qiniu, or OpenRouter. It is useful for UI grouping but is not precise enough by itself for rate limiting.

## Advanced Model Bundles

Model Bundles are advanced reusable configurations. They appear below Roles in the main workspace, but valid/tested bundle cards are also pinned at the top of the right-side `Available Models` area so configured bundles are easy to use.

Storage:

```yaml
model_bundles:
  claude_strict_thinking:
    display_name: Claude Strict Thinking
    model_groups:
      - canonical_id: claude-sonnet-4-7
        provider_models:
          - route_id: anthropic-official:claude-sonnet-4-7
            runtime_overrides:
              thinking:
                mode: required
              target_output_tokens:
                mode: target
                value: 8192
```

Rules:

- Bundles are optional.
- Normal role authoring must not require creating a bundle.
- Bundles can be tested independently.
- Valid bundles must be available for use from the right-side `Available Models` area as `Pinned Model Bundles`.
- Bundle cards are visually distinct from Model Group cards.
- A bundle is still Studio authoring data. Dragging or applying it results in Role Model Group/provider selections, and Studio Backend materializes the final gateway `fallback_chain`.

## Frontend Component Changes

Target structure:

```text
settings/llm-roles/
  AvailableModelsSidebar.tsx
  ModelGroupCard.tsx
  ProviderModelList.tsx
  RoleCardList.tsx
  RoleCard.tsx
  RoleModelGroupCard.tsx
  RoleIntentDialog.tsx
  ModelGroupIntentDialog.tsx
  CapabilityBadges.tsx
  RoleTestReport.tsx
  AdvancedModelBundles.tsx
  useLazyRenderCount.ts
```

`role-utils.ts` should be rewritten around model group operations:

- `appendModelGroupToRole`
- `removeModelGroupFromRole`
- `reorderModelGroupInRole`
- `appendProviderModelToGroup`
- `removeProviderModelFromGroup`
- `reorderProviderModelInGroup`
- `updateRoleIntent`
- `updateModelGroupIntent`
- `validateRoleModelGroups`

It should not contain provider ownership inference or raw model string canonicalization.

## API Changes

Recommended additions:

```text
GET /api/llm/registry
  includes model_groups, route_runtime_settings, role_test summaries where cheap

GET /api/llm/model-groups
  optional focused endpoint for Available Models

PUT /api/llm/roles/{role_name}
  stores role model groups and intent

DELETE /api/llm/roles/{role_name}
  needed for existing role delete UX

POST /api/llm/roles/{role_name}/test
  runs role fallback test

POST /api/llm/routes/{route_id}/probe
  remains backend route API, UI labels as Capability Test

POST /api/llm/routes/{route_id}/probe?force=true
  Test Now for Cooling Down provider model option

GET /api/llm/model-bundles
PUT /api/llm/model-bundles/{bundle_id}
DELETE /api/llm/model-bundles/{bundle_id}
POST /api/llm/model-bundles/{bundle_id}/test
```

The existing `model_profiles` API is not the target product API. It may be migrated into `model_bundles`, kept as a temporary compatibility alias, or removed after migration. UI copy and new frontend code should use Model Bundle. Gateway runtime should receive generated role fallback chains, not profile/bundle IDs.

## Error Handling

- Unknown route ID in role storage: backend returns 400 with field path.
- Deleted provider model option still referenced: backend returns warning/repair metadata in registry; frontend shows a non-executable provider row.
- Required capability unavailable: Role Fit is `Needs Test` when unknown or `Not Fit` when proven unsupported; if no fallback satisfies the requirement, Role Test returns a blocked Role result.
- Downgrade allowed: Role Test returns `warning`, not silent success.
- Capability unknown: provider state remains `Ready` or `Untested` based on callable status; Role Fit may show `Needs Test` when the current Role requires the unknown capability.

## Verification Requirements

Backend:

- schema validation for model group role entries;
- migration from flat fallback chain to model groups;
- Studio backend materializer preserves order when generating gateway fallback chains;
- intent resolution downgrades with warnings;
- role test response includes resolved settings and warnings;
- unknown route IDs rejected.

Frontend:

- Available Models shows Model Group cards as the main list, with Pinned Model Bundles visually separated above them;
- singleton unknown provider model displays as same card format;
- dragging a Model Group adds a Role Model Group card;
- default provider selection follows official/filter/provider-state policy;
- role/model group reordering persists;
- UI contains no visible `route`, `endpoint`, or `canonical` primary labels;
- Role Test renders downgrade warnings.

Manual:

- run Studio/Tauri;
- open Settings -> LLM Roles;
- add role;
- set role intent;
- drag Model Group into role;
- reorder Model Groups and Providers;
- run Capability Test and Role Test;
- inspect downgrade warning;
- check Advanced Model Bundles area;
- verify narrow width.
