---
status: Implementing
created: 2026-05-30
owner: Studio + Engine
---

# Studio LLM Platform Control Plane / Runtime Plane Research

## Current Code Baseline

The merged platform branch already separates the Gateway package from Studio backend, but the v1.1 target is not yet complete:

| Area | Current finding | Migration implication |
|---|---|---|
| Gateway runtime schema | `ProviderEndpoint.api_key` and `ResolvedRoute.api_key` still carry secrets | Add `credential_ref` first, keep `api_key` as compatibility, then delete after runtime migration |
| Gateway resolver | `resolve_role()` rejects routes without inline `api_key` | Phase 1b can dual-write `credential_ref`; later phases can call CredentialProvider.describe |
| Gateway client manager | SDK clients are cached by `credential_fingerprint`; SDK `max_retries=0` | Add SecretLifetimePolicy and TerminalRetryPolicy contracts before changing retry behavior |
| Gateway classifier | Existing decision is `fallback_allowed` / `fail_fast` / `fail_fast_with_route_context` | Add action/scope model while preserving old adapter |
| Studio backend probe | `llm.py` and `copilot_test.py` build provider-specific payloads | Phase 2 moves provider primitives into Gateway |
| Studio job state | Endpoint and role test jobs are router-level in-memory dicts | Phase 1a extracts a job-store shell before behavior changes |
| Catalog knowledge | Legacy docs place catalog in Gateway or Studio | v1.1 assigns catalog to Control Plane/local registry, not Gateway runtime |

## Source Documents

- `temp/2026-05-30-llm-platform-control-plane-runtime-final-design.md` is v1.1 and the source of truth for this spec.
- `temp/2026-05-30-llm-platform-control-plane-runtime-final-design-audit-v1-r4.md` confirms R4 items were absorbed into v1.1.
- `apps/studio/backend/docs/llm-registry/LLM_REGISTRY_V2_STRATEGY.md` is superseded because it places catalog ownership ambiguously and predates credential references, terminal retry policy, and ClientSpec/terminal/probe adapters.

## Design Conclusions

1. The first implementation slice should be contract-first and compatible. Deleting `ResolvedRoute.api_key` before Gateway can call a CredentialProvider would break current Graph Agent and Copilot runtime.
2. `credential_ref` must not equal route identity. Existing endpoints can use a migration reference such as `endpoint:<endpoint_id>` until Studio owns explicit refs.
3. Retry and fallback must be modeled separately. The existing runtime can keep using the old `fallback_allowed` adapter until a terminal retry wrapper is wired.
4. Gateway can define ClientSpec, CredentialProvider, ExecutionTerminal, ReadinessProbe, SecretLifetimePolicy, TerminalRetryPolicy, and ErrorContext contracts without depending on Studio.
5. Studio backend extraction should follow the existing route registry boundaries: Control Plane owns jobs/probes/materialization; Gateway owns provider execution primitives.

## Implementation Slice Selected

This branch implements the v1.1 Phase 1 contract kernel:

- Kiro requirements, research, design, and tasks.
- Formal v1.1 backend design document and superseded banner on the old strategy.
- Gateway schema additions for credential references, credential descriptors, secret lifetime, terminal retry policy, and snapshot version metadata.
- Gateway resolver dual-write of `credential_ref` while preserving `api_key` compatibility.
- Gateway error action classifier with compatibility mapping to the old decision enum.

The later behavior-changing work remains in tasks: terminal retry wrapper, CredentialProvider runtime retrieval, Studio probe migration, generic terminal registry, Copilot SDK adapter, UI consumption of client-route profiles, and Control Plane package extraction.
