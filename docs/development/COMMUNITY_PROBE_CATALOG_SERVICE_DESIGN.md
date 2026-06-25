# Community Probe Knowledge Catalog Service Design

> Status: draft design for phase 2. This document does not change MVP1 local
> Probe Knowledge Catalog behavior and does not reintroduce Import Draft as a
> product feature.

## Problem Statement

MVP1 keeps Probe Knowledge Catalog local-first: local endpoint/model/capability
probe results are appended to the local catalog, remote catalog sync is a
read-only suggestion source, and `/api/llm/catalog/share` only produces a local
sanitized export. Phase 2 needs a separate Community Catalog Service that can
accept many users' probe evidence, remove sensitive data, resist abuse, aggregate
evidence into explainable summaries, and publish read-only catalog artifacts for
future Studio clients.

The service must answer one product question: when a new user configures a
provider, endpoint, protocol, model, or capability, how can Studio show useful
candidate information that is correct enough to save time, explainable enough to
debug, verifiable by local probe, and unable to pollute local active
credentials?

The core rule remains unchanged: community evidence is advisory. It may seed
candidate model lists, capability hints, probe priority, and `historical_ready`
blue state. It must never write `ready` green or active route verification into
local credentials. Only the current user, current key, and local probe can do
that.

## Non-Goals

- Do not restore Import Draft as a feature. `draft` is legacy wording only.
- Do not design a remote evidence path that automatically applies credentials,
  endpoints, routes, roles, model profiles, or active `route.status=verified`.
- Do not let the desktop app hold a maintainer token that can write a public
  catalog repository.
- Do not upload API keys, `credential_ref`, local paths, raw prompt/input/output,
  user account identifiers, organization identifiers, or private endpoint
  originals.
- Do not treat `provider-list-observed` as connectivity evidence. Only real
  successful probe evidence may contribute to `historical_ready`.
- Do not make the community service part of the gateway runtime execution path.
  Runtime resolution still executes explicit `route_id` fallback chains.

## Current MVP1 Contract

MVP1 has three relevant contracts that phase 2 must preserve.

First, active configuration truth lives locally in V4 credentials and V2/V3
roles. Gateway runtime resolution uses exact route IDs from the role fallback
chain. Catalog evidence can help discover candidates and explain state, but it
cannot select a replacement route.

Second, Probe Knowledge Catalog is local-first and append-only. It can store
endpoint evidence, model-list observations, route probe success/failure, and
capability observations. Remote sync is read-only and advisory. Share/export is
`local_export_only`, with `auto_upload_enabled=false`.

Third, UI state is a six-state projection:

| State | Meaning |
|---|---|
| `ready` | Local live probe verified for this user/key/route. |
| `historical_ready` | Historical route probe success exists, but current route is not live verified. |
| `untested` | No live or historical connectivity evidence. |
| `failed` | Configuration or probe failure, with reason. |
| `cooling_down` | Temporary network/rate-limit/quota circuit with retry time. |
| `off` | Disabled or deprecated/unavailable model. |

Remote community artifacts can only affect `historical_ready`, `untested`,
capability provenance, model-list fallback, and probe priority. They cannot
produce `ready`.

## Proposed Architecture

### Recommended Shape

Use a hosted ingestion and aggregation service that publishes signed read-only
artifact shards. Studio clients upload only after explicit opt-in and download
only read-only artifacts. The client never writes the public catalog mirror
directly.

Alternative A, a GitHub-only community catalog edited by maintainers, is simple
but does not scale to high-volume evidence, dedupe, rate limiting, or abuse
control. Alternative B, peer-to-peer catalog sharing, avoids a hosted service but
cannot provide reliable withdrawal, scoring, signatures, or privacy enforcement.
The hosted service plus artifact publishing model is the right phase-2 design
because it separates mutable untrusted ingestion from stable read-only sync.

### Boundaries

| Component | Responsibilities |
|---|---|
| Desktop app / frontend | Shows upload preview, asks for opt-in, displays local queue/ack status, renders read-only artifact-derived suggestions. It never stores public repo maintainer tokens. |
| Studio backend | Owns local storage, redaction preview, upload queue, retry, local ack records, read-only artifact sync, and HTTP shell for frontend. It never lets remote evidence write active `ready`. |
| Gateway SDK | Owns reusable data contracts and algorithms: endpoint normalization, endpoint fingerprinting, model/capability normalization, probe priority, catalog matching, six-state projection input semantics. It is storage-agnostic. |
| Community Catalog Service | Authenticates upload clients, validates schema, rejects unsafe/private data, rate-limits, deduplicates, stores raw accepted evidence, aggregates summaries, signs artifacts, supports withdrawal and audit. |
| Artifact CDN / GitHub mirror | Serves signed read-only shards and manifests by provider/protocol/version/ETag. It has no ingestion API and no secrets. |

### Data Flow

1. Local probe appends evidence into local `llm_probe_catalog.json`.
2. Studio builds a sanitized upload batch from local evidence that has not been
   acknowledged.
3. User previews and explicitly opts in.
4. Studio uploads to Community Catalog Service with a client token and idempotency
   keys.
5. Service validates, redacts again, deduplicates, stores accepted evidence, and
   returns per-record ack/reject details.
6. Aggregation jobs compute provider/endpoint/model/route/capability summaries.
7. Publishing jobs write signed artifact shards to CDN/GitHub mirror.
8. Studio startup or manual sync downloads provider-relevant shards by manifest,
   ETag, and incremental cursor.
9. Gateway matching logic uses the artifact as a suggestion source only.

## Data Model and Indexes

### Core Entities

`ProviderProfile`
: `provider_id`, display metadata, provider kind, known public domains,
supported protocols, optional region/cohort taxonomy, deprecation status.

`EndpointProfile`
: `provider_id`, `endpoint_fingerprint`, optional `public_base_url_hash`,
optional public `normalized_base_url` when safely shareable, `protocol`,
`request_mapper_id`, `auth_scheme_class`, region/cohort hints, first/last seen
windows, connectivity summaries, deprecation status.

`ModelProfile`
: `provider_id`, `provider_model_id`, `canonical_model_id`, display aliases,
model family, modality, first/last seen windows, deprecation signals, list-source
observations.

`RouteProfile`
: `route_key = endpoint_fingerprint + provider_model_id + method_id/request_mapper_id`,
connectivity summary, capability summary, failure summary, trust score, evidence
refs, latest safe explanation.

`CapabilityProfile`
: normalized capability key/value, source class, confidence, evidence refs,
first/last verified windows, conflict state.

`EvidenceRecord`
: immutable event with `evidence_id`, `schema_version`, `source_client`,
`idempotency_key`, `provider_id`, endpoint/method/model keys, `evidence_type`,
`trust_state`, `observed_at`, client/library versions, privacy class, failure
class, latency bucket, capability summary, and signature/hash metadata.

`ArtifactMetadata`
: artifact schema version, build id, build time, source evidence cutoff, signing
key id, shard key, row counts, content digest, previous manifest pointer,
compatibility range.

### Evidence Types and Trust States

`probe_result`
: Real endpoint or route probe. Success can become `probe-verified`; failure can
become `probe-failed`.

`model_list_observation`
: Provider list output. It can seed candidates and model existence hints, but it
is not connectivity proof.

`capability_observation`
: Capability from API list, provider docs, local probe, or verified profile.
Only probe-derived capability facts count as verified.

`deprecation_observation`
: Explicit provider response that a model is absent, disabled, retired, or
unsupported.

`artifact_correction`
: Service-side moderation, withdrawal, schema migration, or provider rule update.

Trust states:

- `probe-verified`: real local probe succeeded.
- `probe-failed`: real local probe failed; failure class required.
- `provider-list-observed`: provider list showed a model; not connectivity.
- `provider-doc-observed`: provider docs or official metadata; not connectivity.
- `community-reported`: accepted but low-confidence non-probe metadata.
- `deprecated`: model/route appears removed or explicitly unsupported.
- `stale`: old evidence retained for history but excluded from fresh scoring.
- `withdrawn`: rejected after audit or user/provider removal request.

### Index Strategy

Use flat append-only evidence storage plus derived relational/columnar/search
indexes. Do not make nested provider JSON the service database of record.

Recommended storage:

- Raw accepted evidence: append-only partitioned table or object log by
  `provider_id`, month, and schema version.
- Aggregation store: relational tables for provider, endpoint, model, route, and
  capability summaries.
- Analytical store: columnar partitions for time-window scoring and abuse
  analysis.
- Search index: optional, for admin/debug lookup by model aliases or provider
  text.
- Published artifacts: compact JSON or JSONL shards, gzip/zstd compressed,
  signed by manifest.

Primary indexes:

- `provider_id`
- `(provider_id, endpoint_fingerprint, protocol, request_mapper_id)`
- `(provider_id, protocol, canonical_model_id)`
- `(provider_id, provider_model_id)`
- `(provider_id, endpoint_fingerprint, provider_model_id, request_mapper_id)`
- `(capability_key, capability_value, provider_id)`
- `(source_cohort, region_hint, provider_id)` when enough safe cohort data exists
- `(observed_at_bucket, trust_state, failure_class)`
- `idempotency_key` unique per client/install pseudonym
- `evidence_hash` unique for dedupe across retries and clients

Artifacts should be sharded first by provider, then optionally by protocol and
model family for high-volume providers:

```text
manifest.json
providers/{provider_id}/index.json
providers/{provider_id}/endpoints/{protocol}-{shard}.jsonl.zst
providers/{provider_id}/models/{family_or_hash_shard}.jsonl.zst
providers/{provider_id}/routes/{protocol}-{hash_shard}.jsonl.zst
providers/{provider_id}/capabilities/{capability_key}.jsonl.zst
```

## Ingestion API

### Auth and Identity

Phase 2 should support anonymous/pseudonymous upload tokens, with an upgrade path
to signed-in accounts for higher limits. The default desktop client requests a
privacy-preserving upload token from the service. The token identifies an install
or account pseudonym, not a user account name. Tokens are scoped to ingestion
only and cannot publish artifacts or write a mirror repository.

Suggested auth tiers:

| Tier | Use | Limits |
|---|---|---|
| Anonymous token | Default opt-in client uploads. | Low daily volume, strict duplicate and private endpoint checks. |
| Signed account token | Trusted contributors, CI probes, maintainers. | Higher volume, stronger audit trail. |
| Official publisher token | Official provider or project-maintained probes. | Highest trust, strict signing, separate review lane. |

### Batch Endpoint

`POST /v1/evidence/batches`

Required headers:

- `Authorization: Bearer <upload_token>`
- `Idempotency-Key: <batch_key>`
- `Content-Type: application/json`
- optional `X-Catalog-Client-Version`

Request body:

```json
{
  "schema_version": 1,
  "client": {
    "app": "studio",
    "app_version": "x.y.z",
    "gateway_version": "x.y.z",
    "platform_family": "macos|windows|linux|ci",
    "locale_region": "optional coarse region"
  },
  "privacy_attestation": {
    "local_redaction_version": "v1",
    "user_confirmed_upload": true
  },
  "records": [
    {
      "idempotency_key": "stable per local evidence record",
      "local_evidence_ref": "opaque local id, hashed before upload",
      "evidence_type": "probe_result",
      "trust_state": "probe-verified",
      "observed_at": "2026-06-24T00:00:00Z",
      "provider_id": "openai",
      "endpoint": {
        "endpoint_fingerprint": "sha256:...",
        "normalized_public_base_url": "https://api.openai.com/v1",
        "base_url_share_class": "public_known",
        "protocol": "openai_compatible",
        "request_mapper_id": "openai_chat_completions",
        "auth_scheme_class": "bearer_api_key"
      },
      "route": {
        "provider_model_id": "gpt-4.1",
        "canonical_model_id": "openai:gpt-4.1",
        "method_id": "chat_completions",
        "request_mapper_id": "openai_chat_completions"
      },
      "probe": {
        "status": "ok",
        "failure_class": null,
        "latency_bucket_ms": "500-1000",
        "http_status_class": "2xx"
      },
      "capabilities": {
        "input_modalities": {
          "value": ["text"],
          "source": "probed_verified"
        }
      }
    }
  ]
}
```

Response:

```json
{
  "batch_id": "srv_batch_...",
  "status": "accepted_with_rejections",
  "accepted": [
    {
      "idempotency_key": "...",
      "server_evidence_id": "ev_...",
      "dedupe_status": "new|duplicate",
      "artifact_visibility": "eligible_after_aggregation"
    }
  ],
  "rejected": [
    {
      "idempotency_key": "...",
      "code": "private_endpoint_detected",
      "message": "Endpoint can only be kept local."
    }
  ],
  "retry_after_seconds": null
}
```

### Required and Forbidden Fields

Allowed upload fields are normalized provider/model/protocol/capability facts,
coarse probe outcome, latency bucket, failure class, client/gateway version,
public endpoint or endpoint fingerprint, and evidence hashes.

Forbidden fields:

- API keys or any secret material.
- `credential_ref`.
- Local file paths, usernames, home directories, project paths.
- Raw prompts, raw model inputs, raw outputs, request bodies, response bodies.
- Account IDs, organization IDs, billing IDs, team names, email addresses.
- Private/internal base URL originals.
- Full IP addresses or private hostnames.
- Headers except coarse auth scheme class.
- Provider error bodies containing user/account/request identifiers.

### Idempotency and Retry

Each record needs a stable local `idempotency_key` derived from local evidence id,
normalized route key, observed timestamp bucket, and event type. Each batch needs
a separate batch idempotency key. Retries use the same keys. The service must be
safe for at-least-once delivery and return duplicate acknowledgements without
duplicating evidence.

The client retries transient service failures with exponential backoff and keeps
local records queued until acknowledged, rejected, expired, or user disables
upload. Rejections are stored locally with reason so the same unsafe record is
not repeatedly retried.

## Aggregation and Trust

### Matching Rules

Use the most specific safe key first:

1. Exact route: `provider_id + endpoint_fingerprint + protocol + request_mapper_id + provider_model_id + method_id`.
2. Endpoint/model: `provider_id + endpoint_fingerprint + protocol + provider_model_id`.
3. Provider/protocol/model: `provider_id + protocol + provider_model_id`.
4. Canonical model family: `provider_id + protocol + canonical_model_id`.
5. Provider/protocol fallback candidates.

The client should prefer exact matches. Degraded matches can seed candidates and
probe order, but cannot show `historical_ready` unless the artifact clearly marks
route-level probe success that matches the user's endpoint fingerprint or a
public-known endpoint identity equivalent.

Normalization must be deterministic and shared with gateway SDK rules:

- Normalize base URL by protocol before fingerprinting.
- Include protocol and request mapper in endpoint and route keys.
- Keep provider model ID exact; canonical model ID is grouping, not execution.
- Treat transport prefixes and endpoint-scoped aliases conservatively.
- Split public and private endpoint handling before any original URL leaves the
client.

### Conflict Handling

When evidence conflicts, preserve the conflict instead of hiding it. The
published summary should show:

- success count and weighted success score;
- failure count by failure class;
- latest successful window;
- latest failure window;
- deprecation signals;
- trust score;
- explanation refs.

Client rule: uncertainty downgrades to `untested` or low-priority suggestion, not
green. Recent verified success can produce blue only under the narrow matching
rule; recent hard deprecation can move a candidate toward `off`/deprecated
suggestion but still allows local re-probe because deprecation can be reversible.

### Scoring

A route's aggregate score should combine:

- trust source weight: provider-maintained probe > project CI probe > signed-in
  user probe > anonymous probe > provider list/doc observation;
- recency decay: recent evidence matters more, with half-life tuned per provider;
- diversity: multiple independent cohorts count more than repeated reports from
  one token/IP/client;
- outcome: success boosts, temporary failures mildly penalize, hard invalid-model
  or deprecation strongly penalizes;
- version fit: client/gateway/provider protocol versions close to current build
  count more;
- abuse risk: suspicious clusters are downweighted or quarantined.

Suggested trust bands:

| Band | Meaning | Client effect |
|---|---|---|
| `verified_high` | Multiple recent independent probe successes, no strong contrary signal. | Candidate, capability hints, probe priority, blue if exact route match. |
| `verified_mixed` | Probe success exists but failures/conflict are significant. | Candidate and probe priority with warning; blue only if exact and recent enough. |
| `observed_only` | Provider list/docs only. | Candidate/model-list fallback, gray untested. |
| `failed_recent` | Recent failures dominate. | Lower probe priority; show failure explanation if useful. |
| `deprecated_likely` | Provider says gone/unsupported or repeated invalid-model. | Deprecated/off suggestion, still allow local re-probe. |
| `quarantined` | Abuse/privacy/schema risk. | Not published to client artifacts. |

### Artifact Derivations

Published artifacts should contain summaries, not raw high-cardinality user event
logs. Raw evidence remains service-side for audit and recomputation. Each summary
row should include enough provenance to explain itself without exposing users:

- count windows, not user identifiers;
- evidence class counts;
- latest observation windows;
- confidence/trust band;
- top failure classes;
- capability sources and confidence;
- artifact evidence refs that resolve only to safe server-side/debug IDs.

## Client Sync and Upload Flow

### Read-Only Sync

On startup or manual sync, Studio downloads a small manifest first. It sends or
uses only local provider IDs and existing ETags; it should not upload local
credentials or private endpoint originals as part of sync.

Flow:

1. Fetch `manifest.json` with current artifact schema and provider shard list.
2. Compare ETag/build id against local artifact cache.
3. Download only configured providers and default notable providers.
4. For high-volume providers, download only protocol/model-family shards needed
   by local endpoints or visible settings pages.
5. Verify digest and signature before use.
6. Merge artifact into local read-only suggestion cache, separate from local
   append-only evidence.

Incremental sync can use either ETags per shard or a manifest cursor:
`since_build_id`, `provider_id`, `protocol`, `shard_key`. If a client misses too
many versions, it falls back to downloading the latest shard.

### Upload Queue

Local upload is opt-in and visible.

1. Local probe writes local evidence.
2. Studio classifies evidence as shareable, local-only, or blocked.
3. User sees a preview: record counts, providers, public endpoints vs hashed
   endpoints, model IDs, capability keys, failure classes, and forbidden fields
   removed.
4. User enables upload globally or per batch/provider.
5. Studio sends batches in the background, storing per-record ack/reject.
6. Upload failure leaves records queued with retry backoff.
7. Disabling upload stops new uploads; already acknowledged records remain in the
   community service unless later withdrawal is supported for that token/account.

Local ack record fields:

- local evidence id;
- upload policy version;
- upload batch id;
- server evidence id or reject reason;
- uploaded artifact eligibility status;
- timestamp;
- redaction version;
- schema version.

## Privacy and Abuse Controls

### Client-Side Redaction

Before preview or upload, Studio must reject private data locally:

- private IP ranges: RFC1918, loopback, link-local, multicast, carrier-grade NAT,
  IPv6 ULA/link-local;
- `.local`, `.lan`, `.internal`, `.corp`, `.home`, and configurable internal
  suffixes;
- unqualified hostnames;
- localhost and machine names;
- file paths in URLs or metadata;
- ports usually tied to local dev unless explicitly public and allowlisted;
- hostnames containing likely user/org tokens.

If an endpoint is private, upload only an endpoint fingerprint and coarse
provider/protocol facts when safe; otherwise mark local-only. For unknown
endpoints, default to local-only unless the user marks the endpoint public and
the service passes its own public-host validation.

### Service-Side Validation

The service repeats redaction and validation independently:

- schema validation with `extra=forbid`;
- deny secret-looking strings by entropy and known key prefixes;
- deny private IP/host patterns after DNS-safe parsing without resolving private
  hostnames unnecessarily;
- deny raw request/response body fields;
- scan metadata for paths, emails, org/account identifiers, bearer tokens, and
  provider key prefixes;
- quarantine records with unexpected fields or suspicious values;
- attach validation version and rejection reason.

### Abuse and Operations

Controls:

- token bucket rate limits by token, IP/cohort, provider, endpoint fingerprint,
  and batch size;
- duplicate suppression by idempotency key and evidence hash;
- anomaly detection for sudden mass failures/successes from one cohort;
- minimum independent-source threshold before high-trust publication;
- quarantine queue for suspicious providers/endpoints/models;
- provider/maintainer allowlists for public base URL publication;
- signed ingestion from project CI probes;
- audit log for accepted/rejected/withdrawn evidence;
- withdrawal/erasure path for records associated with a token/account where
  feasible;
- provider takedown/correction mechanism;
- artifact rollback by build id;
- signing key rotation and artifact compatibility windows;
- metrics for acceptance rate, rejection reasons, shard size, sync errors,
  scoring drift, and top conflict clusters.

## Migration Plan

1. Keep MVP1 behavior unchanged. `llm_probe_catalog.json` remains local-first,
   and `/catalog/share` remains local export only.
2. Introduce canonical phase-2 names in docs and APIs:
   `CommunityCatalogService`, `EvidenceRecord`, `ProbeKnowledgeCatalog`, and
   `CatalogArtifact`. Keep `ProviderImportDraft` only as legacy storage wording.
3. Add a local upload queue in a future implementation without changing local
   catalog append semantics.
4. Add explicit user opt-in and preview before any network upload.
5. Add hosted ingestion in shadow mode: accept batches, validate, return ack, but
   do not publish artifacts until scoring and privacy audits pass.
6. Publish beta artifacts under a new schema version and keep MVP1 remote catalog
   sync compatible with existing read-only artifacts.
7. Migrate local legacy containers by read-compatible adapters. Never rewrite or
   delete user local evidence without backup.
8. Add artifact sync cache separate from local evidence store. Remote artifact
   cache is disposable; local evidence is not.
9. Deprecate old default GitHub catalog file only after clients support manifest
   sync and a compatibility mirror exists.

Migration invariants:

- A catalog-seeded route is `unverified_manual` / `untested`, not verified.
- Catalog capabilities keep provenance/evidence refs.
- Remote evidence never mutates API key, credential ref, roles, or active route
  readiness.
- Provider-list observations never produce blue.
- Legacy `draft` names do not appear in new public APIs except migration notes.

## Test Plan

Service tests:

- Schema accepts valid batches and rejects unknown fields.
- Forbidden fields are rejected, including API keys, credential refs, local paths,
  prompts, outputs, account/org IDs, and private endpoint originals.
- Private endpoint detection covers IPv4, IPv6, localhost, internal DNS suffixes,
  unqualified hosts, and tricky URL encodings.
- Idempotency returns stable duplicate acks.
- Batch partial acceptance reports per-record errors.
- Dedupe does not drop genuinely distinct time-window evidence.
- Trust scoring handles success/failure conflicts, time decay, source diversity,
  deprecation, and suspicious clusters.
- Aggregation never lets `provider-list-observed` produce route connectivity.
- Artifact builder signs manifests, writes correct digests, and can roll back.
- Artifact compatibility tests load old and new schema versions.

Client tests:

- Upload queue only sends after user opt-in.
- Preview shows providers/models/capability/failure summaries and never shows
  forbidden raw data.
- Local-only/private evidence is not queued.
- Retry and ack state survive restart.
- Rejected records are not retried forever.
- Disabling upload prevents future sends.
- Artifact sync downloads by manifest/ETag and avoids full download when shards
  are unchanged.
- Remote artifact can seed candidates/capabilities/probe priority but cannot
  write active `ready`.

Gateway/shared algorithm tests:

- Endpoint fingerprint is stable across equivalent normalized URLs and different
  across protocol/request mapper changes.
- Exact route match outranks degraded provider/protocol matches.
- Degraded match cannot produce `historical_ready`.
- Provider-list evidence can seed untested model candidates only.
- Probe-verified exact historical route can produce blue; local probe success
  upgrades to green.
- Capability provenance survives artifact import.

Operational tests:

- Rate limits trigger predictable retry responses.
- Quarantined evidence is excluded from artifacts.
- Withdrawn/corrected evidence disappears from the next artifact build.
- Artifact signature verification fails closed.
- Rollback manifest restores previous build.

## Open Questions

1. Should default uploads use anonymous install tokens only, or require a signed
   account before any community contribution is accepted?
2. Which public endpoint allowlist should permit publishing normalized base URLs
   instead of only endpoint fingerprints?
3. What exact endpoint fingerprint salt policy should balance cross-user matching
   with privacy? A global public hash enables matching; per-install salt protects
   privacy but prevents aggregation.
4. Should private endpoint evidence ever upload as provider/protocol/model-only
   aggregate, or should all private endpoint evidence remain local-only?
5. What time-decay half-life should apply per provider class, especially for fast
   model churn providers and aggregator gateways?
6. How many independent sources are required before a route can appear as
   high-trust `historical_ready` in artifacts?
7. Should official provider/CI probes get a separate trust lane and visible
   provenance label in the client?
8. What artifact hosting target is preferred for phase 2: project CDN, GitHub
   Pages/raw mirror, or both?
9. Do we need a provider-facing correction/takedown process before public beta?
10. How should user withdrawal work for anonymous uploads when the service cannot
    identify the person behind a token?
11. Which failure classes should be standardized first across OpenAI-compatible,
    Anthropic-compatible, Gemini, and Ark runtimes?
12. When should legacy `ProviderImportDraft` storage be physically migrated to a
    new `ProbeKnowledgeCatalog` file/schema, versus kept behind adapters?
