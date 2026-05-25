# Requirements: LLM Provider Intelligence V2 (Deterministic Resolver Edition)

## 1. Vision and Positioning

Studio is a local developer tool for deterministic LLM debugging, orchestration, and configuration. It is not a production gateway that dynamically chooses models from intent.

This feature fixes three problems as one architecture:

- The UI sees fragmented model names across providers and proxies.
- The backend lacks trustworthy model capability metadata.
- The engine execution path still depends on role/provider configuration that can drift away from Studio credentials.

The core rule is:

> Execution must always resolve to an explicit physical route. Capabilities may lint, warn, block invalid saves, and fail fast, but they must never cause the system to secretly select a different model.

No backward compatibility with the old short-code `models/providers/roles` shape is required for this prototype phase. The implementation may replace the existing LLM config schema if the new design is cleaner.

## 2. Terminology

- **ProviderEndpoint**: One callable API endpoint plus authentication and protocol, for example `anthropic-official` or `qiniu-openai`. A provider brand may have multiple endpoints.
- **ProviderRoute**: One physical model route on one endpoint. It contains the exact `provider_model_id` sent to the API.
- **route_id**: Stable route identity used by roles and logs. It identifies a `ProviderRoute`; it is not sent to LLM APIs.
- **canonical_id**: Display/grouping label for equivalent or intentionally grouped model routes. It is never an execution identifier.
- **RoleRouteChain**: Ordered fallback chain of explicit `route_id` entries for one role.
- **CapabilityValue**: A normalized capability value plus source and verification metadata.
- **ProviderImportDraft**: Sandboxed output from Agent-assisted onboarding before it can affect active execution config.
- **LintRequirement**: Static rule that compares a role's expectations with route capabilities.

## 3. Functional Requirements

### REQ-01: Shared LLM Registry Core

The schema, canonical mapping, role-route resolution, and capability linting must be implemented in a shared Python module consumed by both Graph Agent Engine and Studio Backend.

- The shared module must live under `packages/graph-agent/src/graph_agent/llm_registry/`.
- Studio Backend may import `graph_agent.llm_registry`.
- `graph_agent.llm_registry` must not import `apps/studio/backend`.
- Studio Frontend must not reimplement canonicalization or route resolution. It consumes backend API DTOs derived from the shared module.
- `packages/graph-agent/src/graph_agent/models/resolver.py` remains a runtime model factory and must not become the registry domain module.

### REQ-02: Deterministic Role Execution

Roles must reference ordered `route_id` chains, not model short codes plus provider short codes.

- A role's `fallback_chain` is an ordered array of route references.
- Resolver must try the chain in declared order.
- Resolver must not search for other routes by capability, provider, price, latency, or availability.
- Resolver must not replace one `canonical_id` with another.
- Capability requirements may block save or fail fast, but may not mutate the fallback chain.
- `model_override`-style runtime overrides must resolve to explicit `route_id` values or be rejected with a clear error.

### REQ-03: Credential and Endpoint SSoT

`llm_credentials.json` is the single source of truth for endpoint credentials and physical routes.

- Engine must be able to run from `llm_credentials.json` plus `llm_roles.yaml` without requiring API keys in `.env`.
- Provider API keys are stored on `ProviderEndpoint` records.
- API responses must redact secrets by default.
- Credential writes must remain atomic and protected by the existing file-lock/write-lock discipline.
- Runtime client cache keys must include endpoint identity and a credential fingerprint/version, so key/base URL changes do not reuse stale SDK clients.

### REQ-04: Route Identity Contract

`route_id` must be stable, explicit, and safe for YAML keys, URLs, React keys, logs, and file-like debug output.

- `endpoint_id` must match: `[a-z0-9][a-z0-9._-]*`
- `route_slug` must match: `[a-z0-9][a-z0-9._-]*`
- `route_id` format is: `<endpoint_id>:<route_slug>`
- `route_id` must match: `[a-z0-9][a-z0-9._-]*:[a-z0-9][a-z0-9._-]*`
- `provider_model_id` is stored as data and may contain `/`, `:`, uppercase, or vendor-specific syntax.
- The system must never parse `provider_model_id` back out of `route_id`.
- If two provider model IDs map to the same desired route slug under one endpoint, the backend must generate a deterministic suffix, for example `claude-sonnet-4.6-2`, and preserve the explicit `provider_model_id`.

### REQ-05: Provider Route Data Contract

Every active `ProviderRoute` must contain:

- `route_id`
- `endpoint_id`
- `provider_model_id`
- `canonical_id`
- `display_name`
- `status`
- `capabilities`

Route `status` must be one of:

- `verified`
- `unverified_manual`
- `disabled`
- `failed`

Only `verified` and `unverified_manual` routes may be referenced in role chains. `disabled` and `failed` routes remain visible for diagnosis but are not selectable.

### REQ-06: Explicit Canonicalization

Canonicalization must be conservative and explainable.

- `canonical_id` is a UI grouping label only.
- Safe transport normalization may strip known proxy prefixes when the provider behavior is understood.
- Complex equivalence requires an explicit alias rule.
- Routes without a matching rule must remain as independent orphan canonical groups.
- The mapper must keep positive and negative examples in tests.
- Rules must not merge `latest`, dated snapshots, `fast`, `thinking`, or provider-specific variants unless an explicit rule names that exact equivalence.

### REQ-07: Capability Sources and Lint Semantics

Every normalized capability value must carry a source.

Allowed `source` values:

- `api_list`
- `provider_doc`
- `agent_draft`
- `manual`
- `probed_verified`

Capability values must be represented as:

```json
{
  "value": 8192,
  "source": "probed_verified",
  "observed_at": "2026-05-24T00:00:00Z",
  "message": "Verified by max_output_tokens probe"
}
```

Only `value` and `source` are required. `observed_at` and `message` are optional.

Role `lint_requirements` use severities:

- `off`
- `warn`
- `error`

Lint behavior:

- `off`: no UI warning and no save/runtime effect.
- `warn`: visible warning but save and execution remain allowed.
- `error`: save must be blocked when the route is known incompatible; execution must fail fast if an invalid route reaches runtime.

### REQ-08: Lazy Capability Probing

Capability probing must run per route and only when useful.

- Backend may list models from provider APIs during endpoint testing.
- Strong capability probing must be triggered for selected `route_id` values, not by full-provider brute force.
- Strong probes include minimal calls for thinking, tool calling, structured output, and max output token bounds when those capabilities are requested by lint or surfaced in UI.
- Probe results must update the corresponding route capabilities with `source: probed_verified`.
- Probe errors must preserve diagnostic detail without deleting previous verified capabilities unless the route identity changed.

### REQ-09: Safe Agent-Assisted Onboarding

Agent analysis is untrusted until verified.

- Agent output must first become `ProviderImportDraft`.
- Draft data must not change active `provider_endpoints`, `provider_routes`, or role chains until applied.
- Backend must probe draft endpoints and draft routes before promotion.
- Verified endpoint fields and verified routes may be auto-promoted only when the draft was created for a new endpoint and no active endpoint would be overwritten.
- Unverified executable routes require explicit user confirmation and become `status: unverified_manual`.
- Unverified metadata may be saved only with `source: agent_draft` or `source: manual`.
- UI must show a diff between draft and active config before applying changes.

### REQ-10: Fallback Error Boundary

Runtime fallback must preserve developer predictability.

Fallback may continue to the next route for:

- network connection errors
- request timeouts
- retryable provider 5xx errors
- rate-limit errors when the adapter can classify them
- route temporarily marked down by the runtime health cache

Runtime must fail fast, without trying unrelated fallback routes, for:

- invalid API request shape
- unsupported capability requested by role or call parameters
- unknown model / invalid model ID
- missing credential
- invalid credential when all routes share the same endpoint credential
- schema/config validation failures

If classification is uncertain, the error must be surfaced with route context rather than silently treated as a model-selection signal.

### REQ-11: Studio Frontend Requirements

The frontend must follow `docs/development/FRONTEND_UI_SPEC.md` section 2.

- Use local shadcn/Radix wrappers from `apps/studio/frontend/src/components/ui/`.
- Available model/sidebar UI becomes an Available Routes UI grouped by `canonical_id`.
- Dragging from the sidebar into a role adds a `route_id` to the role's `fallback_chain`.
- Route cards must show endpoint label, provider model ID, canonical ID, verification status, and relevant capability badges.
- Capability lint warnings/errors must use local `Badge`, `Tooltip`, `Alert`, `Dialog`, and `Button` wrappers as appropriate.
- UI may show `canonical_id` groups, but must expose the physical `provider_model_id` for inspectability.
- Frontend must not synthesize backend route records from raw model strings.

### REQ-12: Observability and Debuggability

Every runtime LLM call and fallback event must include:

- role name
- route_id
- endpoint_id
- provider_model_id
- canonical_id
- provider protocol
- fallback decision and error class when fallback occurs

Logs and UI diagnostics must make it obvious which physical route was used.

### REQ-13: Verification Requirements

The implementation must include:

- Unit tests for route ID validation.
- Unit tests for canonical mapper positive and negative cases.
- Unit tests for role-route resolver ordering and no dynamic capability matching.
- Unit tests for capability linter severities.
- Backend API tests for import draft creation, probing, diff, and apply.
- Engine tests proving credentials file values flow into runtime calls without `.env`.
- Frontend tests for route grouping, lint state, and route drag/drop payloads.
- Manual frontend verification in browser or Tauri shell for touched UI flows, including narrow-width layout.
