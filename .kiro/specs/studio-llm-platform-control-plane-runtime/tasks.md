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

- [x] 6a. Reconcile platform branch with main cutover contracts
  - Remove stale Engine-owned LLM config/client public-contract entries and tests after Gateway ownership.
  - Keep `run_skill` model resolver injection explicit and preserve `mock_llm` override precedence.
  - Update contract docs, manifest fixtures, and hash locks with the approved Engine surface.
  - _Requirements: 1.1, 7.1, 7.4_

- [x] 6b. Restore provider notable-model suggestions without reintroducing runtime config
  - Keep deprecated provider test endpoints removed.
  - Restore `GET /api/llm/providers/notable-models` as suggestion-only placeholder data.
  - Parse provider-note §4 entries for Anthropic, Ark, DeepSeek, Gemini, OpenAI, OpenRouter, Qiniu, and Wavespeed.
  - _Requirements: 1.1, 1.4, 7.2_

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
  - _Requirements: 1.3, 5.2, 6.2, 8.2_

- [ ] 14a. Wire Copilot CredentialProvider execution path
  - Resolve `credential_ref` through the host CredentialProvider before Claude Agent SDK session creation.
  - Preserve inline `api_key` as a compatibility fallback until no-secret snapshots are the only persisted shape.
  - Make credential lookup failures route-scoped so Copilot can continue the Gateway fallback chain.
  - Key session reuse by non-secret credential fingerprint and SecretLifetimePolicy invalidation.
  - Cover credential-ref-only success, missing-secret fallback, fingerprint invalidation, and secret-free logs/events.
  - _Requirements: 2.5, 4.2, 7.1, 8.1, 8.3, 8.4, 8.5, 8.6_

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

## Phase 6: Draft Evidence Library And Route Testing Semantics

- [x] 19. Phase A - Define Requirement 9 schema and migration boundaries
  - Add Requirement 9 acceptance criteria for manual role order, Thinking preferred UI semantics, in-place official profile probes, durable draft evidence, provider-level list-only tests, single-model generation probes, shared trust tag colors, and typed capability groups.
  - Document draft evidence records: provider docs URL, model docs URL, model-list observations, candidate methods, candidate capabilities, modality/type metadata, probe attempts, successful probes, failed probes, deprecated/stale evidence, and agent notes.
  - Document trust states: `doc-discovered`, `provider-list-observed`, `draft-inferred`, `probe-verified`, `probe-failed`, `deprecated`, and `stale`.
  - Document that persisted `official_first` and `ready_first` migrate to `manual_order` without reordering existing `model_groups`, `provider_models`, or `fallback_chain`.
  - _Requirements: 9.1, 9.6, 9.7, 9.13_

- [x] 20. Phase B - Collapse provider ordering intent and save Thinking as preferred from Studio UI
  - Remove `official_first` and `ready_first` from backend `RoleIntent` and `ModelGroupIntent` literals while coercing old persisted values to `manual_order` during schema load.
  - Remove `official_first` and `ready_first` from frontend TypeScript role preference types and test fixtures.
  - Remove materializer provider sorting by provider kind or readiness so user-authored provider order is exact.
  - Change the LLM Roles `Field` + `Switch` Thinking control to display preferred semantics and save `thinking: "preferred"` when enabled.
  - Keep backend `thinking: "required"` behavior for admin/non-UI inputs and retain warning/downgrade behavior for preferred Thinking.
  - Run focused backend schema/materializer tests and focused frontend API/LLM Roles tests.
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 21. Phase C - Probe missing official VerifiedProfile during Role Test
  - Detect official provider routes in Role Test that have no matching `VerifiedProfile`.
  - Run the official profile probe for only that route/model and active credential.
  - On success, write `verified_profiles`, derived capabilities, and probe attempts to the active credential route and continue the same Role Test.
  - On failure, add the specific scoped failure reason to the role test route result without redirecting the user to API Keys.
  - Cover success and failure with backend router tests.
  - _Requirements: 9.4, 9.5, 9.10_

- [x] 22. Phase D - Add durable draft evidence schema and first write paths
  - Extend the import-draft storage model into a durable evidence library while preserving compatibility for existing draft files.
  - Add append-only evidence write helpers that never let new failed evidence overwrite older successful probe evidence.
  - Write `probe-verified` and `probe-failed` evidence from API Keys single-model tests.
  - Write `probe-verified` and `probe-failed` evidence from Role Test in-place official profile probes.
  - Cover evidence append behavior and compatibility load/dump with backend tests.
  - _Requirements: 9.6, 9.7, 9.10_

- [ ] 23. Phase E - Split provider-level connectivity/model-list tests from generation probes
  - Change provider-level Test/Get Models to verify endpoint/base URL/API key connectivity and fetch model lists where supported.
  - Compare model-list observations with draft evidence, record diffs, and hydrate draft-inferred route candidates.
  - Stop generation-probing all models from provider-level Test.
  - For providers without a model-list API, treat HTTP 200 as connectivity only and rely on draft evidence for suggestions.
  - Keep single-model Test as the only generation-probe path outside Role Test.
  - Cover model-list providers and no-list providers with backend tests.
  - _Requirements: 9.8, 9.9, 9.10_

- [ ] 24. Phase F - Align API Keys and LLM Roles route presentation with evidence trust
  - Use shared trust colors: green for active credential probe verified, blue for inferred/list/doc evidence without generation proof, and warning/destructive for failed or deprecated evidence.
  - Add `model_type` or `capability_family` metadata to route/model DTOs used by API Keys and LLM Roles.
  - Restrict LLM Roles language fallback candidates to routes with text input and text output modalities.
  - Render multimodal, embedding, audio, video, translation, 3D, moderation, and interactions-agent records in typed provider capability groups rather than the text fallback chain.
  - Follow `docs/development/FRONTEND_UI_SPEC.md`, use local `Tag`, `Tooltip`, `CatalogAccordion`, `Field`, and `Switch` wrappers where applicable, and manually verify changed API Keys and LLM Roles workflows in a browser or Tauri shell.
  - _Requirements: 6.3, 6.4, 9.11, 9.12, 9.13_
