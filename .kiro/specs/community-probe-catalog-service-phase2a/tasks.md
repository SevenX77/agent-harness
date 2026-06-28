---
spec: community-probe-catalog-service-phase2a
status: Implemented
date: 2026-06-26
linked_specs:
  - studio-llm-remote-draft-catalog
linked_docs:
  - docs/development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md
  - docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md
---

# Tasks — Community Probe Catalog Service (Phase 2a)

> **Status: implemented, TDD-first.** The in-repo desktop client (Phases 0–5)
> ships in `apps/studio/backend/app/services/community_catalog*.py` + the
> `/catalog/contribute` and `/catalog/sync-verified` endpoints; the server side
> (Phase 6) ships as a self-contained Node/Cloudflare scaffold in
> `services/community-catalog-gate/` (its own `node --test`, deliberately outside
> the Python CI). Dormant by default — MVP1 local-first behavior is unchanged
> until a gate/manifest is configured. See "Implementation notes & deviations".

## Phase 0: Governance & Baseline
- [x] 0.1 Locked design (this spec + design doc Phase 2a) is the contract; scope
  held to R1–R8.
- [x] 0.2 `protocol_major` + signing public key + gate URL/token added as injected
  config (`BackendConfig.community_*`); absent ⇒ dormant.
  Test: `test_community_catalog_*` dormant paths + `test_community_catalog_boundary`.

## Phase 1: Redaction + allowlist drop (R2) — pure, highest red-line value
- [x] 1.1 forbidden-field stripping → `test_forbidden_fields_never_reach_upload_payload`.
- [x] 1.2 non-allowlisted host ⇒ no base URL/hash; allowlisted ⇒ normalized URL +
  fingerprint; no bare un-salted hash → `test_community_catalog_redaction.py`.
- [x] 1.3 `EvidenceUpload` allowlist model + `build_upload_record` +
  `normalize_base_url` in `community_catalog.py`.
- [x] 1.4 `is_uploadable` enforces `probe` + `probe-verified`; `provider-list-observed`
  never eligible.

## Phase 2: Schema mapping (R5)
- [x] 2.1 `probe_result` ↔ `probe` round-trip + community-provenance ingest →
  `test_community_catalog_schema_mapping.py`.
- [x] 2.2 Mapping implemented at the **studio boundary** (`community_catalog.py`:
  `to_/from_wire_evidence_type`, `parse_catalog_evidence`) — gateway
  `registry/schema.py` left untouched (KEEP-MAIN); the wire-only `probe_result`
  name never enters the gateway. (Deviation from original wording — see notes.)

## Phase 3: Opt-in upload client (R1, R3, R6)
- [x] 3.1 opt-in only; idempotency key dedups; ack + `receipt_token`; offline queue
  retains on failure → `test_community_catalog_upload.py`.
- [x] 3.2 ingestion-scoped token only — `CommunityUploadClient` takes a gate URL +
  ingestion token; no code path hands it a GitHub repo token.
- [x] 3.3 upload client against `POST /v1/evidence/batches` + dormant
  `/catalog/contribute` endpoint (`test_community_catalog_contribute.py`).
- [~] 3.4 `receipt_token` is returned by the endpoint; **local persistence + the
  withdraw UI are a frontend follow-up** (withdraw call itself is gate-side, R6).

## Phase 4: Verified manifest/shard sync (R4) — read-path migration
- [~] 4.1 ETag short-circuit at the **manifest** level (skip whole sync when the
  manifest ETag is unchanged); per-shard differential download is a follow-up.
- [x] 4.2 signature/digest verify **fail-closed**; the disposable cache is left
  untouched on any failure → `test_sync_fails_closed_on_*`.
- [x] 4.3 incompatible `manifest.protocol_major` ⇒ `ProtocolVersionRefused`, no
  crash, nothing written → `test_sync_refuses_incompatible_protocol_*`.
- [x] 4.4 disposable cache isolated from the evidence store
  (`community_catalog_cache_path() != probe_catalog_path()`); legacy `/catalog/sync`
  untouched.
- [x] 4.5 verified sync + disposable cache + `/catalog/sync-verified` endpoint;
  served via a configurable manifest URL (Pages/CDN per README).

## Phase 5: Boundary regression guards (R8)
- [x] 5.1 `/catalog/share` still `local_export_only` / `auto_upload_enabled=false`
  even when the gate is configured → `test_community_catalog_boundary.py`.
- [x] 5.2 `/catalog/repository/ensure` unchanged; not the community upload path.
- [x] 5.3 Backend ruff + mypy + suite green before PR (see PR notes).

## Phase 6: External infra (`services/community-catalog-gate/` — NOT this repo's CI)
- [x] 6.1 Serverless gate (`src/gate.mjs`): `POST /v1/evidence/batches`, anonymous
  ingestion token, idempotency, server-side redaction re-validation
  (`src/redaction.mjs`), KV buffer, `receipt_token`, withdraw endpoint.
  **No GitHub repo token.**
- [x] 6.2 KV drain (`publish/drain-kv.mjs`) + publishing aggregator
  (`publish/aggregate.mjs`): shard, digest, **Ed25519-sign**; Action
  (`publish/publish-catalog.yml`) commits with minimal `permissions: contents: write`.
- [x] 6.3 Manifest + shards published to a CDN/Pages URL (documented in README).
- [~] 6.4 Service tests: redaction re-validation + sign/verify contract green
  (`node --test`, incl. cross-language Node-sign → Python-verify proof);
  rate-limit / abuse-sim tests are a follow-up.

## Implementation notes & deviations
- **Gateway untouched (KEEP-MAIN).** The whole client lives in the studio backend;
  `probe_result` is a wire-only name mapped at the studio boundary. No edit to
  `packages/graph-agent*`.
- **`cryptography` promoted to a direct backend dependency** (was transitive) for
  Ed25519 manifest verification; `uv.lock` refreshed (version unchanged, 49.0.0).
- **E2E-found integration fix:** a full real-code run (client redact → gate
  screen → publish + sign → client verified sync over HTTP) caught that published
  records carried no `evidence_id` (clients never upload one, by privacy design),
  so the client's `parse_catalog_evidence` rejected every record. Root cause was
  in the publisher: it now derives a stable content-addressed id
  (`aggregate.deriveEvidenceId`, covered by a Node test). The signature +
  shard-digest chain was confirmed to verify end to end.
- **Open follow-ups (frontend / refinement, not blocking the red-lines):**
  receipt-token persistence + withdraw UI (3.4); per-shard ETag differential (4.1);
  gate rate-limit + abuse-sim tests (6.4).

## Exit Criteria
- [x] R1–R8 behavior implemented + tested in this repo (Phases 0–5).
- [x] External-infra scaffold (Phase 6) implemented + tested in
  `services/community-catalog-gate/` with the red-lines held (gate holds no repo
  token; Action least-privilege; no un-salted hash published; signature fail-closed).
- [x] MVP1 local-first behavior unchanged when no gate/artifacts configured.
