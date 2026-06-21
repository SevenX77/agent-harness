---
spec: studio-llm-remote-draft-catalog
status: Draft
date: 2026-06-20
---

# Tasks - Studio LLM Remote Draft Catalog

## Phase 0 - Contract Lock

- [x] 0.1 Confirm target stable route ID behavior with tests.
  - Add tests for route slug generation and stable endpoint ID derivation.
  - Acceptance: same official endpoint/model produces same route ID in two isolated stores.
  - Acceptance: same custom URL/protocol/model produces the same URL-derived stable `route_id` across isolated stores.
  - Acceptance: persisted custom route IDs never include random UUIDs.

- [x] 0.2 Define stable endpoint ID helper.
  - Add a gateway/backend helper for `stable_endpoint_id(protocol, canonical_base_url)` and `stable_route_id(endpoint, route)`.
  - Acceptance: ID is deterministic from canonical URL + protocol.
  - Acceptance: ID does not include API key, display name, random local endpoint ID, or local path.

- [ ] 0.3 Define public/private catalog policy.
  - Add sanitizer policy for public-safe URL-derived records.
  - Public target may include public custom/third-party URLs after sanitization.
  - Private URLs require private catalog target or hash-only policy.
  - Acceptance: random `custom-*` is never used as persisted or catalog identity after migration.

- [x] 0.4 Define hard migration scope.
  - Migration inputs:
    - `llm_credentials.json`
    - `llm_roles.yaml`
    - `llm_import_drafts.json`
    - `llm_role_test_results.json`
    - `llm_health.sqlite`
  - Migration rewrites endpoint IDs, route IDs, role fallback chains, model profiles, model bundles, evidence records, route candidates, probe results, and circuit scope IDs.
  - Acceptance: one migration report lists every old ID and new ID.
  - Acceptance: migration validation fails if any persisted reference still contains a random `custom-<uuid>` endpoint ID.

- [ ] 0.5 Correct docs before implementation.
  - Modify:
    - `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md`
    - `docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md`
    - `docs/development/FRONTEND_UI_SPEC.md`
  - Acceptance: docs agree that remote GitHub catalog is canonical shared draft/evidence source and local evidence is cache/private pending state.
  - Acceptance: docs say custom/third-party route IDs are derived from canonical URL + protocol, not random endpoint ID.
  - Acceptance: docs say no backwards-compatible old-ID matching is allowed after migration.
  - Acceptance: docs no longer claim real draft probe worker is landed until code proves it.
  - Current status: `FRONTEND_UI_SPEC.md` blue tag semantics are corrected; Studio workflow and gateway alignment docs still need sync.

## Phase 1 - Hard Local Data Migration

- [x] 1.1 Write failing tests for current local data migration.
  - Fixtures contain old `custom-<uuid>` endpoints, routes, roles, role test results, import drafts, and health circuits.
  - Acceptance: tests fail before migration implementation because old IDs remain.

- [x] 1.2 Implement stable ID derivation.
  - Use shared gateway `canonicalize_base_url`.
  - Derive endpoint ID from protocol + canonical Base URL.
  - Derive route ID from stable endpoint ID + route slug.
  - Acceptance: deterministic test vectors pass.

- [x] 1.3 Implement hard migration command/service.
  - Create backups before writing.
  - Rewrite every affected store in one migration transaction where possible.
  - Restore backups on validation failure.
  - Acceptance: old fixture migrates to stable IDs with all references valid.

- [ ] 1.4 Add startup guard.
  - If persisted LLM data still contains random custom endpoint IDs after migration should have run, return a clear migration-required error.
  - Do not silently use old IDs in projection/sync/share.
  - Acceptance: startup/registry tests reject old random IDs.

## Phase 2 - Remote Catalog Seed

- [x] 2.1 Create remote GitHub catalog repository and initialize `llm_import_drafts.json`.
  - Shape: top-level `drafts.studio-evidence-library`.
  - Start with an empty valid catalog or a sanitized official-provider seed.
  - Acceptance: raw GitHub URL returns HTTP 200.

- [x] 2.2 Add schema validation tests for generated seed payload.
  - Test path: backend GitHub catalog service tests.
  - Acceptance: generated `llm_import_drafts.json` validates as `ProviderImportDraft`.

- [ ] 2.3 Add a catalog lint script or test.
  - Checks:
    - no random `custom-*` endpoint IDs used as persisted or catalog identity;
    - URL-derived stable endpoint IDs / route IDs present for custom/third-party records;
    - no `api_key`;
    - no `authorization`;
    - no private base URL fields;
    - evidence IDs unique.
  - Acceptance: CI fails on unsafe catalog content.

## Phase 3 - Remote-First Sync

- [x] 3.0 Add GitHub catalog repository API.
  - Backend config:
    - `STUDIO_GITHUB_TOKEN`
    - `STUDIO_GITHUB_OWNER`
    - `STUDIO_LLM_CATALOG_REPO`
    - `STUDIO_LLM_CATALOG_BRANCH`
    - `STUDIO_LLM_CATALOG_PATH`
  - Add GitHub client that can `GET /user`, `GET /repos/{owner}/{repo}`, `POST /user/repos`, `GET/PUT /contents/{path}`.
  - Add `POST /api/llm/catalog/repository/ensure`.
  - Acceptance: service tests prove repo creation uses `POST /user/repos` with `private: false`.
  - Acceptance: service tests prove missing `llm_import_drafts.json` is created through Contents API with a valid seed.
  - Acceptance: router test returns raw URL and does not expose the token.

- [x] 3.1 Tighten `sync_remote_evidence_library`.
  - Public catalog reads use the raw GitHub URL and must not require `STUDIO_GITHUB_TOKEN`.
  - Treat HTTP 404 as sync error in API response.
  - Do not treat stale local cache as remote truth.
  - Record source metadata: source URL, fetched time, ETag/commit if available.
  - Acceptance: test 404 returns clear remote catalog failure instead of silent success.
  - Current status: public raw read, 404 error behavior, and sync source metadata are implemented.

- [x] 3.2 Make `/api/llm/catalog/sync` return source metadata.
  - Include counts, source URL, cache flag, and new record count.
  - Acceptance: router test asserts metadata fields.

- [ ] 3.3 Ensure clean-machine behavior.
  - Test with no local app-support `llm_import_drafts.json`.
  - Acceptance: successful remote sync materializes evidence library from GitHub payload.

## Phase 4 - Evidence Writeback and Sanitized Share

- [ ] 4.0 Add public URL safety classifier.
  - Classify endpoint URLs as `public_safe`, `private_or_internal`, `malformed`, or `review_required`.
  - Reject localhost, RFC1918, link-local, unique-local IPv6, bare internal hostnames, userinfo, query, and fragment.
  - Allow official providers through curated mapping.
  - Acceptance: unit tests cover public OpenAI/OpenRouter/WaveSpeed-style URLs and private/internal URLs.

- [ ] 4.1 Add public evidence sanitizer.
  - Input: local `EvidenceRecord` + route candidate map.
  - Output: publishable record or exclusion reason.
  - Acceptance: secrets, private base URLs, raw request/response bodies, and random `custom-*` identities are excluded.
  - Acceptance: public custom/third-party records use URL-derived stable route IDs.
  - Acceptance: exclusion reason codes include `random_legacy_route_id`, `private_base_url`, `malformed_base_url`, `review_required_url`, `secret_like_value`, `raw_request_body`, `raw_response_body`, `missing_route_context`, `evidence_id_conflict`, and `unsupported_evidence_type`.

- [ ] 4.2 Replace unsafe `/api/llm/catalog/share` behavior.
  - Return sanitized publish preview.
  - Include counts and exclusion reasons.
  - Include PR-ready catalog patch or merged JSON payload.
  - Acceptance: existing custom endpoint evidence is not returned under random local identity.
  - Acceptance: existing custom endpoint evidence is publishable only after migration/normalization to URL-derived stable route ID and allowed by public/private URL policy.

- [ ] 4.3 Include required route candidates in share output.
  - If a publishable evidence references a route, include the corresponding sanitized `RouteCandidate`.
  - Route candidates must use URL-derived stable route IDs.
  - Acceptance: exported catalog can be validated and synced on a clean machine.

- [ ] 4.4 Add deterministic merge/dedupe.
  - Deduplicate by `evidence_id`.
  - Exclude conflicting same-id records with `evidence_id_conflict`.
  - Sort route candidates and evidence records deterministically.
  - Acceptance: applying the same writeback preview twice produces the same catalog.

- [ ] 4.5 Add GitHub draft PR writeback endpoint.
  - Add `POST /api/llm/catalog/writeback/preview`.
  - Add `POST /api/llm/catalog/writeback/pr`.
  - Create branch `studio-catalog/<timestamp>-<short-hash>`.
  - Open draft PR; never push directly to `main`.
  - Acceptance: tests prove token is used only for branch/commit/PR writes, not public reads.

## Phase 5 - Real Draft Probe Worker

- [ ] 5.1 Write failing tests for current `probe_import_draft` stub.
  - Test that probing a draft writes `probe_results`.
  - Test that success appends `probe-verified` evidence.
  - Test that failure appends `probe-failed` evidence.
  - Acceptance: tests fail against current stub.

- [ ] 5.2 Implement real draft probe worker.
  - Iterate selected route candidates.
  - Reuse existing endpoint/route probe machinery.
  - Append success and failure evidence.
  - Write evidence under the stable route ID only.
  - Keep active credentials conservative: no direct `verified` promotion from untrusted draft.
  - Acceptance: Phase 5.1 tests pass.

- [ ] 5.3 Add transient failure handling.
  - Temporary errors open cooling-down circuit when applicable.
  - Hard failures write failed evidence.
  - Acceptance: tests cover transient and hard failure distinction.

## Phase 6 - Unified 6-State UI Consumption

- [x] 6.0 Add General setting for automatic remote catalog reads.
  - Add backend `AppSettings.remote_model_catalog_enabled: bool = true`.
  - Add frontend `AppSettings.remote_model_catalog_enabled`.
  - Add Settings General `Remote Model Catalog` switch using local `Switch`.
  - Add i18n copy in English and Simplified Chinese.
  - Acceptance: GET `/api/settings` defaults the field to `true`.
  - Acceptance: PUT `/api/settings` persists `false`.
  - Acceptance: `useAppSettings` equality treats the flag as save-worthy.
  - Acceptance: General tab renders an on-by-default switch and calls `setRemoteModelCatalogEnabled(false)` when toggled off.

- [x] 6.0.1 Wire the setting to automatic sync.
  - Add frontend API wrapper for `POST /api/llm/catalog/sync`.
  - Settings load triggers one background sync only when `remote_model_catalog_enabled` is `true`.
  - Turning the setting off prevents automatic sync on later Settings opens.
  - Acceptance: frontend test proves disabled setting does not call sync.
  - Acceptance: frontend test proves enabled setting calls sync without hydrating secrets.

- [ ] 6.1 Change API Keys route chip rendering to use `ui_state`.
  - Remove old `status=probe-verified` as a UI truth path.
  - Acceptance: `historical_ready` route renders blue in API Keys without old status.
  - Acceptance: provider-list-only candidate renders neutral even when present in remote catalog.

- [ ] 6.2 Align compact endpoint test response with 6-state vocabulary.
  - Add `ui_state` to compact model info or map compact results through backend projection before frontend render.
  - Acceptance: frontend no longer needs `status=probe-verified` to show blue.

- [x] 6.2.1 Add catalog source metadata to registry response.
  - Include enabled/source URL/fetched_at/counts/last_error.
  - Acceptance: manual/API tests can tell whether Settings read remote catalog or only local cache.

- [ ] 6.3 Update frontend tests.
  - API Keys ProviderCard tests must assert route tag color from `ui_state`.
  - LLM Roles existing `historical_ready` tests remain valid.
  - Acceptance: targeted frontend tests pass.

## Phase 7 - End-to-End Verification

- [ ] 7.1 Backend focused tests.
  - Run gateway import draft tests.
  - Run backend LLM registry/router tests for catalog sync/share/projection.
  - Acceptance: all targeted tests pass.

- [ ] 7.2 Frontend focused tests.
  - Run ProviderCard and AvailableModels tests.
  - Acceptance: all targeted tests pass.

- [ ] 7.3 Manual Studio verification.
  - Start one Tauri dev session.
  - Open Settings -> API Keys.
  - Sync catalog.
  - Test an official provider endpoint.
  - Confirm:
    - green means current verified;
    - blue means historical probe verified;
    - provider-list-only candidates are not labeled Previously Connected.

- [ ] 7.4 Remote verification after merge.
  - Confirm GitHub raw catalog URL returns HTTP 200.
  - Confirm clean local cache sync works.
  - Confirm current local credentials/draft data have been rewritten to stable IDs.
  - Confirm no code path reads old random custom IDs for business logic.
  - Confirm no public catalog lint violations.
