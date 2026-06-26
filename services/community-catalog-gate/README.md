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
| Ingestion gate | `src/gate.mjs` | Serverless Worker: accept opt-in batches, re-validate redaction, dedupe, buffer | KV buffer only |
| Redaction re-validation | `src/redaction.mjs` | Allowlist-only screen; rejects secrets / private hosts / bare hashes | none (pure) |
| KV drain | `publish/drain-kv.mjs` | Read buffer + withdrawals into a records file | none (read-only) |
| Aggregator / signer | `publish/aggregate.mjs` | Shard, digest, build + Ed25519-sign the manifest | writes files |
| Publishing Action (gate) | `publish/publish-catalog.yml` | Scheduled commit, drains the gate KV | `contents: write` |
| **No-gate** publisher | `publish/publish-from-incoming.mjs` | Read `incoming/` batches, re-screen, merge with shards, sign | writes files |
| **No-gate** Action | `publish/ingest-incoming.yml` | On `incoming/**` push: re-screen + sign + publish | `contents: write` |

## Two write-path deployments

Both deployments share the same redaction screen, aggregator, signer, and the
"only the Action holds repo-write power, the signing key is only an Action
secret" model. They differ only in **how evidence reaches the Action**:

- **Gate** (`src/gate.mjs` + KV + `drain-kv.mjs` + `publish-catalog.yml`) — for
  *multi-user* contribution: anyone's desktop POSTs an opt-in batch to a
  Cloudflare Worker that buffers it; a scheduled Action drains + publishes.
  Strangers never get repo-write power.
- **No-gate** (`publish-from-incoming.mjs` + `ingest-incoming.yml`) — the
  *simple* deployment: the desktop pushes sanitized batches straight into the
  repo's `incoming/` staging area with the user's own git credentials, and the
  Action re-screens + publishes on push. No Cloudflare, no KV. Fits a single
  trusted publisher (or a few collaborators) who already have repo write access.

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
- **Opt-in only.** A batch must carry a valid anonymous ingestion token
  (`INGESTION_TOKEN`). `Idempotency-Key` dedupes retries; the returned
  `receipt_token` lets a user later withdraw a contribution.
- **Signed read path.** The manifest is signed with an Ed25519 key whose private
  half exists only as the Action secret `CATALOG_SIGNING_PRIVATE_KEY_PEM`. The
  desktop client verifies with the matching raw public key
  (`STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY`) and fails closed on any mismatch.

## Wire protocol

`POST /v1/evidence/batches`

```
Authorization: Bearer <INGESTION_TOKEN>
Idempotency-Key: <stable per-batch key>
{ "protocol_major": 1, "records": [ { "evidence_type": "probe_result", ... } ] }
-> { "accepted": N, "rejected": M, "receipt_token": "uuid" }
```

`POST /v1/evidence/withdraw` — `{ "receipt_token": "uuid" }` → marks the
contribution for exclusion at the next publish.

## Setup

```bash
# 1. Generate the signing keypair.
npm run keygen
#   -> store the PEM as the Action secret CATALOG_SIGNING_PRIVATE_KEY_PEM
#   -> set the desktop client STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY=<hex>

# 2. Deploy the gate (Cloudflare Worker).
cp wrangler.toml.template wrangler.toml   # fill in KV namespace IDs
wrangler kv namespace create BUFFER
wrangler kv namespace create IDEMPOTENCY
wrangler kv namespace create WITHDRAWN
wrangler secret put INGESTION_TOKEN
wrangler deploy

# 3. Install the publishing Action in the PUBLIC catalog repo.
#   copy publish/publish-catalog.yml -> <catalog-repo>/.github/workflows/
#   vendor this dir as <catalog-repo>/gate (submodule or copy)
#   add secrets: CATALOG_SIGNING_PRIVATE_KEY_PEM, CF_* (read-only KV token)

# 4. Point the desktop client at the catalog + gate.
#   STUDIO_COMMUNITY_CATALOG_MANIFEST_URL=https://<pages-cdn>/manifest.json
#   STUDIO_COMMUNITY_UPLOAD_ENABLED=true
#   STUDIO_COMMUNITY_GATE_URL=https://<worker-host>
#   STUDIO_COMMUNITY_INGESTION_TOKEN=<INGESTION_TOKEN>
```

### No-gate setup (desktop pushes to `incoming/`)

```bash
# 1. Generate the signing keypair (same as above) — store the PEM as the catalog
#    repo's Action secret CATALOG_SIGNING_PRIVATE_KEY_PEM.

# 2. Vendor the publisher into the PUBLIC catalog repo, preserving layout, and
#    install the no-gate Action:
#      .catalog-publisher/publish/publish-from-incoming.mjs
#      .catalog-publisher/publish/aggregate.mjs
#      .catalog-publisher/src/redaction.mjs
#      publish/ingest-incoming.yml -> <catalog-repo>/.github/workflows/

# 3. Point the desktop client at the catalog + its own repo (no gate URL/token).
#    No-gate REUSES the existing github_* + llm_catalog_* settings, plus one switch
#    (STUDIO_COMMUNITY_NOGATE_UPLOAD_ENABLED) — distinct from the gate's
#    STUDIO_COMMUNITY_UPLOAD_ENABLED. After a successful probe the desktop silently
#    pushes sanitized batches to incoming/; the user perceives nothing.
#      STUDIO_COMMUNITY_CATALOG_MANIFEST_URL=https://<pages-cdn>/manifest.json
#      STUDIO_COMMUNITY_NOGATE_UPLOAD_ENABLED=true
#      STUDIO_GITHUB_TOKEN=<token with contents:write on the catalog repo>
#      STUDIO_GITHUB_OWNER=<your github login>             # repo owner
#      STUDIO_LLM_CATALOG_REPO=studio-llm-model-catalog    # incoming/ push target (name)
#      STUDIO_LLM_CATALOG_BRANCH=main
```

## Test

```bash
npm test   # node --test — redaction screen + sign/verify contract, zero deps
```
