---
spec: studio-llm-remote-draft-catalog
status: Draft
date: 2026-06-20
---

# Research - Studio LLM Remote Draft Catalog

## 1. Current Branch and Runtime Context

The active Studio dev process was started from:

```text
/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased/apps/studio/tauri
```

Current investigated branch:

```text
feat/n0-settings-frontend
```

The active local app-support LLM files are:

```text
/Users/sevenx/Library/Application Support/AgentStudio/llm/llm_credentials.json
/Users/sevenx/Library/Application Support/AgentStudio/llm/llm_import_drafts.json
```

## 2. Current Route ID Generation

Observed code paths:

- `apps/studio/backend/app/services/llm_credentials.py`
- `apps/studio/backend/app/routers/llm.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/import_draft_store.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`

Current rule:

```text
route_id = endpoint_id + ":" + route_slug
```

`route_slug` is generated from `provider_model_id` by:

- trim;
- lowercase;
- replace `/` with `.`;
- replace `_` with `-`;
- replace unsafe characters with `-`;
- collapse repeated `-`;
- strip leading/trailing `-`;
- normalize Claude family versions such as `claude-sonnet-4-6` to `claude-sonnet-4.6`.

Endpoint test discovery has a deterministic collision suffix:

```text
if <endpoint_id>:<route_slug> exists for a different provider_model_id:
  route_id = <endpoint_id>:<route_slug>-<sha256(endpoint_id + ":" + provider_model_id)[0:8]>
```

The schema validator requires:

```text
route_id == endpoint_id + ":" + route_slug
```

## 3. Cross-Terminal Route ID Stability

Official endpoint IDs are stable:

- `openai-official`
- `anthropic-official`
- `gemini-official`
- `deepseek-official`
- `ark-official`

For the same official endpoint and same provider model ID, two terminals should produce the same route ID as long as they use the same code version.

User-created custom providers are currently not stable across terminals. The frontend add-provider flow creates:

```text
custom-<crypto.randomUUID()>
```

Because `endpoint_id` is part of active `route_id`, two terminals adding the same custom provider and same model will produce different active route IDs unless the endpoint ID is explicitly made stable.

This means the current random active `route_id` cannot be the remote catalog identity for custom providers. The target should not be two permanent identities; instead, persisted local route IDs and remote catalog route IDs should both be derived from the provider endpoint URL after protocol-aware canonicalization, plus protocol and provider model ID.

Target grouping key:

```text
canonical_base_url = canonicalize_base_url(base_url, protocol)
stable_endpoint_id = f(protocol, canonical_base_url)
stable_route_id = stable_endpoint_id + ":" + route_slug(provider_model_id)
```

The current code already has a shared base URL canonicalizer in `packages/graph-agent-gateway/src/graph_agent_gateway/registry/base_url.py`, so the implementation should build on that instead of using raw user input URLs.

## 4. Current Remote Catalog State

Current code default:

```text
https://raw.githubusercontent.com/SevenX77/agent-harness/main/llm_import_drafts.json
```

Observed result on 2026-06-20:

```text
HTTP 404
```

`git ls-tree` on both current HEAD and `origin/main` did not show a repository-root `llm_import_drafts.json`.

Conclusion: the code supports a remote catalog URL, but the default remote catalog is not actually published right now.

## 5. Current Local Evidence Library State

The local app-support file contains only:

```text
draft_id = studio-evidence-library
```

Observed counts:

```text
route_candidates = 1113
evidence_records = 65
probe-verified = 32
probe-failed = 7
provider-list-observed = 26
```

This is useful diagnostic evidence, but it is machine-local and must not be treated as the shared draft catalog.

## 6. Current Sync and Share Behavior

Current sync:

```http
POST /api/llm/catalog/sync
```

calls `sync_remote_evidence_library()`, which fetches the default URL or `STUDIO_CATALOG_URL`, validates `studio-evidence-library`, and merges it into the local store.

Current share:

```http
POST /api/llm/catalog/share
```

returns local `probe-verified` evidence records and tells the user to submit a PR manually.

Risk: current share behavior is too broad for product use because it can include custom/private endpoint evidence under random local route IDs. It needs URL-derived stable route IDs, public/private URL policy, and sanitization before becoming a real GitHub writeback path.

## 7. Current Blue State Behavior

Gateway projection allows `historical_ready` only when:

- endpoint is verified;
- route is not currently verified;
- matching evidence has `evidence_type = "probe"` and `trust_state = "probe-verified"`.

`provider-list-observed` evidence does not currently produce `historical_ready`.

This matches the stricter "blue = previously connected" meaning, but conflicts with some frontend spec wording that also describes provider-list/doc/draft inferred candidates as blue. The implementation plan chooses the stricter meaning to preserve user trust in the blue label.

## 8. Current Implementation Gaps

- Default GitHub catalog file is missing.
- Local app-support file is still effectively the only available evidence store.
- `probe_import_draft` is still a stub in current code.
- API Keys route chips still have mixed legacy `status = "probe-verified"` and newer `ui_state = "historical_ready"` semantics.
- Docs disagree on whether real draft probe worker has landed.
- Public/private catalog boundaries are not enforced.
- Custom/third-party evidence currently lacks a URL-derived stable route ID, so it cannot be reliably merged across terminals.
