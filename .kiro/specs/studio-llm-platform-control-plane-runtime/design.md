---
status: Implementing
created: 2026-05-30
owner: Studio + Engine
related_requirements: .kiro/specs/studio-llm-platform-control-plane-runtime/requirements.md
source_design: apps/studio/backend/docs/llm-registry/LLM_PLATFORM_CONTROL_PLANE_RUNTIME_V1.md
---

# Studio LLM Platform Control Plane / Runtime Plane Design

## Overview

This design implements the v1.1 LLM Platform direction as a phased SDK architecture. Studio remains the first host, but the reusable platform boundary is Control Plane for configuration intelligence and Gateway Runtime Plane for execution governance.

The current branch starts with a compatibility kernel. It introduces the data contracts needed for secret-free snapshots and richer runtime decisions while preserving the current `api_key` execution path until CredentialProvider runtime retrieval is wired.

### Goals

- Establish the Control Plane / Gateway boundary as SDK facades.
- Move snapshots toward `credential_ref` and versioned contracts without breaking current runtime.
- Model retry, fallback, and fail-request as separate decisions.
- Keep v1.1 implementation traceable through Kiro tasks.

### Non-Goals

- Do not turn Control Plane or Gateway into service processes.
- Do not delete `ResolvedRoute.api_key` in the first compatibility slice.
- Do not move Studio provider-specific probe code to Gateway until Gateway probe primitives are implemented.
- Do not add or redesign Studio frontend UI in this slice.

## Architecture

### Boundary Map

```mermaid
flowchart LR
  Studio["Studio host\nUI, API keys, sessions"] --> CP["Control Plane SDK\ncatalog, registry, probes, jobs, materialization"]
  Studio --> GA["Graph Agent client"]
  Studio --> CO["Copilot client"]
  CP --> GW["Gateway Runtime Plane SDK\nexecution, retry, fallback, runtime health"]
  GA --> GW
  CO --> GW
  GW --> Cred["CredentialProvider\nimplemented by host"]
  GW --> Term["ExecutionTerminalRegistry\nstandard + client adapters"]
```

Gateway never imports Studio or Control Plane internals. The only host callback is CredentialProvider.

### Technology Stack

| Layer | Choice | Role |
|---|---|---|
| Gateway SDK | `packages/graph-agent-gateway` Python package | Runtime schema, resolver, terminal contracts, error classification |
| Studio backend | FastAPI app | First host and current Control Plane location |
| Studio frontend | React/Tauri | Consumer of Control Plane projections; unchanged in this slice |
| Storage | Studio local registry JSON/SQLite | Current credential, route, health, and job state until extraction |

## System Flows

### Compatibility Runtime Flow

```mermaid
sequenceDiagram
  participant Client as Graph Agent/Copilot
  participant GW as Gateway
  participant Route as ResolvedRoute
  participant Provider as Provider SDK

  Client->>GW: call with resolved snapshot
  GW->>Route: read credential_ref and compatibility api_key
  GW->>Provider: execute with api_key
  Provider-->>GW: response or error
  GW->>GW: classify into action/scope, adapt to legacy decision
  GW-->>Client: result or fallback failure
```

### Target Credential Flow

```mermaid
sequenceDiagram
  participant CP as Control Plane
  participant Host as Studio CredentialProvider
  participant GW as Gateway
  participant Terminal as ExecutionTerminal

  CP->>Host: describe(credential_ref)
  Host-->>CP: descriptor without secret
  CP-->>GW: snapshot with credential_ref
  GW->>Host: get(credential_ref)
  Host-->>GW: secret for this call/session
  GW->>Terminal: execute(route, secret, request)
```

## Requirements Traceability

| Requirement | Summary | Components |
|---|---|---|
| 1.1-1.4 | SDK boundary and one-way dependencies | Formal design doc, Gateway contract models |
| 2.1-2.5 | Credential references and secret lifetime | `ProviderEndpoint.credential_ref`, `ResolvedRoute.credential_ref`, CredentialProvider contract, SecretLifetimePolicy |
| 3.1-3.4 | Versioned snapshot and config/evidence split | SnapshotVersion contract, Kiro phase tasks |
| 4.1-4.5 | Retry and error action semantics | TerminalRetryPolicy, ErrorContext, ErrorActionClassification |
| 5.1-5.4 | Test path equals runtime path | Phase 2/3 tasks |
| 6.1-6.4 | Studio backend/frontend consumption | Phase 3/UI tasks |
| 7.1-7.4 | Phased migration | Kiro tasks, legacy doc banner |

## Components And Interfaces

| Component | Domain | Intent | Requirements |
|---|---|---|---|
| CredentialProvider contract | Gateway public contract | Non-secret describe + execution-time get | 2 |
| SecretLifetimePolicy | Gateway runtime schema | Defines allowed secret-bearing cache lifetime and invalidation triggers | 2 |
| SnapshotVersion | Gateway/Control Plane schema | Records versions used by a materialized snapshot | 3 |
| TerminalRetryPolicy | Gateway runtime schema | Deterministic retry defaults by terminal/mode | 4 |
| ErrorContext classifier | Gateway runtime | Classifies provider/runtime errors into action + scope | 4 |
| Kiro spec | Planning/governance | Tracks complete v1.1 implementation phases | 7 |

### Gateway Contracts

Gateway owns provider execution contracts, but not product catalog state. The first slice adds schemas and compatibility behavior:

- `ProviderEndpoint.credential_ref` and `ResolvedRoute.credential_ref`.
- `ResolvedRoute.api_key` remains optional compatibility data and must stay redacted.
- `CredentialDescriptor` represents readiness without a secret.
- `CredentialProviderProtocol` declares host-provided secret lookup.
- `SecretLifetimePolicy` describes cache lifetime and invalidation semantics.
- `TerminalRetryPolicy` carries standard runtime/probe and SDK runtime/probe defaults.
- `ErrorContext` provides the data needed for route, endpoint, credential ref, method, mapper, runtime settings, role requirements, provider error type/message, status code, and stream phase.

### Studio Control Plane Shell

Studio backend currently hosts Control Plane behavior. Future tasks extract router job state and probe orchestration into services before package extraction.

## Data Models

| Model | Key Fields | Notes |
|---|---|---|
| `CredentialDescriptor` | `ref`, `exists`, `status`, `fingerprint`, `scope`, `updated_at` | No secret fields |
| `SnapshotVersion` | `registry_version`, `catalog_version`, `client_id`, `client_version`, `terminal_version`, `probe_contract_version`, `client_route_profile_version`, `generated_at` | Supports stale snapshot/readiness detection |
| `TerminalRetryPolicy` | `standard_runtime`, `standard_probe`, `sdk_runtime`, `sdk_probe` | `max_attempts` includes the initial attempt |
| `ErrorActionClassification` | `action`, `scope`, `status_code`, `retryable`, `fallback_eligible` | New model; old decision adapter remains |

## Error Handling

Gateway classifies errors in two layers:

- New action model: `retry_same_route`, `fallback_route`, `fail_request`.
- Compatibility model: `fallback_allowed`, `fail_fast`, `fail_fast_with_route_context`.

The first implementation keeps Gateway callers on the compatibility adapter. Transient errors and route/credential scoped failures adapt to `fallback_allowed`; malformed request failures adapt to `fail_fast`.

## Testing Strategy

- Gateway schema tests cover credential refs, no-secret snapshots, secret redaction, terminal retry defaults, and snapshot version validation.
- Gateway resolver tests cover migration-generated and explicit `credential_ref`.
- Gateway classifier tests cover 529 retry, 402/404 fallback, 413 fail request, and old adapter compatibility.
- Full Gateway test suite remains the required verification for this slice.
