---
status: Implementing
created: 2026-05-30
owner: Studio + Engine
source_design: apps/studio/backend/docs/llm-registry/LLM_PLATFORM_CONTROL_PLANE_RUNTIME_V1.md
---

# Studio LLM Platform Control Plane / Runtime Plane Requirements

## Introduction

This spec turns the v1.1 LLM Platform direction into an implementation contract. The platform splits LLM configuration intelligence into a reusable Control Plane SDK and runtime execution into the Gateway Runtime Plane SDK, while Studio remains the first host rather than the only host.

The first implementation slice must be compatible with the current Studio and Gateway runtime. It establishes the contracts for credential references, secret lifetime, terminal retry policy, and structured error action classification without deleting the existing `api_key` compatibility path.

## Requirements

### Requirement 1: SDK Boundary And One-Way Dependencies

**Objective:** As a platform maintainer, I want Control Plane and Gateway responsibilities to be explicit SDK boundaries, so that Studio, Graph Agent, Copilot, and future clients can reuse the same mechanism without reverse dependencies.

#### Acceptance Criteria

1. When a host imports the LLM platform, the system shall expose Control Plane responsibilities as configuration/catalog/probe/job/materialization concerns and Gateway responsibilities as execution/fallback/runtime-health concerns.
2. When Gateway executes a request, the system shall not depend on Studio backend or Control Plane internals except through declared callback protocols.
3. If a future client integrates with the platform, then the system shall require a ClientSpec and terminal/probe adapters rather than a separate provider-routing stack.
4. The system shall describe the public shape as SDK facade or library facade, not as an HTTP service process.

### Requirement 2: Credential References And Secret Lifetime

**Objective:** As a Studio host, I want snapshots to carry credential references instead of raw API keys, so that cached config, logs, and events never persist secrets.

#### Acceptance Criteria

1. When a route is resolved for runtime, the system shall include a `credential_ref` that is distinct from the route identity.
2. When a compatibility route still contains `api_key`, the system shall keep it redacted in JSON responses and model dumps.
3. When a route has only `credential_ref`, the system shall validate it as a future no-secret snapshot candidate.
4. When a runtime object caches SDK clients or sessions, the system shall describe its allowed secret lifetime and invalidation triggers.
5. The system shall provide a CredentialProvider contract with `describe(ref)` for non-secret readiness checks and `get(ref)` for execution-time secret retrieval.

### Requirement 3: Versioned Snapshot And Registry Contracts

**Objective:** As a runtime caller, I want the materialized snapshot to be versioned, so that readiness and route selection can be invalidated when client, terminal, catalog, or registry contracts change.

#### Acceptance Criteria

1. When Control Plane materializes a snapshot, the system shall be able to carry registry, catalog, client, terminal, probe-contract, profile, and generation timestamps.
2. If a ClientSpec version changes, then the system shall treat related readiness evidence as stale until it is re-probed.
3. Where local registry state stores both config and evidence, the system shall keep terminal configuration separate from client-route readiness profiles.
4. The system shall keep catalog knowledge in Control Plane or local registry ownership, not in Gateway runtime schema.

### Requirement 4: Terminal Retry And Error Action Semantics

**Objective:** As a Gateway runtime maintainer, I want retry, fallback, and fail-request decisions to be distinct, so that transient provider failures do not look like invalid app requests.

#### Acceptance Criteria

1. When a provider returns transient network, 5xx, 529, or temporary 429 errors, the system shall classify them as `retry_same_route` before route fallback is considered.
2. When credential, billing, permission, or missing-model errors affect only one endpoint or route, the system shall classify them as `fallback_route` with an explicit scope.
3. When malformed app input or an unsupported request cannot be fixed by another route, the system shall classify it as `fail_request`.
4. The system shall retain a compatibility adapter for existing `fallback_allowed` and `fail_fast` runtime callers until the Gateway loop is migrated.
5. The system shall make TerminalRetryPolicy deterministic, including standard runtime/probe and SDK runtime/probe defaults.

### Requirement 5: Test Path Equals Runtime Path

**Objective:** As a Studio user, I want readiness tests to exercise the same terminal used at runtime, so that a green settings page predicts a successful real run.

#### Acceptance Criteria

1. When a route is tested for Graph Agent, the system shall use Gateway standard terminal probe primitives rather than Studio-specific provider payload construction.
2. When a route is tested for Copilot, the system shall use the Copilot SDK terminal/probe adapter rather than provider API availability alone.
3. If a role requires capability contracts such as thinking, tools, structured output, or vision, then the system shall record capability readiness separately from availability readiness.
4. The system shall store sanitized observations and evidence references without secrets.

### Requirement 6: Studio UI And Backend Consumption

**Objective:** As a Studio operator, I want API Keys, LLM Roles, and Copilot settings to share the same registry source, so that the product does not maintain duplicate LLM configuration paths.

#### Acceptance Criteria

1. When Studio renders LLM Roles or Copilot configuration, the system shall derive route candidates from the same local registry and role materialization output.
2. When Copilot filters models, the system shall apply ClientSpec accepted methods and SDK readiness, not a second credentials store.
3. Where Studio frontend changes are required, the system shall follow `docs/development/FRONTEND_UI_SPEC.md` and use local design-system wrappers.
4. The system shall verify changed Studio UI paths manually in a browser or Tauri shell before completion.

### Requirement 7: Phased Migration And Compatibility Gates

**Objective:** As a reviewer, I want the platform migration to land in safe phases, so that the large branch can merge without silently changing every LLM runtime behavior at once.

#### Acceptance Criteria

1. When Phase 1 starts, the system shall add structural contracts and compatibility fields before deleting legacy fields.
2. If a phase changes runtime behavior, then the system shall document the behavior gate and test coverage in the Kiro tasks.
3. When a legacy document is superseded by v1.1, the system shall include a visible superseded banner in that legacy document.
4. The system shall keep future work traceable through Kiro tasks with requirement IDs.
