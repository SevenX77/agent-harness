# Community Probe Catalog — Gate + Publisher (Phase 2a)

The server-side half of the Community Probe Catalog. It lets desktop users
**opt in** to sharing sanitized probe evidence (which public endpoint/model/
capability combos connected) and republishes the aggregate as a signed, CDN-
served catalog that any client can verify.

> This is a **separate Node/Cloudflare service**, deliberately **outside the
> Python uv-workspace and its CI gates**. It has its own zero-dependency tests
> (`node --test`). The desktop client side lives in
> `apps/studio/backend/app/services/community_catalog*.py`.

## Components

| Component | File | Role | Write power |
| --- | --- | --- | --- |
| Ingestion gate | `src/gate.mjs` | Serverless Worker: accept anonymous batches (no token), rate-limit, re-validate redaction, dedupe, buffer | KV buffer only |
| Redaction re-validation | `src/redaction.mjs` | Allowlist-only screen; rejects secrets / private hosts / bare hashes | none (pure) |
| KV drain | `publish/drain-kv.mjs` | Read buffer + withdrawals into a records file | none (read-only) |
| Aggregator / signer | `publish/aggregate.mjs` | Shard, digest, build + Ed25519-sign the manifest | writes files |
| Publishing Action | `publish/publish-catalog.yml` | Scheduled: drain gate KV, aggregate, sign, commit | `contents: write` |

## Write path

The gate enables **multi-user** contribution without giving anyone repo-write
power. Any desktop POSTs an opt-in, pre-sanitized batch to the Cloudflare Worker
(`src/gate.mjs`), which independently re-screens it (`src/redaction.mjs`) and
buffers the survivors to KV. A scheduled Action (`publish-catalog.yml`) drains
the buffer (`drain-kv.mjs`), aggregates + Ed25519-signs the manifest
(`aggregate.mjs`), and commits the signed catalog. Strangers never get
repo-write power; the gate holds no repo token; the signing private key exists
only as an Action secret.

## Security model (three-way converged design v3)

- **The gate holds no catalog-repo write token.** It only writes its own KV
  buffer. The *only* component that can write the public catalog repo is the
  scheduled Action, scoped to the minimum `contents: write`. A gate compromise
  cannot rewrite the catalog.
- **Defense in depth on redaction.** Even though the desktop client sanitizes
  before upload, `src/redaction.mjs` independently re-screens every record and
  rejects anything outside a strict field allowlist, any non-allowlisted base
  URL, and any bare endpoint fingerprint without its plaintext (no
  de-anonymizable hashes).
- **Clean open API + server-side rate limiting.** The client sends only
  sanitized records — no token, no credentials, nothing to configure or leak. A
  shared token would end up in every client anyway, so instead the gate is keyed
  on client IP via the Cloudflare `RATE_LIMITER` binding to shed floods, and
  redaction caps what any single request can land. `Idempotency-Key` dedupes
  retries; the returned `receipt_token` lets a user later withdraw a contribution.
- **Signed read path.** The manifest is signed with an Ed25519 key whose private
  half exists only as the Action secret `CATALOG_SIGNING_PRIVATE_KEY_PEM`. The
  desktop client verifies with the matching raw public key
  (`STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY`) and fails closed on any mismatch.

## Wire protocol

`POST /v1/evidence/batches`

```
Idempotency-Key: <stable per-batch key>
{ "protocol_major": 1, "records": [ { "evidence_type": "probe_result", ... } ] }
-> { "accepted": N, "rejected": M, "receipt_token": "uuid" }   # 429 if rate-limited
```

`POST /v1/evidence/withdraw` — `{ "receipt_token": "uuid" }` → marks the
contribution for exclusion at the next publish.

## Setup

```bash
# 1. Generate the signing keypair.
npm run keygen
#   -> store the PEM as the Action secret CATALOG_SIGNING_PRIVATE_KEY_PEM
#   -> set the desktop client STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY=<hex>

# 2. Deploy the gate (Cloudflare Worker). No token/secret — it's an open API
#    guarded by the RATE_LIMITER binding (configured in wrangler.toml).
cp wrangler.toml.template wrangler.toml   # fill in KV namespace IDs
wrangler kv namespace create BUFFER
wrangler kv namespace create IDEMPOTENCY
wrangler kv namespace create WITHDRAWN
wrangler deploy

# 3. Install the publishing Action in the PUBLIC catalog repo.
#   copy publish/publish-catalog.yml -> <catalog-repo>/.github/workflows/
#   vendor this dir as <catalog-repo>/gate (submodule or copy)
#   add secrets: CATALOG_SIGNING_PRIVATE_KEY_PEM, CF_* (read-only KV token)

# 4. Bake the public endpoints into the desktop build (defaults in
#    apps/studio/backend/app/core/backends.py — all public, no secrets):
#      community_gate_url, community_catalog_manifest_url,
#      community_catalog_signing_pubkey. Stock Studio then reads + contributes
#      with ZERO config; the single in-app catalog toggle is the only control.
```

After a successful probe the desktop silently uploads any newly probe-verified,
sanitized evidence to the gate — on by default, no token, the user perceives
nothing. Unreachable-gate batches are parked in a local offline queue and
retried, preserving their idempotency key.

## Test

```bash
npm test   # node --test — redaction screen + sign/verify contract, zero deps
```
