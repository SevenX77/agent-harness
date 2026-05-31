# Requirements: LLM Provider Intelligence V2 (Deterministic Resolver Edition)

## 1. Vision and Positioning

Studio is a local developer tool for deterministic LLM debugging, orchestration, and configuration. It is not a production gateway that dynamically chooses models from intent.

This feature fixes three problems as one architecture:

- The UI sees fragmented model names across providers and proxies.
- The backend lacks trustworthy model capability metadata.
- The engine execution path still depends on role/provider configuration that can drift away from Studio credentials.

The core rule is:

> Execution must always resolve to an explicit physical route. Capabilities may lint, warn, block invalid saves, and fail fast, but they must never cause the system to secretly select a different model.

Backward compatibility with the old short-code `models/providers/roles` shape is explicitly not supported for this prototype phase. The implementation must hard-cut to the new endpoint/route registry and route-chain role schema. Old runtime readers, compatibility DTOs, and compatibility wrappers are out of scope.

## 2. Terminology

- **ProviderEndpoint**: One callable API endpoint plus authentication and protocol, for example `anthropic-official` or `qiniu-openai`. A provider brand may have multiple endpoints.
- **ProviderRoute**: One physical model route on one endpoint. It contains the exact `provider_model_id` sent to the API.
- **route_id**: Stable route identity used by roles and logs. It identifies a `ProviderRoute`; it is not sent to LLM APIs.
- **canonical_id**: Display/grouping label for equivalent or intentionally grouped model routes. It is never an execution identifier.
- **ModelProfile**: Reusable authoring-time route bundle, for example `CLO47T = Claude Opus 4.7 Thinking across selected providers`. It is not a runtime execution identifier.
- **RoleRouteChain**: Ordered fallback chain of explicit `route_id` entries for one role.
- **CapabilityValue**: A normalized capability value plus source and verification metadata.
- **RuntimeSettings**: User-authored request parameters on a role/profile route entry, for example temperature, max output tokens, tool choice, structured output, and reasoning settings.
- **EffectiveRuntimeSettings**: Resolver-produced runtime parameters after applying defaults and capability validation. Gateway adapters use this shape to build provider-specific requests.
- **ProviderImportDraft**: Sandboxed output from Agent-assisted onboarding before it can affect active execution config.
- **LintRequirement**: Static rule that compares a role's expectations with route capabilities.
- **RuntimePolicy**: Explicit runtime health/probing policy for gateway-owned provider clients. It is loaded into the registry snapshot and is not inferred from legacy role circuit-breaker fields.
- **ProviderProtocolAdapter**: Gateway-owned adapter that maps normalized routes and effective runtime settings to one concrete provider SDK/API surface, for example OpenAI-compatible, Anthropic-compatible, Google GenAI, or Volcengine Ark runtime SDK.

## 3. Functional Requirements

### REQ-01: Shared LLM Registry Core

The schema, canonical mapping, role-route resolution, and capability linting must be implemented in the standalone gateway package consumed by both Graph Agent Engine and Studio Backend.

- The shared module must live under `packages/graph-agent-gateway/src/graph_agent_gateway/registry/`.
- Studio Backend may import `graph_agent_gateway.registry` and the public `graph_agent_gateway` resolver APIs.
- `graph_agent_gateway.registry` must not import `apps/studio/backend`.
- `graph_agent_gateway.registry` must not import `graph_agent` runtime modules.
- Studio Frontend must not reimplement canonicalization or route resolution. It consumes backend API DTOs derived from the shared module.
- `graph_agent_gateway.resolver.ModelResolver` remains the runtime adapter that turns resolved route chains into `GatewayChatModel` instances; the registry subpackage owns the domain schema and pure resolution/linting logic.
- `packages/graph-agent/src/graph_agent/models/llm_client_manager.py` must be moved into the gateway package and removed from the Engine production path before credentials-file execution is considered complete. The old Engine-owned client-manager mode must be deleted from production imports.

### REQ-02: Deterministic Role Execution

Roles must reference ordered `route_id` chains, not model short codes plus provider short codes.

- A role's `fallback_chain` is an ordered array of route references.
- Resolver must try the chain in declared order.
- Resolver must not search for other routes by capability, provider, price, latency, or availability.
- Resolver must not replace one `canonical_id` with another.
- Capability requirements may block save or fail fast, but may not mutate the fallback chain.
- `model_override`-style runtime overrides must resolve to explicit `route_id` values or be rejected with a clear error.

### REQ-02A: Model Profiles as Authoring Abstraction

Backend may provide reusable model profile records for Studio editing workflows, but runtime execution must still use explicit route chains.

- A `ModelProfile` groups one ordered `fallback_chain` of explicit `route_id` entries under a stable `model_profile_id`, for example `CLO47T`.
- `model_profile_id` must be a safe slug matching `[A-Za-z0-9][A-Za-z0-9._-]*`.
- A profile may carry display metadata such as `display_name`, `canonical_id`, capability expectations, and tags.
- A profile may carry normalized route-level `runtime_settings` defaults such as `temperature`, `max_output_tokens`, and `reasoning.budget_tokens`.
- Profiles are authoring-time templates only. The runtime resolver must not dynamically resolve a role through `model_profile_id`.
- Adding a profile to a role must snapshot or expand the profile into the role's explicit `fallback_chain`.
- A role may keep `source_profile_id` and profile snapshot metadata for UI traceability, but runtime behavior is determined only by the saved `fallback_chain`.
- Updating or deleting a profile must not mutate existing role fallback chains unless the user explicitly reapplies the profile.
- Backend must validate and lint profile route chains using the same route and capability rules used for roles.
- Frontend must not construct profile fallback chains from raw provider model strings; it must use backend DTOs containing route IDs.

### REQ-03: Credential and Endpoint SSoT

`<studio_config_dir>/llm/llm_credentials.json` is the single source of truth for endpoint credentials and physical routes. `<studio_config_dir>/llm/llm_roles.yaml` is the active local source for model profiles and role fallback chains. `studio_config_dir` is resolved by `apps/studio/backend/app/core/paths.app_settings_dir`, with `STUDIO_CONFIG_DIR` as the explicit override. Repository `config/` files are examples, seeds, or package defaults only; production runtime must not hard-code repo-root `config/` as the active user configuration directory.

- Engine must be able to run from `llm_credentials.json` plus `llm_roles.yaml` without requiring API keys in `.env`.
- Studio Backend must resolve active credentials from `STUDIO_LLM_CREDENTIALS_PATH` or default to `<studio_config_dir>/llm/llm_credentials.json`.
- Studio Backend must resolve active roles from `STUDIO_LLM_ROLES_PATH` or default to `<studio_config_dir>/llm/llm_roles.yaml`.
- Checked-in role examples may live under `docs/development/examples/`, but active runtime writes must target the user-local Studio config directory.
- Runtime resolver construction must use an explicit registry snapshot or explicit credentials/roles paths. It must not silently fall back to built-in model defaults, old role files, or environment API keys.
- Provider API keys are stored on `ProviderEndpoint` records.
- API responses must redact secrets by default.
- Credential writes must be atomic and protected by a single write-lock discipline.
- Runtime client cache keys must include endpoint identity and a credential fingerprint/version, so key/base URL changes do not reuse stale SDK clients.
- Runtime health knobs must come from an explicit `RuntimePolicy` record in the registry snapshot or from documented defaults. Removed legacy `circuit_breaker` fields must not be parsed as runtime policy.
- Deleting endpoints, routes, or model profiles must be explicit API actions. If active role/profile references would be broken, backend must return a conflict with references instead of silently rewriting fallback chains.

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

Route metadata may be edited only without changing physical identity. `route_id`, `endpoint_id`, and `provider_model_id` are immutable for an existing route; changing them requires creating a new route and deleting the old route.

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

Supported lint keys must map explicitly to normalized capability keys. The implementation must not compare arbitrary lint strings against arbitrary provider metadata.

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

### REQ-08A: Runtime Settings Defaults and Capability-Gated Validation

Runtime settings must use a fixed normalized schema. Provider/model capabilities control which fields are shown, validated, warned about, or omitted from provider requests; they must not create arbitrary runtime setting keys.

- Role/profile route entries may set normalized runtime fields such as `temperature`, `top_p`, `max_output_tokens`, `stop_sequences`, `seed`, `tool_choice`, `parallel_tool_calls`, `structured_output`, and `reasoning`.
- `reasoning` must support provider-neutral fields for `enabled`, `effort`, and `budget_tokens`; adapters map these to provider-specific request shapes.
- A missing user setting must resolve through documented defaults instead of being passed as an ambiguous null.
- Default resolution order is: explicit route entry, model profile default, route capability default, protocol default, Studio safe default.
- Capabilities describe support, limits, defaults, and evidence source. Runtime settings describe user intent. The resolver must not conflate the two.
- Gateway must emit effective runtime settings with per-field source metadata in diagnostics/tracing so users can see whether a value came from a route entry, profile, probed provider default, protocol default, or Studio safe default.
- Unsupported or out-of-range runtime settings must fail validation or fail fast with route context; they must not trigger dynamic model replacement.
- UI may dynamically show or disable controls based on capability metadata, but backend and gateway must still validate the normalized schema.

### REQ-09: Safe Agent-Assisted Onboarding

Agent analysis is untrusted until verified.

- Agent output must first become `ProviderImportDraft`.
- Provider import drafts must be stored outside active credentials and active roles.
- Draft data must not change active `provider_endpoints`, `provider_routes`, or role chains until applied.
- A single import draft may contain multiple endpoint candidates when one provider document exposes multiple protocols or base URLs.
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
- Roles UI includes Model Profile cards for reusable authoring-time route bundles.
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

Role-level `system_prompt_prefix` must be resolved by the gateway-owned role resolution path, not by direct Engine reads of `llm_roles.yaml`.

### REQ-13: Verification Requirements

The implementation must include:

- Unit tests for route ID validation.
- Unit tests for canonical mapper positive and negative cases.
- Unit tests for role-route resolver ordering and no dynamic capability matching.
- Unit tests for capability linter severities.
- Unit tests for lint key to capability key mapping.
- Unit tests for `RuntimePolicy` defaults, validation ranges, and runtime propagation.
- Unit tests for `RuntimeSettings` defaults, effective setting source metadata, out-of-range validation, and unsupported-setting fail-fast behavior.
- Backend API tests for import draft creation, probing, diff, and apply.
- Backend API tests for import draft expiration and concurrent apply conflicts.
- Backend API tests for endpoint, route, and model profile delete reference conflicts.
- Engine tests proving credentials file values flow into runtime calls without `.env`.
- Gateway tests for fallback/fail-fast error classification.
- Frontend tests for route grouping, lint state, and route drag/drop payloads.
- Frontend tests proving route/model grouping comes from backend DTOs rather than raw model-string canonicalization.
- Manual frontend verification in browser or Tauri shell for touched UI flows, including narrow-width layout.

### REQ-14: Provider Protocol Matrix Verification

Provider-specific behavior must be recorded per `route_id`, not only per `canonical_id`, because the same model can expose different capabilities through official SDKs, OpenAI-compatible endpoints, and aggregators.

- The verification matrix must include at least one official Anthropic route, one OpenAI-compatible route, one Google GenAI route when credentials are available, one DeepSeek/OpenAI-compatible route when credentials are available, and one Volcengine Ark route.
- Volcengine Ark must be tested through its official Ark runtime SDK protocol in addition to the existing OpenAI-compatible path when local credentials are available.
- Tests must compare SDK vs OpenAI-compatible behavior for the same Ark endpoint/model where feasible.
- Tests must include positive probes and negative boundary probes for runtime settings that have provider-specific lower bounds, such as reasoning/thinking budget tokens and max output token limits.
- Results from provider documentation, model-list APIs, manual entries, and live probes must be stored with source metadata and must not be collapsed across providers unless an explicit route-level rule says they are equivalent.
