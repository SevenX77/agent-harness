---
spec: community-probe-catalog-service-phase2a
status: Draft
date: 2026-06-26
linked_specs:
  - studio-llm-remote-draft-catalog
linked_docs:
  - docs/development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md
  - docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md
---

# Design — Community Probe Catalog Service (Phase 2a)

## Overview

Phase 2a realizes the community catalog on free tiers while preserving every
Non-Goal. Three runtime pieces, one of which is in this repo:

1. **Serverless gate** (external infra) — `POST /v1/evidence/batches`; auth,
   rate-limit, redaction re-validation, enqueue. **Holds no repo-write token.**
2. **Scheduled publishing Action** (external infra) — drains the queue, aggregates,
   signs, and commits read-only shards + `manifest.json`. **Only repo writer.**
3. **Desktop / Studio client** (this repo) — opt-in redacted upload to the gate;
   verified manifest/shard sync into a disposable cache; schema mapping; boundary
   preservation.

```
 client (this repo)        external infra
 ┌───────────────┐  POST   ┌──────────┐   enqueue   ┌──────────┐
 │ redact + drop │ ──────▶ │  gate    │ ─────────▶  │  KV /    │
 │ opt-in upload │ /v1/... │ (no repo │             │  queue   │
 └───────────────┘  token  │  token)  │             └────┬─────┘
        ▲                   └──────────┘                  │ cron drain
        │ verified sync                                   ▼
 ┌──────┴────────┐  Pages   ┌──────────────┐  commit  ┌───────────────┐
 │ disposable    │ ◀─────── │ GitHub Pages │ ◀─────── │ publishing    │
 │ cache (≠ evid │  CDN     │  (artifacts) │ contents │ Action (only  │
 │  store)       │  ETag    └──────────────┘  :write  │ repo writer)  │
 └───────────────┘                                    └───────────────┘
```

## Architecture

### In-repo components (Studio backend + gateway SDK)
- **Redaction + allowlist filter** — extends the existing share/redaction path so
  the *upload* payload is built by the same forbidden-field stripper, plus the
  public-host allowlist drop (R2). Lives next to
  `apps/studio/backend/app/services/llm_probe_catalog.py` /
  `llm_import_drafts.py`; pure function, fully unit-testable.
- **Upload client** — a thin client to `POST /v1/evidence/batches` with an
  ingestion-scoped token, idempotency key, local ack + `receipt_token` store, and
  an offline queue. Gate base URL + token are injected config (absent by default →
  feature dormant, R8.2).
- **Verified sync** — new manifest/shard path in the backend sync service that
  writes a **disposable cache** distinct from the evidence store consumed by
  `materialize_probe_catalog_candidates`. The legacy single-file `/catalog/sync`
  stays as fallback (R4.4).
- **Schema mapping** — `probe_result` ↔ `probe` adapter at the ingestion/artifact
  boundary, anchored on `registry/schema.py` (R5).

### External infra (contract-only here)
- **Gate**: stateless function; secrets = ingestion-token signing key + the
  ingestion buffer credentials. Explicitly NOT the GitHub repo token.
- **Publishing Action**: scheduled workflow; secrets = artifact signing key +
  (implicit) `GITHUB_TOKEN` with `permissions: contents: write`.

## System Flows

### Upload (opt-in)
1. User reviews probe evidence and opts in to share a batch.
2. Client builds payload via redactor: strip forbidden fields; for each endpoint,
   allowlist → normalized URL + fingerprint, else **drop identity**.
3. Client POSTs to gate with ingestion token + idempotency key.
4. Gate authenticates, rate-limits, **re-validates redaction** (`extra=forbid`,
   secret/private-host scans), enqueues, returns `receipt_token`.
5. Client records ack + stores `receipt_token`. On failure/offline → keep queued.

### Publish (cron, external)
6. Action drains queue, aggregates, **signs** shards + `manifest.json` (with
   protocol major version), commits with minimal write permission.

### Sync (verified, read-path migration)
7. Client GETs `manifest.json` from Pages; ETag-diff selects changed shards.
8. Client downloads changed shards; **verifies signature/digest (fail-closed)**;
   if major version is newer than the client supports → refuse with clear error.
9. Verified content merges into the **disposable suggestion cache**; previous good
   cache is retained on any verify failure.

## Requirements Traceability
| Req | Design element |
|---|---|
| R1 | Opt-in upload flow; `/catalog/share` untouched; `"probe"` filter reused |
| R2 | Redaction + allowlist filter (pure function) |
| R3 | Upload client (token, idempotency, ack, offline queue) |
| R4 | Verified sync + disposable cache + manifest version gate |
| R5 | `probe_result`↔`probe` adapter on `registry/schema.py` |
| R6 | `receipt_token` store on client; withdraw is gate-side |
| R7 | Gate rate-limit/queue contract; Pages serving; Action least-privilege |
| R8 | `/catalog/repository/ensure` untouched; dormant-without-config default |

## Components And Interfaces

### `POST /v1/evidence/batches` (gate contract the client targets)
- Request: `{ idempotency_key, install_token, records: [EvidenceUpload...] }`
- `EvidenceUpload`: `{ evidence_type: "probe_result", provider_id,
  endpoint_fingerprint?, normalized_public_base_url?, route_key,
  provider_model_id, capability_profile, observed_at }`
  — `extra=forbid`; no secret/credential/path/prompt fields permitted.
- Response: `{ accepted: int, rejected: [{index, reason}], receipt_token }`

### `manifest.json` (artifact contract the client consumes)
- `{ protocol_major: int, generated_at, shards: [{ id, etag, digest, sig }] }`
- Client refuses `protocol_major > supported_major`.

### Artifact verification
- Detached signature over each shard digest; client holds the public key; verify
  is fail-closed.

## Data Models
- Reuse `EvidenceRecord` (`registry/schema.py`); add the `"probe_result"` →
  `"probe"` mapping at the boundary, not a new internal type.
- **Disposable cache**: a separate on-disk store (e.g.
  `remote_catalog_cache/`), never described or read as the canonical evidence
  library; cleared/rebuilt on sync; failures never corrupt the evidence store.

## Error Handling
- Gate unreachable / 5xx / timeout → keep batch queued; surface retry, no data loss.
- Gate 4xx (rejected record) → show per-record reason; do not silently drop.
- Sync signature/digest fail → reject artifact, keep last good cache, log.
- Manifest major-version too new → refuse, prompt client upgrade.
- No gate configured → all upload/verified-sync code dormant; MVP1 path unchanged.

## Testing Strategy
TDD, tests first. In-repo, runnable under this repo's CI:
- **Redaction red-line tests**: forbidden fields stripped; private/non-allowlisted
  host yields no base URL and no raw hash; allowlisted host yields normalized URL +
  fingerprint; un-salted SHA-256 never appears.
- **Upload client tests**: idempotency, ack + `receipt_token` persisted, offline
  queue retention, ingestion-scoped token only (assert no GitHub repo token path).
- **Verified sync tests**: ETag-diff selects only changed shards; signature/digest
  **fail-closed**; major-version-too-new refusal; disposable cache isolation from
  evidence store; legacy `/catalog/sync` fallback still works.
- **Schema mapping test**: `probe_result` round-trips to `probe`, consumable by
  `materialize_probe_catalog_candidates`.
- **Boundary regression**: `/catalog/share` contract unchanged
  (`local_export_only`, `auto_upload_enabled=false`); `/catalog/repository/ensure`
  unchanged; dormant-without-config behaves as MVP1.

External-infra tests (gate, Action — in the service repo, NOT this repo's CI):
Action least-privilege, signature fail-closed at publish, rate-limit responses,
token-extraction abuse simulation, manifest downgrade/rollback refusal.
