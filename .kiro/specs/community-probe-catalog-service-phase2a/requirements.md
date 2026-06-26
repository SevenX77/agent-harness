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

# Requirements — Community Probe Catalog Service (Phase 2a)

## 1. Problem

MVP1 keeps the Probe Knowledge Catalog local-first: `/catalog/sync` pulls a
read-only single-file suggestion source and `/catalog/share` only does
`local_export_only`. Users cannot contribute the evidence ("which endpoint /
protocol / model / capability combinations connected or failed") that would let
later users skip dead ends. Phase 2 is the hosted community service; Phase 2a is
its free-tier starting shape that ships value without standing up costly infra
and **without breaking any Non-Goal or MVP1 contract**.

## 2. Product Decision

Ship community evidence contribution + richer remote sync on free tiers:

- A **serverless ingestion gate** receives opt-in, redacted evidence batches.
- A **scheduled publishing Action** (the only repo writer) aggregates and commits
  signed read-only artifacts.
- The desktop client gains **opt-in upload** and a **manifest/shard verified
  sync** into a disposable cache.

The local-first MVP1 behavior remains the default and the fallback.

## 3. Non-Goals (inherited, enforced)

- No Import Draft (待导入草稿 → apply) revival.
- No path that auto-applies remote evidence to active credentials.
- The desktop client never holds a token that can write the public catalog repo.
- Never upload API keys, `credential_ref`, local paths, raw prompt/input/output,
  account/org IDs, or identifiable private endpoints.
- `provider-list-observed` never contributes to `historical_ready`.
- Remote/community artifacts can feed `historical_ready` / `untested` / capability
  provenance / model-list fallback / probe priority — **never `ready`**.

## 4. Requirements

### R1 — Opt-in upload, no silent sharing
- **R1.1** Upload happens only on explicit per-batch user opt-in. There is no
  global "auto-upload" toggle in Phase 2a.
- **R1.2** `/catalog/share` keeps `sharing_mode="local_export_only"` and
  `auto_upload_enabled=false`. Acceptance: existing share contract test still
  passes unchanged.
- **R1.3** Only `evidence_type == "probe"` records are eligible to upload (same
  filter as `/catalog/share`). `provider-list-observed` is never uploaded.

### R2 — Client-side redaction + allowlist drop (privacy red-line)
- **R2.1** Before preview/upload the client strips all forbidden fields (API key,
  `credential_ref`, local paths, raw prompt/input/output, account/org IDs).
- **R2.2** Endpoint identity: if the host is on the public-provider allowlist,
  emit `normalized_public_base_url` + fingerprint; otherwise **drop the endpoint
  identity entirely** before upload. Acceptance: a private/non-allowlisted host
  produces an upload payload containing **no** base URL and **no** raw hash of it.
- **R2.3** A raw, un-salted SHA-256 of a base URL is never present in any upload
  payload or published artifact. Acceptance: redaction unit test asserts absence.

### R3 — Upload client targets the gate contract
- **R3.1** The client uploads via `POST /v1/evidence/batches` with an
  ingestion-scoped token only; it never holds a GitHub catalog-repo write token.
- **R3.2** Idempotent batches (idempotency key) so retries don't double-insert.
- **R3.3** On accepted upload the client records a local ack (and stores the
  returned `receipt_token` for later withdrawal — see R6).
- **R3.4** Offline / gate-unreachable: the batch stays queued locally; no data
  loss, no blocking of local-first flow.

### R4 — Verified manifest/shard sync (read-path migration)
- **R4.1** New sync flow: fetch `manifest.json` → ETag-diff → download only changed
  shards → verify signature/digest (**fail-closed**) → merge into a **disposable
  suggestion cache separate from the local evidence store**.
- **R4.2** `manifest.json` carries a protocol major version; a client on an older
  major **refuses** the artifact (clear error) rather than crashing.
- **R4.3** Signature/digest failure → artifact rejected, previous good cache kept.
- **R4.4** The legacy single-file `/catalog/sync` path remains available as a
  fallback/transition; the migration does not delete local evidence.

### R5 — Schema mapping
- **R5.1** The ingestion schema's `evidence_type: "probe_result"` maps to the
  gateway's existing `"probe"` on the way in/out. Acceptance: a round-trip test
  shows a `"probe_result"` ingestion record materializes as a `"probe"` evidence
  record consumable by `materialize_probe_catalog_candidates`.

### R6 — Withdrawal for anonymous uploads
- **R6.1** The gate returns a one-time `receipt_token` on accepted upload.
- **R6.2** A withdraw call with a valid `receipt_token` retracts that batch within
  a defined window. (Gate-side behavior; client stores + can present the token.)

### R7 — Abuse / ops controls (gate + Action)
- **R7.1** Gate enforces: anonymous install-token issuance rate-limit, per-token +
  per-IP request rate-limit, max batch size / record count, server-side revocation.
- **R7.2** Ingestion is queued (KV/D1); the cron Action drains and commits in
  batches (no per-request commit → no git non-fast-forward contention).
- **R7.3** Artifacts are served via GitHub Pages (CDN-backed), not `raw`, to avoid
  429 under sync load.
- **R7.4** The publishing Action runs with minimal `permissions: contents: write`;
  no other component holds repo-write.

### R8 — Boundary preservation
- **R8.1** `/catalog/repository/ensure` is not reused as the community upload path
  and keeps using the user's own token for the user's own repo only.
- **R8.2** No regression to MVP1 local-first defaults; with no gate configured the
  app behaves exactly as today.

## 5. Out of Scope (deferred to full hosted shape)
Signed-account tiers + official publisher lane (open Q1/Q7); strong anomaly
detection + quarantine automation; a dedicated CDN separate from GitHub (Q8);
server-side peppered-HMAC fingerprints for non-allowlisted public hosts (Q2/Q3
upgrade).
