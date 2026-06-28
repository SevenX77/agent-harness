---
spec: studio-llm-remote-draft-catalog
status: Draft
date: 2026-06-20
---

# Design - Studio LLM Remote Draft Catalog

## 1. Current Route ID Behavior

The current active route identity is:

```text
route_id = endpoint_id + ":" + route_slug
```

`route_slug` is generated from `provider_model_id` by lowercasing and normalizing unsafe characters. The backend also has a collision branch for endpoint test discovery:

```text
base = <endpoint_id>:<slug(provider_model_id)>
if base already exists for a different provider_model_id:
  route_id = base + "-" + sha256(endpoint_id + ":" + provider_model_id)[0:8]
```

Import draft materialization trusts `RouteCandidate.route_slug` and materializes:

```text
route_id = candidate.endpoint_id + ":" + candidate.route_slug
```

Implication:

- Official endpoints are cross-terminal stable because endpoint IDs are stable.
- Custom providers are not cross-terminal stable today because the add-provider UI creates `custom-<randomUUID>` endpoint IDs.
- Therefore persisted custom endpoint IDs must stop being random. Local active credentials and the remote catalog must converge on the same URL-derived route ID.

## 2. Target Identity Model

There is one persisted route identity:

```text
route_id
  Shared by local active credentials and remote GitHub catalog.
  Used by roles, evidence, logs, projection, and route execution.
  Shape: <stable_endpoint_id>:<route_slug>.
```

For custom/third-party endpoints, `stable_endpoint_id` is derived from stable provider endpoint facts:

```text
canonical_base_url = canonicalize_base_url(raw_base_url, protocol)
endpoint_identity_material = protocol + "|" + canonical_base_url
stable_endpoint_id = url_endpoint_slug(canonical_base_url, protocol) + "-" + sha256(endpoint_identity_material)[0:10]
route_id = stable_endpoint_id + ":" + route_slug(provider_model_id)
```

Examples:

```text
https://openrouter.ai/api/v1 + openai_compatible
  -> openrouter-ai-api-v1-openai-<hash>:anthropic.claude-opus-4

https://llm.wavespeed.ai/v1 + openai_compatible
  -> llm-wavespeed-ai-v1-openai-<hash>:openai.gpt-5
```

The exact slug format can be adjusted, but these invariants are fixed:

- it is deterministic from canonical URL + protocol;
- it does not depend on display name;
- it does not depend on API key;
- it does not depend on random `custom-<uuid>`;
- hash input uses canonical URL after gateway protocol normalization.

For official providers, curated endpoint IDs like `openai-official` may remain the stable endpoint ID. The important rule is not that every endpoint uses the same textual formula; it is that the chosen persisted endpoint ID is deterministic and shared by local runtime and remote catalog.

## 3. Target Architecture

```text
GitHub repository: <user>/studio-llm-model-catalog
  llm_import_drafts.json
    drafts.studio-evidence-library
      route_candidates
      evidence_records
        probe-verified
        probe-failed
        provider-list-observed

Studio backend
  /api/llm/catalog/sync
    fetch GitHub raw
    validate ProviderImportDraft
    optionally cache locally with source metadata
    expose merged advisory catalog to registry projection

  /api/llm/catalog/repository/ensure
    call GitHub REST as Studio backend
    create/confirm <user>/studio-llm-model-catalog
    initialize llm_import_drafts.json through Contents API when missing

  /api/llm/catalog/share
    collect local public probe evidence
    sanitize
    produce catalog patch / PR payload

Active local runtime
  llm_credentials.json
    provider_endpoints
    provider_routes
    route.status

Frontend
  General settings switch controls automatic remote catalog reads
  render backend ui_state only
```

The remote catalog is a shared advisory knowledge base. Active runtime truth remains local credentials and local route status. Remote evidence can produce blue `historical_ready`, but only a local real probe promotes a route to green `ready`.

## 4. Remote Catalog File

Default repository:

```text
studio-llm-model-catalog
```

Default file path:

```text
llm_import_drafts.json
```

Minimum valid seed:

```json
{
  "drafts": {
    "studio-evidence-library": {
      "draft_id": "studio-evidence-library",
      "source": {
        "kind": "studio_evidence_library",
        "location": "github",
        "repo": "<github-owner>/studio-llm-model-catalog"
      },
      "status": "pending",
      "endpoint_candidates": {},
      "route_candidates": {},
      "probe_results": {},
      "evidence_records": [],
      "agent_notes": [],
      "diff": {}
    }
  }
}
```

The repository ensure API initializes this file through GitHub Contents API. Once initialized, the default raw URL shape is:

```text
https://raw.githubusercontent.com/<github-owner>/studio-llm-model-catalog/main/llm_import_drafts.json
```

The backend must keep GitHub access server-side. The frontend calls Studio APIs only.

## 4.1 GitHub API Design

Environment/config fields:

```text
STUDIO_GITHUB_TOKEN
STUDIO_GITHUB_OWNER          optional; inferred from GET /user when omitted
STUDIO_LLM_CATALOG_REPO      default: studio-llm-model-catalog
STUDIO_LLM_CATALOG_BRANCH    default: main
STUDIO_LLM_CATALOG_PATH      default: llm_import_drafts.json
```

GitHub calls:

```http
GET /user
GET /repos/{owner}/{repo}
POST /user/repos
GET /repos/{owner}/{repo}/contents/{path}?ref={branch}
PUT /repos/{owner}/{repo}/contents/{path}
```

The client must send:

```text
Authorization: Bearer <token>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
```

Behavior of `POST /api/llm/catalog/repository/ensure`:

1. Resolve owner from configured `STUDIO_GITHUB_OWNER` or GitHub `GET /user`.
2. Check `GET /repos/{owner}/{repo}`.
3. If missing, create public repo with `POST /user/repos` and `private: false`.
4. Check catalog file through Contents API.
5. If missing, create `llm_import_drafts.json` with the minimum valid seed.
6. Return repository URL, raw URL, file path, branch, and whether repo/file were created.

The ensure/write API should surface missing token and GitHub 4xx/5xx as structured Studio errors. It must not log the token.

Catalog reads are public reads. `/api/llm/catalog/sync` must read:

```text
https://raw.githubusercontent.com/<github-owner>/studio-llm-model-catalog/main/llm_import_drafts.json
```

Reading the public catalog must not require or send `STUDIO_GITHUB_TOKEN`. The token is only for owner discovery, repository creation, file initialization, and future branch/PR writeback.

## 5. Catalog Identity Policy

Allowed persisted endpoint ID forms in public catalog:

- official stable IDs: `openai-official`, `anthropic-official`, `gemini-official`, `deepseek-official`, `ark-official`;
- curated public proxy IDs only after explicit product approval, for example `openrouter-prod`;
- URL-derived stable endpoint IDs for custom/third-party public base URLs.

Rejected by default:

- random local `custom-*` / UUID-looking endpoint IDs as persisted or catalog identity;
- raw private base URLs in public catalog;
- any route candidate with secret-like metadata.

For private custom providers, private catalog mode may accept:

```text
STUDIO_CATALOG_URL=https://raw.githubusercontent.com/<private-org>/<private-repo>/<branch>/llm_import_drafts.json
```

That private catalog must be user-configured and must not write private raw URL evidence to the public default catalog. If the private catalog still wants to avoid exposing raw URLs, the stable endpoint ID may be hash-only or salt-scoped depending on the privacy model.

## 6. Matching Local Routes to Remote Evidence

Matching is direct:

```text
record.route_id == local.route_id
```

No runtime fallback may match old random route IDs. The migration must rewrite local data before the app relies on remote evidence.

## 7. Active Endpoint ID Policy

Future saved custom endpoints should prefer deterministic endpoint IDs derived from canonical URL + protocol:

```text
endpoint_id = <url-host-path-slug>-<protocol-suffix>-<hash8>
protocol-suffix = openai | anthropic | google | ark
```

Changing existing endpoint IDs breaks references unless all dependent stores are rewritten together. The migration must be an atomic hard cut:

1. Back up all affected local files/databases.
2. Compute stable endpoint IDs from canonical Base URL + protocol.
3. Compute stable route IDs from stable endpoint ID + route slug.
4. Rewrite `llm_credentials.json`.
5. Rewrite `llm_roles.yaml`.
6. Rewrite `llm_import_drafts.json`.
7. Rewrite `llm_role_test_results.json`.
8. Rewrite `llm_health.sqlite` circuit `scope_id` values for route and endpoint scopes.
9. Validate that no persisted route/endpoint/test/evidence reference points at `custom-<uuid>`.
10. Commit the rewritten local data atomically or restore the backup.

There is no compatibility mode after this migration. The app should refuse to run the LLM settings/projection workflow if old random IDs remain.

Final target state:

```text
No persisted random custom endpoint IDs.
No separate catalog route key.
Local active route_id == remote catalog route_id.
```

## 8. Pull Flow

`sync_remote_evidence_library` should become a true remote-first fetch:

1. Resolve catalog URL from explicit request URL, `STUDIO_CATALOG_URL`, or default GitHub raw URL.
2. Fetch with HTTP timeout.
3. Require HTTP 200 for "synced" status. A 404 should surface as a catalog error, not silently pretend local cache is current.
4. Parse JSON and validate `drafts["studio-evidence-library"]` as `ProviderImportDraft`.
5. Merge remote records into an in-memory or local cache copy.
6. Record source metadata: URL, ETag or commit SHA if available, fetched_at, remote evidence count.
7. Return counts and source metadata to the caller.

The local cache may use the existing app-support path, but it must be named and documented as a cache.

Automatic pull flow:

- `AppSettings.remote_model_catalog_enabled` defaults to `true`.
- Settings load may trigger one background catalog sync when the setting is enabled.
- Settings load must not sync when the setting is disabled.
- This sync does not request `/secret`, does not run provider tests, and does not promote routes to green.

## 9. Projection Flow

Registry projection consumes:

- active endpoint status;
- active route status;
- credential availability;
- health circuit;
- evidence records from the remote catalog/cache.

Projection remains:

```text
off > failed > cooling_down > ready > historical_ready > untested
```

`historical_ready` is allowed only when:

- endpoint status is `verified`;
- route status is not `verified`;
- matching evidence has `evidence_type = "probe"` and `trust_state = "probe-verified"`;
- evidence matches current route by the unified stable `route_id` only.

Provider-list observations may enrich candidates and capability tooltips but must not produce "Previously Connected".

### 9.1 Blue-State End-to-End Contract

The API Keys and LLM Roles UI must never infer blue state from frontend-only fields. Backend registry projection owns the state:

```text
ProviderRoute.status        local active status
ProviderRoute.ui_state      backend-projected UI state
ModelInfo.ui_state          compact frontend-friendly projection
ProviderModelOption.ui_state model group projection
```

The projection algorithm:

```text
if endpoint disabled or missing credential:
  ui_state = off
elif runtime circuit says failed/cooling:
  ui_state = failed/cooling_down
elif route.status == verified:
  ui_state = ready
elif remote/local evidence has matching probe-verified route_id:
  ui_state = historical_ready
elif route is catalog/provider-list candidate:
  ui_state = untested
else:
  ui_state = untested
```

Frontend mapping:

- `ready` -> green tag text such as `Ready`;
- `historical_ready` -> blue tag text such as `Previously connected`;
- `untested` -> neutral candidate tag;
- `failed` -> red failed tag;
- `cooling_down` -> warning/cooldown tag;
- `off` -> disabled/off tag.

The frontend must remove `status === "probe-verified"` as a required render path. If a compact response still includes old `status`, the UI may ignore it once `ui_state` is present.

### 9.2 Candidate Population Contract

Model-list observations create candidate routes but not historical readiness:

```text
model_list_observation -> route_candidates + provider-list evidence
probe success           -> probe-verified evidence + possible historical_ready
probe failure           -> probe-failed evidence + failed history, not blue
```

API Keys "Get models" may add many route candidates. Those candidates should be grouped under the provider and can carry capability hints, but they stay neutral until a real route probe succeeds.

### 9.3 Catalog Source Metadata

Every registry response that consumed remote catalog data should be able to expose non-secret catalog metadata for debugging:

```json
{
  "catalog_source": {
    "enabled": true,
    "source_url": "https://raw.githubusercontent.com/...",
    "fetched_at": "2026-06-20T23:00:00Z",
    "etag": "optional",
    "route_candidates_count": 0,
    "evidence_records_count": 0,
    "last_error": null
  }
}
```

This metadata is not necessary for route execution, but it prevents future ambiguity about whether the page read the remote catalog or only local cache.

## 10. Writeback Flow

Local probing writes local evidence immediately so the current session can use it. Publishing to GitHub is separate:

1. Collect newly generated local evidence since the last remote catalog source metadata.
2. Ensure every local route has a stable URL-derived route ID or a computed migration target.
3. Filter by public/private catalog target policy.
4. Sanitize fields.
5. Include route candidates required by the evidence.
6. Merge with the latest fetched remote catalog.
7. Produce a deterministic JSON patch or complete updated `llm_import_drafts.json`.
8. Return a PR-ready payload.

Default MVP1 behavior is not direct push. A later optional integration may create a branch and draft PR when GitHub credentials are explicitly configured.

### 10.1 Writeback API Shape

Add a writeback preview endpoint first:

```http
POST /api/llm/catalog/writeback/preview
```

Input:

```json
{
  "target": "public",
  "base_remote_sha": "optional remote file sha or etag",
  "include_failed_probe_evidence": true
}
```

Output:

```json
{
  "status": "success",
  "target": "public",
  "base_remote_sha": "...",
  "publishable_records_count": 0,
  "excluded_records_count": 0,
  "excluded_records": [
    {
      "evidence_id": "evidence-...",
      "reason_code": "private_base_url",
      "message": "Endpoint URL is not public-safe."
    }
  ],
  "catalog_patch": {
    "draft_id": "studio-evidence-library",
    "route_candidates": {},
    "evidence_records": []
  },
  "merged_catalog": {}
}
```

Then add an explicit PR endpoint:

```http
POST /api/llm/catalog/writeback/pr
```

It must:

1. Re-fetch remote catalog before writing.
2. Re-run sanitizer against the fresh remote base.
3. Create a branch named `studio-catalog/<timestamp>-<short-hash>`.
4. Commit updated `llm_import_drafts.json` to that branch.
5. Open a draft PR.
6. Return branch, commit SHA, PR URL, and exclusions.

It must not push directly to `main`.

### 10.2 Merge and Dedupe Rules

Merging local sanitized evidence with remote catalog is deterministic:

```text
record key = evidence_id
route candidate key = route_id
```

If a local record has the same `evidence_id` as remote:

- identical payload: keep one;
- different payload: exclude local record with `reason_code = evidence_id_conflict`.

If a local record has no `evidence_id`, it is not publishable. Evidence IDs are generated when evidence is first written locally, not during publication.

Output ordering:

1. `route_candidates` sorted by route ID.
2. `evidence_records` sorted by `observed_at`, then `attempted_at`, then `evidence_id`.
3. JSON serialized with stable indentation and sorted object keys.

## 11. Sanitization Rules

Publishable fields:

- `evidence_id`
- `evidence_type`
- `trust_state`
- `observed_at`
- `attempted_at`
- `scope`
- `provider_id`
- `endpoint_id`
- `route_id`
- `stable_endpoint_id`
- `stable_route_id`
- `canonical_base_url_hash`
- `model_id`
- `provider_model_id`
- `method_id`
- `request_mapper_id`
- `probe_status`
- non-sensitive `reason`
- `model_type`
- `capability_family`
- `input_modalities`
- `output_modalities`
- `candidate_methods`
- `candidate_capabilities`
- summarized `probe_attempts`
- `successful_probe`
- sanitized `failed_probe`

Forbidden fields or values:

- API keys;
- Authorization headers;
- full request body;
- full response body;
- private base URLs;
- account IDs;
- organization IDs;
- local filesystem paths;
- raw provider error objects;
- any metadata value matching secret-like patterns.

### 11.1 Public URL Safety Classifier

Public writeback needs a deterministic classifier:

```text
classify_catalog_url(base_url) -> public_safe | private_or_internal | malformed | review_required
```

Rules:

- `localhost`, `.local`, `.internal`, `.lan`, `.home`, `.corp`, and hostnames without a public suffix are private/internal.
- Loopback, link-local, multicast, RFC1918, carrier NAT, and unique-local IPv6 addresses are private/internal.
- URLs with username/password are malformed for catalog publication.
- URLs with query or fragment are review-required by default.
- Paths longer than a generic API prefix are review-required unless provider allowlist says otherwise.
- Official provider URLs are public-safe through curated endpoint mapping.

The classifier must return both a boolean decision and a `reason_code`. The sanitizer must persist only the reason code and a generic message, not the raw private URL.

### 11.2 Sanitizer Pipeline

The sanitizer operates on one evidence record plus the active route/endpoint context:

```text
sanitize(record, route, endpoint, target="public")
  1. verify stable route_id and endpoint_id
  2. reject random custom/UUID-like endpoint IDs
  3. classify endpoint base_url
  4. remove secrets and raw request/response payloads
  5. keep only allowlisted evidence fields
  6. rewrite metadata to safe summaries
  7. validate ProviderImportDraft schema
```

Each rejected record returns:

```json
{
  "evidence_id": "...",
  "route_id": "...",
  "reason_code": "secret_like_value",
  "message": "Record contains a secret-like value."
}
```

Required reason codes:

- `random_legacy_route_id`
- `private_base_url`
- `malformed_base_url`
- `review_required_url`
- `secret_like_value`
- `raw_request_body`
- `raw_response_body`
- `missing_route_context`
- `evidence_id_conflict`
- `unsupported_evidence_type`

### 11.3 Route Candidate Sanitization

Route candidates are publishable only when referenced by at least one publishable evidence record or when produced by a public provider model-list observation. The published candidate must include:

- `endpoint_id`
- `route_slug`
- `provider_model_id`
- `canonical_id`
- `display_name`
- safe capability values
- source URLs only if public documentation URLs

It must not include API keys, raw base URLs for private endpoints, user display names, local provider names, or probe request/response bodies.

### 11.4 Failed Probe Evidence

Failed probes are publishable when sanitized. They should preserve:

- route identity;
- provider model ID;
- method/request mapper candidate;
- high-level reason code such as `unauthorized`, `rate_limited`, `timeout`, `unsupported_method`, `provider_error`.

They must not preserve raw provider error text unless the text passes the secret scanner and account-ID scanner. Default behavior is to store normalized reason code only.

## 12. API Adjustments

Existing endpoints remain but semantics tighten:

```http
POST /api/llm/catalog/repository/ensure
```

Returns:

```json
{
  "status": "success",
  "owner": "sevenx",
  "repo": "studio-llm-model-catalog",
  "html_url": "https://github.com/sevenx/studio-llm-model-catalog",
  "raw_url": "https://raw.githubusercontent.com/sevenx/studio-llm-model-catalog/main/llm_import_drafts.json",
  "catalog_path": "llm_import_drafts.json",
  "branch": "main",
  "repository_created": true,
  "catalog_created": true
}
```

```http
POST /api/llm/catalog/sync
```

Returns:

```json
{
  "status": "success",
  "source_url": "...",
  "fetched_at": "...",
  "route_candidates_count": 0,
  "evidence_records_count": 0,
  "new_records_count": 0
}
```

```http
POST /api/llm/catalog/share
```

Returns sanitized publish preview:

```json
{
  "status": "success",
  "publishable_records_count": 0,
  "excluded_records_count": 0,
  "excluded_reasons": {},
  "catalog_patch": {},
  "export_instructions": "Open a PR that updates llm_import_drafts.json"
}
```

## 13. Documentation Corrections

Docs must say:

- remote GitHub catalog repository is the shared source;
- local evidence file is cache/private pending state;
- General `Remote Model Catalog` controls automatic reads and defaults on;
- custom/third-party persisted route identity is derived from canonical URL + protocol, not random endpoint ID;
- current `probe_import_draft` is not a real worker until implemented;
- API Keys route tags render `ui_state`;
- blue means historical real success;
- inferred candidates and provider-list candidates are not "Previously Connected".

## 14. Testing Strategy

Tests must cover:

- route slug determinism and collision suffix;
- official route IDs match across independent simulated stores;
- custom random legacy endpoint IDs migrate to one URL-derived stable route ID;
- public export uses the same stable route ID as active credentials;
- remote sync validates a real `studio-evidence-library` payload;
- 404 remote sync reports a meaningful error;
- sanitized share excludes secrets, random custom identities, and private raw URLs;
- `probe-verified` evidence produces `historical_ready`;
- `provider-list-observed` evidence does not produce `historical_ready`;
- API Keys route chip uses `ui_state`.
