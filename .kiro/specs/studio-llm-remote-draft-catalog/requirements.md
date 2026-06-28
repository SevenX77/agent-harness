---
spec: studio-llm-remote-draft-catalog
status: Draft
date: 2026-06-20
linked_specs:
  - llm-provider-intelligence-v2
  - studio-llm-gateway-redesign
linked_docs:
  - docs/studio/mvp1/01_workflows/00_settings-ux-spec.md
  - docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md
  - docs/development/FRONTEND_UI_SPEC.md
---

# Requirements - Studio LLM Remote Draft Catalog

## 1. Problem

MVP1 defines draft/evidence as the historical knowledge source for provider routes, model capabilities, successful probes, and failed probes. Current implementation stores this knowledge in the local Studio app-support file and points at a default GitHub raw URL that does not currently exist.

This makes blue `historical_ready` labels unreliable as a product signal:

- the default remote catalog cannot be fetched;
- local evidence differs per terminal;
- custom provider route IDs currently inherit random endpoint IDs, so persisted route IDs are not yet suitable as the shared catalog identity;
- API Keys still has mixed old `status=probe-verified` and new `ui_state=historical_ready` semantics;
- docs disagree on whether draft probing has actually landed.

## 2. Product Decision

The shared draft/evidence catalog must live on GitHub remote, not as a local-only truth source.

Local files may exist only as:

- a cache of the last fetched remote catalog;
- a pending writeback/export queue;
- active private credentials and private runtime state.

Local cache must never be described or treated as the canonical shared draft catalog.

## 3. Terminology

- **Remote catalog**: the canonical GitHub JSON file for public route candidates and public evidence.
- **Evidence library**: the `ProviderImportDraft` with `draft_id = "studio-evidence-library"`.
- **Route candidate**: advisory candidate metadata for one provider route.
- **Stable endpoint ID**: persisted endpoint identity derived from official provider mapping or canonical provider URL + protocol.
- **Stable route ID**: persisted route identity shared by local active credentials and remote GitHub catalog.
- **Probe evidence**: append-only evidence record from real model or endpoint probing.
- **Blue / historical_ready**: route has historical real probe success but is not currently live `verified`.
- **Green / ready**: route is currently live verified.

## 4. Route Identity Requirements

### REQ-01: route_id format remains deterministic for active routes

An active `route_id` must continue to have this shape:

```text
<endpoint_id>:<route_slug>
```

Both parts must match `[a-z0-9][a-z0-9._-]*`.

### REQ-02: route_slug generation must remain stable

For provider model IDs discovered from provider APIs:

- lowercase;
- replace `/` with `.`;
- replace `_` with `-`;
- replace other unsafe characters with `-`;
- collapse repeated `-`;
- preserve `.` where safe;
- keep the existing Claude version normalization, for example `claude-sonnet-4-6` -> `claude-sonnet-4.6`.

If two different `provider_model_id` values map to the same route slug under one endpoint, the backend must append a deterministic hash suffix derived from `endpoint_id:provider_model_id`.

### REQ-03: route_id must become the unified local and remote identity

The same provider model must produce the same persisted `route_id` across terminals when protocol and canonical Base URL are the same.

Official endpoints such as `openai-official`, `anthropic-official`, `gemini-official`, `deepseek-official`, and `ark-official` are stable and may be shared through the remote catalog.

Current user-created custom providers use `custom-<randomUUID>` endpoint IDs, so the same provider/model on two terminals does not automatically produce the same persisted `route_id`. This must be fixed by replacing random saved endpoint IDs with deterministic endpoint IDs once Base URL and protocol are known.

### REQ-04: custom/third-party endpoint_id must be URL-derived

The persisted `endpoint_id` for custom/third-party endpoints must be derived from stable endpoint facts:

```text
endpoint_id = hash_or_slug(protocol + "|" + canonical_base_url)
route_id = endpoint_id + ":" + route_slug(provider_model_id)
```

`canonical_base_url` must be produced by the shared gateway base URL canonicalizer before `endpoint_id` is computed. The identity must not include API key, display name, random local ID, or local file path.

### REQ-05: random custom IDs are temporary only

A random UI ID may exist only before an endpoint is saved and canonicalized. Persisted credentials must use stable endpoint IDs wherever Base URL and protocol are known.

Existing local `custom-<uuid>` endpoints must be migrated immediately by rewriting:

- provider endpoint keys;
- provider route IDs;
- role fallback chains;
- model profiles;
- model bundles;
- health/test-result references;
- evidence references where they point at local route IDs.

Only the one-shot migration tool may read old random IDs as input. Runtime business logic, projection, sync, share/export, and UI rendering must not match or branch on old random IDs after migration. If old IDs remain after migration validation, startup must fail with a migration error instead of silently running in compatibility mode.

### REQ-06: active routes must retain enough source metadata for audit

Every active `ProviderEndpoint` or `ProviderRoute` created from API Keys testing or draft apply must carry enough metadata to explain its stable identity:

- protocol;
- canonical base URL or safe URL hash;
- stable endpoint ID derivation version;
- provider model ID;
- route slug.

Registry projection must match remote evidence by the same stable `route_id` used in active credentials. It must not contain legacy random route matching logic.

### REQ-07: new custom providers must stop using random persisted endpoint IDs

For newly created custom providers, once Base URL and protocol are known, the backend should prefer a deterministic endpoint ID derived from canonical URL + protocol. A random temporary UI ID may exist before the endpoint is saved, but saved active credentials should not depend on `custom-<randomUUID>` if a stable endpoint key can be computed.

Existing local `custom-<uuid>` endpoints must be rewritten as part of this feature. Metadata-only compatibility and old-id fallback are not allowed.

### REQ-08: public/private catalog policy is based on URL sensitivity, not customness

The public remote catalog may contain:

- official provider endpoint IDs;
- curated public third-party endpoint IDs with stable documented names, for example `openrouter-prod` if accepted as public catalog identity;
- URL-derived stable endpoint IDs for public custom/third-party base URLs;
- route candidates and evidence that have been sanitized for public sharing.

The public remote catalog must not contain:

- random local `custom-<uuid>` endpoint IDs as persisted or remote identity;
- API keys;
- private base URLs;
- private organization IDs;
- raw request/response bodies;
- local machine paths;
- provider error text that may include secrets or account identifiers.

### REQ-09: private provider URLs require a private remote catalog or hashed identity

If users want remote draft behavior for private providers, it must use an explicitly configured private catalog URL/repository, or a hashed URL identity that never exposes the private host/path. The public catalog must not publish private raw URLs.

## 5. Remote Catalog Requirements

### REQ-10: GitHub catalog repository exists

The canonical shared catalog must live in a dedicated GitHub repository owned by the configured GitHub account, not in the local app-support directory and not in the main `agent-harness` source repo by default.

MVP1 default repository name:

```text
studio-llm-model-catalog
```

The backend must expose an API that can create or confirm this repository for the authenticated GitHub user:

```http
POST /api/llm/catalog/repository/ensure
```

This API must use GitHub REST `POST /user/repos` when the repository does not exist. The backend must not require the frontend to call GitHub directly.

### REQ-11: GitHub catalog file exists

The remote repository must contain a canonical catalog JSON file at the path used by the backend default URL:

```text
llm_import_drafts.json
```

The default raw URL must resolve successfully from GitHub `main` once the repository is initialized.

### REQ-12: catalog schema uses ProviderImportDraft

The remote file must use this top-level shape:

```json
{
  "drafts": {
    "studio-evidence-library": {
      "draft_id": "studio-evidence-library",
      "source": { "kind": "studio_evidence_library", "location": "github" },
      "status": "pending",
      "route_candidates": {},
      "evidence_records": []
    }
  }
}
```

### REQ-13: pulling remote catalog must not require local evidence

`POST /api/llm/catalog/sync` must fetch the remote GitHub catalog and project it into the backend response even when local app-support cache is absent or stale.

### REQ-14: local cache is optional and subordinate

The backend may cache the fetched remote catalog locally for performance and offline startup, but the cache must record remote metadata such as source URL, fetched commit or ETag, and fetched time. UI and docs must call it a cache, not the source of truth.

### REQ-15: remote evidence is advisory, not green

Remote evidence must not set `route.status = "verified"` in active credentials. It may only contribute to advisory state such as `historical_ready` when the route has matching `probe-verified` evidence and endpoint credentials are present.

### REQ-16: remote model catalog reading is user-configurable

Global Studio settings must include:

```json
{
  "remote_model_catalog_enabled": true
}
```

The setting defaults to `true` for new and existing settings files. When disabled, Studio must not automatically fetch remote model catalog/draft/evidence information during Settings/API Keys/LLM Roles load. Manual catalog management APIs may still be called explicitly.

## 6. Writeback Requirements

### REQ-17: successful and failed probes write evidence

Every real route/model probe must append evidence:

- success: `evidence_type = "probe"`, `trust_state = "probe-verified"`;
- failure: `evidence_type = "probe"`, `trust_state = "probe-failed"`.

Failures are historical knowledge and must not be dropped.

### REQ-18: model-list observations write route candidates

Provider model-list calls must write `model_list_observation` evidence and route candidates, but this does not mean the route previously connected.

### REQ-19: writeback to GitHub must be sanitized

Writeback must export only sanitized records. Public GitHub writeback may include custom/third-party records only after their persisted route IDs are stable and URL-derived, and the URL is public-safe. Private records require an explicit private catalog target or hashed identity policy.

### REQ-20: GitHub writeback uses PR flow

MVP1 writeback should create a catalog patch or PR payload. Automatic direct push to main is forbidden. If a GitHub token is configured later, it may create a branch and draft PR, but the default safe path is patch/export + human review.

### REQ-20a: public catalog reads do not require GitHub token

The default remote catalog repository is public. Studio must read it through the public raw GitHub URL without requiring or sending a GitHub token. GitHub authentication is only required for repository creation, file initialization, or future PR/writeback flows.

### REQ-21: share endpoint must not leak local evidence

The existing share behavior that returns every local `probe-verified` record is not acceptable as product behavior. It must filter, sanitize, and label what is safe to publish.

### REQ-21a: public URL safety is explicit and testable

The public catalog may include URL-derived stable endpoint IDs only when the endpoint URL is public-safe. Public-safe means:

- host is not localhost or loopback;
- host is not private RFC1918, link-local, carrier NAT, or unique-local IPv6;
- host is not a bare internal hostname without a public suffix;
- URL does not include username/password, query, fragment, tenant IDs, workspace IDs, or local paths;
- provider-specific path is generic API surface only, for example `/v1`, `/api`, `/api/v1`.

If public-safety cannot be proven, the record must be excluded from public writeback with an explicit exclusion reason.

### REQ-21b: writeback produces deterministic catalog patches

Sanitized writeback must produce a deterministic patch or merged JSON payload:

- stable sorted object keys;
- deterministic evidence ordering by `observed_at`, then `evidence_id`;
- idempotent re-running does not duplicate evidence;
- conflicts are reported as review-required instead of silently overwriting remote evidence.

### REQ-21c: GitHub writeback must use branch or PR, not main

When GitHub write credentials are configured, Studio may create a branch and draft PR against the catalog repository. It must not push directly to `main`. The returned response must include branch name, commit SHA, PR URL when created, and all excluded records.

## 7. UI State Requirements

### REQ-22: frontend consumes backend 6-state projection

API Keys route tags, LLM Roles available route tags, and Copilot route status must consume backend `ui_state` and not independently infer route truth.

### REQ-23: blue means historical real success

`historical_ready` / blue means real historical success from `probe-verified` evidence. Provider-list/doc/draft inferred candidates may be shown as candidates, but they must not be labeled "Previously Connected" unless they have real probe success evidence.

### REQ-24: Settings General exposes the remote catalog switch

The General settings page must render a `Remote Model Catalog` switch using the local shadcn/Radix `Switch` wrapper. The switch must:

- be on by default;
- auto-save through the existing `AppSettings` debounced save flow;
- use localized English and Simplified Chinese copy;
- not hydrate API keys or perform provider tests;
- only control automatic remote catalog reads.

### REQ-25: docs must be corrected

The MVP1 design docs, gateway alignment doc, and frontend UI spec must agree on:

- remote GitHub catalog as shared draft/evidence source;
- local cache is not canonical;
- `probe_import_draft` current implementation status;
- blue semantics;
- compact response migration away from old `status = "probe-verified"` as final UI truth.

### REQ-26: catalog population is separate from endpoint testing

Provider model-list observations may populate route candidates and capability candidates in the remote catalog, but they must remain visually distinct from historical successful probes. A user can see model-list candidates as available candidate routes, but they must not be labeled connected, previously connected, or ready unless matching probe evidence exists.

### REQ-27: migration health is observable

The hard stable-ID migration must expose a report that can be inspected by tests and logs:

- old endpoint ID -> new endpoint ID;
- old route ID -> new route ID;
- files/databases rewritten;
- validation failures;
- backup paths.

Startup and registry endpoints must surface migration failure clearly instead of producing partial settings UI state.

## 8. Acceptance Criteria

- GitHub raw URL for `llm_import_drafts.json` returns HTTP 200.
- A clean machine with no local `llm_import_drafts.json` can sync the remote catalog.
- Official provider route IDs are stable across machines for the same provider model IDs.
- Custom/third-party evidence can be grouped across machines because persisted `route_id` is derived from canonical URL + protocol + model ID.
- Random `custom-*` route IDs are not used as persisted or remote identity after migration.
- A route with endpoint verified + matching remote `probe-verified` evidence + local route not verified projects to `historical_ready`.
- A route with only `provider-list-observed` evidence does not show "Previously Connected".
- API Keys route chip color is driven by backend `ui_state`.
- Share/export output contains no API keys, private base URLs, raw request bodies, or random `custom-<uuid>` catalog identities by default.
- Public writeback excludes private/internal URLs with machine-readable exclusion reasons.
- A generated catalog patch can be applied twice without duplicating evidence.
