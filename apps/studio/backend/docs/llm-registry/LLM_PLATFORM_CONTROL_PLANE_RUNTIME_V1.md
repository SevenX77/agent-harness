# LLM Platform Control Plane / Runtime Plane v1.1

Date: 2026-05-30
Status: v1.1 implementation direction. This document promotes the temp design into the tracked Studio backend docs and is the source of truth for the current platform branch.

Supersedes:

- `apps/studio/backend/docs/llm-registry/LLM_REGISTRY_V2_STRATEGY.md`
- `temp/studio-llm-global-structure-and-code-review-analysis-2026-05-30.md`
- `temp/2026-05-29-copilot-roles-unified-ui-architecture.md`

## North Star

1. Split LLM platform responsibilities into Control Plane and Gateway Runtime Plane, while presenting one SDK facade to clients.
2. Studio is the first host, not the only host. Control Plane and Gateway must both be reusable libraries.
3. Shared abstractions come first. A new client contributes a ClientSpec plus terminal/probe adapters, not a separate provider-routing implementation.
4. Dependencies are one-way. Gateway does not import Studio or Control Plane internals; the only host callback is CredentialProvider.
5. API keys are persisted only by the host app. Snapshots, logs, events, and diagnostics must not contain secrets.
6. Catalog and provider knowledge belong to Control Plane/local registry, not Gateway runtime code.
7. Test path equals runtime path.

If implementation evidence contradicts a North Star item, record an explicit ADR before changing direction.

## Architecture

The platform is a pair of SDK libraries:

- Control Plane: catalog, knowledge, registry authoring, role/route materialization, probe orchestration, job state, import drafts, and view DTOs.
- Gateway Runtime Plane: provider execution, terminal dispatch, request mapping, retry/fallback/circuit semantics, runtime health semantics, probe primitives, and sanitized runtime observations.

Studio imports both libraries in-process. There is no service process in this design.

```text
Configuration path: App/client -> Control Plane -> versioned snapshot
Runtime path:      App/client -> Gateway with snapshot
Credential path:   Gateway -> CredentialProvider callback -> App secret store
```

Gateway never persists product state. Runtime health persistence, credential lookup, and client-specific terminals are injected by the host or integration package.

## Roles

| Role | Owns | Must not own |
|---|---|---|
| App host | UI, login/session, API key storage, app routes, CredentialProvider implementation | Provider protocol knowledge or fallback implementation |
| Control Plane SDK | Catalog, local registry, evidence, role materialization, jobs, probe orchestration, client profiles | Real provider execution |
| Gateway SDK | Provider calls, terminals, retry/fallback/circuit, runtime health semantics, probe primitives | Catalog, UI DTOs, app-specific storage |
| Client | ClientSpec, terminal/probe adapters when needed | Separate provider-routing stack |

## Public Contracts

### ClientSpec

Declares `client_id`, `client_version`, `terminal_id`, `terminal_version`, `probe_contract_version`, `accepted_method_ids`, and required capabilities. Version changes invalidate matching readiness evidence.

### CredentialProvider

The host implements two calls:

- `describe(ref) -> CredentialDescriptor`: returns non-secret availability data such as existence, status, fingerprint, scope, and update timestamp.
- `get(ref) -> secret`: returns the secret only at execution time.

The materialized snapshot carries `credential_ref`, not the secret. Existing inline `api_key` fields are migration compatibility only.

### ExecutionTerminal

Gateway defines the execution interface and dispatches terminals. Standard provider terminals live in Gateway. Client-specific terminals, such as Copilot's Claude Agent SDK terminal, are implemented by the client integration and registered into Gateway.

### ReadinessProbe

Readiness probes reuse the same terminal used at runtime. Provider API readiness and SDK readiness are separate, and each can include availability readiness plus capability contract readiness.

## Snapshot Versioning

Materialized snapshots must be able to record:

- `registry_version`
- `catalog_version`
- `client_id`
- `client_version`
- `terminal_version`
- `probe_contract_version`
- `client_route_profile_version`
- `generated_at`

This allows a runtime caller to reject stale snapshots and allows Control Plane to invalidate readiness when client or terminal contracts change.

## Credential And Secret Lifetime

Hard constraints:

- Snapshots/logs/events never include secrets.
- Gateway may briefly hold a secret during execution.
- Cached standard clients or SDK sessions may hold secrets only under SecretLifetimePolicy.
- Secret-bearing caches must be keyed by credential fingerprint and invalidated on credential rotation, logout, workspace switch, endpoint deletion, or explicit host request.
- Diagnostics must not stringify env, client, session, or secret-bearing objects.

The migration path is:

1. Add `credential_ref` while keeping `api_key` compatibility.
2. Prefer CredentialProvider for execution.
3. Deprecate and hide `ResolvedRoute.api_key`.
4. Delete inline route secrets after consumers migrate.

## Catalog, Registry, And Readiness

Catalog belongs to Control Plane. Gateway must not store public provider knowledge or UI catalog state.

| Data | Owner | Stored in | Version key |
|---|---|---|---|
| `client_terminal_configs` | Control Plane | Local registry | `config_hash` |
| `client_route_profiles` | Control Plane probe runner | Local registry | `profile_version`, `config_hash` |
| terminal adapter manifest | Client integration package | Integration layer | adapter version |

Fact precedence is:

`manual_override > local_probed_verified > catalog.probed_verified > catalog.provider_doc > catalog.api_list > protocol_default`.

## Retry, Fallback, And Error Classification

Retry is terminal-local. Fallback is Gateway-level.

TerminalRetryPolicy defaults:

```yaml
standard_runtime:
  max_attempts: 2
  backoff_ms: [250]
  retryable_status_codes: [429, 500, 502, 503, 504, 529]
standard_probe:
  max_attempts: 1
sdk_runtime:
  claude_code_max_retries: 2
sdk_probe:
  claude_code_max_retries: 1
```

Error actions:

| Action | Meaning |
|---|---|
| `retry_same_route` | Terminal should retry the same route before Gateway fallback |
| `fallback_route` | Gateway should mark the route/endpoint/bucket/credential scope and try another route |
| `fail_request` | The request is invalid or cannot be fixed by another route |

Classification requires ErrorContext: route, endpoint, credential ref, method, mapper, runtime settings, role requirements, provider error type/message, status code, and stream phase.

## Implementation Phases

| Phase | Outcome |
|---|---|
| 0 | SDK spike for Claude Agent SDK env, retry, base URL/model override, and error shapes |
| 1a | Extract service shells, job store, probe runner shell, GatewayProbeClient shell |
| 1a-r | Add standard terminal retry wrapper behind a default-off feature flag |
| 1a-r2 | Enable standard runtime retry after telemetry and tests |
| 1b | Add `credential_ref`, dual-write with `api_key` compatibility |
| 1c | Prefer CredentialProvider execution-time lookup |
| 1d | Deprecate and then delete `ResolvedRoute.api_key` |
| 1e | Migrate error classification to action/scope model |
| 2a | Add Gateway provider probe primitives |
| 2b | Remove Studio provider-specific probe construction |
| 2c | Add minimal Knowledge Lake observation loop |
| 2d | Add catalog-worthy promotion path |
| 3a | Add generic ClientSpec, ExecutionTerminalRegistry, ReadinessProbe skeleton |
| 3b | Add Copilot SDK terminal/probe adapter |
| 3c | Make UI/runtime consume `client_route_profiles` |
| 4 | Extract `packages/llm-control-plane` |
| 5 | Add Provider Intelligence draft and promotion gate |

The current branch implements the Phase 1 contract kernel first. Behavior-changing phases remain gated by tests and task completion.

## Decisions

| ID | Decision |
|---|---|
| D1 | Catalog belongs to Control Plane, not Gateway |
| D2 | Secrets move through CredentialProvider callbacks, not snapshots |
| D3 | Retry belongs to terminals; fallback belongs to Gateway |
| D4 | A client is ClientSpec plus adapters |
| D5 | SDK-specific verification knowledge belongs to the client/integration |
| D6 | Copilot registers SDK terminal/probe; Gateway does not import Copilot backend |
| D7 | Probe path must equal runtime path |
| D8 | Errors classify into action plus scope |
| D9 | Client-specific terminals are injected through a registry |
| D10 | `api_key` to `credential_ref` migrates in phases |
| D11 | Config and readiness evidence are separate structures |
| D12 | ClientSpec versions invalidate readiness |
| D13 | SDK libraries, not service processes |
| D14 | Snapshots carry version stamps |
| D15 | Graph Agent accepts only standard terminal method IDs |
| D16 | Provider Intelligence draft promotion requires validation, secret scrubbing, Gateway validation, probe evidence, and human diff approval |
| D17 | North Star changes require explicit ADR |
