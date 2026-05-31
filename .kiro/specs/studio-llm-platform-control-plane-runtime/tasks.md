---
status: Implementing
created: 2026-05-30
owner: Studio + Engine
related_requirements: .kiro/specs/studio-llm-platform-control-plane-runtime/requirements.md
---

# Studio LLM Platform Control Plane / Runtime Plane Tasks

## Phase 0: Governance And Baseline

- [x] 1. Capture v1.1 as the active Kiro implementation spec
  - Add requirements, research, design, and tasks documents for the platform branch.
  - _Requirements: 1.1, 7.1, 7.4_

- [x] 2. Promote the v1.1 design out of temp
  - Add the formal design under Studio backend LLM registry docs.
  - Add a superseded banner to the old LLM Registry V2 strategy.
  - _Requirements: 1.4, 7.3_

## Phase 1: Compatible Gateway Contract Kernel

- [x] 3. Add credential-reference contracts
  - Add non-secret credential descriptor and CredentialProvider protocol.
  - Add `credential_ref` to endpoint and resolved route schemas.
  - Preserve compatibility `api_key` with redacted serialization.
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [x] 4. Add secret lifetime and snapshot version contracts
  - Model secret-bearing client/session cache policy.
  - Model registry/catalog/client/terminal/probe/profile snapshot versions.
  - _Requirements: 2.4, 3.1, 3.2_

- [x] 5. Add deterministic terminal retry policy
  - Model standard runtime/probe and SDK runtime/probe retry defaults.
  - Keep runtime retry behavior disabled until wrapper wiring lands.
  - _Requirements: 4.1, 4.5, 7.1_

- [x] 6. Add error action classifier with compatibility adapter
  - Classify retry, fallback, and fail-request actions with explicit scopes.
  - Preserve old fallback/fail-fast decisions for current Gateway callers.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

## Phase 2: Studio Control Plane Extraction

- [ ] 7. Extract LLM test job state from the router
  - Introduce `LlmJobStore` for endpoint and role test jobs.
  - Keep the current in-memory behavior during extraction.
  - _Requirements: 1.1, 7.1_

- [ ] 8. Introduce Gateway probe client shell
  - Add a Studio-side interface that will call Gateway probe primitives.
  - Keep existing provider-specific probe behavior until Gateway primitives are ready.
  - _Requirements: 5.1, 5.4, 7.1_

## Phase 3: Runtime Behavior Migration

- [ ] 9. Wire Gateway standard terminal retry wrapper
  - Apply TerminalRetryPolicy when the feature flag is enabled.
  - Keep SDK provider `max_retries=0` and let Gateway wrapper own retry attempts.
  - _Requirements: 4.1, 4.5, 7.2_

- [ ] 10. Prefer CredentialProvider at execution time
  - Use `credential_ref` with host-provided `get(ref)` when available.
  - Keep inline `api_key` fallback until all consumers migrate.
  - _Requirements: 2.1, 2.5, 7.1_

- [ ] 11. Move provider probe primitives into Gateway
  - Expose minimal generation and capability contract probe primitives.
  - Return sanitized observations without secrets.
  - _Requirements: 5.1, 5.3, 5.4_

- [ ] 12. Remove Studio provider-specific probe construction
  - Replace `llm.py` and `copilot_test.py` provider payload/header construction with Gateway probe calls.
  - Preserve current API responses and UI behavior.
  - _Requirements: 5.1, 5.4, 7.2_

## Phase 4: Multi-Client Readiness

- [ ] 13. Add generic ClientSpec and terminal registry skeleton
  - Declare accepted method IDs, terminal versions, and probe contract versions.
  - Add ExecutionTerminalRegistry and ReadinessProbe interfaces.
  - _Requirements: 1.3, 3.2, 5.1_

- [ ] 14. Add Copilot SDK terminal and readiness adapter
  - Register Copilot's Claude Agent SDK terminal through the generic registry.
  - Probe with the same SDK terminal used at runtime.
  - _Requirements: 1.3, 5.2, 6.2_

- [ ] 15. Store client terminal configs and client route profiles
  - Keep runtime configuration separate from readiness evidence.
  - Invalidate readiness when client or terminal versions change.
  - _Requirements: 3.2, 3.3, 5.3_

- [ ] 16. Update Studio UI consumers after backend profiles exist
  - Make Copilot route selection consume SDK readiness.
  - Follow `FRONTEND_UI_SPEC.md` and manually verify changed UI workflows.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

## Phase 5: Package Extraction And Catalog Governance

- [ ] 17. Extract Control Plane into a reusable package
  - Move catalog, registry projections, probe orchestration, jobs, and materialization behind a package facade.
  - Keep Studio as the first host importing the SDK.
  - _Requirements: 1.1, 1.2, 1.4_

- [ ] 18. Add catalog-worthy promotion gate
  - Require schema validation, secret scrubbing, Gateway validation, probe evidence, and human diff approval.
  - _Requirements: 3.4, 5.4, 7.2_
