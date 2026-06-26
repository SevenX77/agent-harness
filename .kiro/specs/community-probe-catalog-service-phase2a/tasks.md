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

# Tasks — Community Probe Catalog Service (Phase 2a)

> **Status: planning artifact (phase-2 / post-MVP1).** Tasks are recorded now and
> sequenced TDD-first (failing test → production code). Implementation begins only
> when this phase is prioritized; it does not change MVP1 behavior. Per repo SOP,
> each in-repo task is written by a1 with a2 audit (or vice-versa) and reconciled
> before merge; external-infra tasks are tracked in the service repo.

## Phase 0: Governance & Baseline
- [ ] 0.1 Confirm the locked design (this spec + design doc Phase 2a) is the
  contract; no scope beyond R1–R8.
- [ ] 0.2 Add `protocol_major` + artifact-signing public key as injected client
  config; default absent ⇒ feature dormant (R8.2). Test: dormant path == MVP1.

## Phase 1: Redaction + allowlist drop (R2) — pure, highest red-line value
- [ ] 1.1 **Test first**: forbidden-field stripping (key/credential_ref/path/
  prompt/account-org) removed from an upload payload.
- [ ] 1.2 **Test first**: non-allowlisted/private host ⇒ no base URL, no raw hash;
  allowlisted host ⇒ normalized URL + fingerprint; un-salted SHA-256 never present.
- [ ] 1.3 Implement the redaction+allowlist pure function reusing the existing
  share redaction path; wire the public-provider allowlist.
- [ ] 1.4 Confirm `evidence_type == "probe"` filter reused; `provider-list-observed`
  never eligible (R1.3).

## Phase 2: Schema mapping (R5)
- [ ] 2.1 **Test first**: `probe_result` ingestion record ↔ `probe` evidence
  record round-trip; result consumable by `materialize_probe_catalog_candidates`.
- [ ] 2.2 Implement the boundary adapter on `registry/schema.py` (no new internal
  type).

## Phase 3: Opt-in upload client (R1, R3, R6)
- [ ] 3.1 **Test first**: opt-in only (no auto-upload); idempotency key dedups
  retries; ack + `receipt_token` persisted; offline queue retains on failure.
- [ ] 3.2 **Test first**: client uses ingestion-scoped token only — assert there is
  no code path that hands it a GitHub catalog-repo write token (R3.1).
- [ ] 3.3 Implement the upload client against `POST /v1/evidence/batches`
  (config-injected gate URL + token; dormant if absent).
- [ ] 3.4 Store `receipt_token` for later withdrawal; surface it in the share UI
  state (withdraw call itself is gate-side, R6).

## Phase 4: Verified manifest/shard sync (R4) — read-path migration
- [ ] 4.1 **Test first**: ETag-diff downloads only changed shards.
- [ ] 4.2 **Test first**: signature/digest verify **fail-closed**; on failure the
  previous good cache is retained.
- [ ] 4.3 **Test first**: `manifest.protocol_major` newer than supported ⇒ refuse
  with clear error (no crash).
- [ ] 4.4 **Test first**: disposable cache is isolated from the evidence store;
  rebuilding/clearing it never corrupts local evidence; legacy `/catalog/sync`
  fallback still works.
- [ ] 4.5 Implement the verified sync + disposable cache; serve via GitHub Pages
  URL (config), prefer Pages over `raw` (R7.3).

## Phase 5: Boundary regression guards (R8)
- [ ] 5.1 **Test first**: `/catalog/share` still returns `local_export_only` /
  `auto_upload_enabled=false` (no regression).
- [ ] 5.2 **Test first**: `/catalog/repository/ensure` unchanged and not used as the
  community upload path.
- [ ] 5.3 Run full backend + gateway suites + ruff + mypy --strict; green before PR.

## Phase 6: External infra (service repo — NOT this repo's CI)
- [ ] 6.1 Serverless gate: `POST /v1/evidence/batches`, anonymous install tokens,
  rate-limits, server-side redaction re-validation, enqueue, `receipt_token`,
  withdraw endpoint. **No GitHub repo token.** (R3, R6, R7.1)
- [ ] 6.2 Ingestion buffer (KV/D1) + scheduled publishing Action: drain, aggregate,
  **sign**, commit with minimal `permissions: contents: write` (R7.2, R7.4).
- [ ] 6.3 GitHub Pages publishing of shards + `manifest.json` (R7.3).
- [ ] 6.4 Service-repo tests: Action least-privilege, signature fail-closed at
  publish, rate-limit responses, token-extraction abuse sim, manifest
  downgrade/rollback refusal.

## Exit Criteria
- R1–R8 acceptance tests green in this repo (Phases 1–5).
- External-infra contracts (Phase 6) implemented + tested in the service repo with
  the red-lines held (gate holds no repo token; Action least-privilege; no
  un-salted hash published).
- MVP1 local-first behavior unchanged when no gate/artifacts configured.
