---
spec: community-probe-catalog-service-phase2a
status: Draft
date: 2026-06-26
linked_specs:
  - studio-llm-remote-draft-catalog
  - llm-provider-intelligence-v2
linked_docs:
  - docs/development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md
  - docs/development/COMMUNITY_CATALOG_SERVICE_HANDOFF_PROMPT.md
  - docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md
---

# Community Probe Catalog Service — Phase 2a Research

This spec implements the **Phase 2a free-tier starting shape** of the Community
Probe Knowledge Catalog Service. The full design (and the three-way review that
locked it) lives in
[`COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md`](../../../docs/development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md);
the post-MVP1 locked decisions are registered in the gateway MVP1 unit
[`08-orch-test-status-ssot/mvp1-alignment.md`](../../../docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md).
This spec does not re-derive the design — it slices the locked design into
implementable work, drawing the boundary between in-repo code and external infra.

## Current Code Baseline

The MVP1 local-first catalog already exists. Phase 2a builds on it, it does not
replace it.

- **Backend facade** — `apps/studio/backend/app/services/llm_probe_catalog.py`:
  `append_evidence_record`, `sync_remote_probe_catalog`, `DEFAULT_CATALOG_URL`.
- **Legacy storage / remote sync** —
  `apps/studio/backend/app/services/llm_import_drafts.py`:
  `sync_remote_evidence_library_with_metadata` pulls a **single
  `llm_probe_catalog.json`** from a raw URL and merges it into the local evidence
  library. No manifest, no shards, no signature, no ETag-diff.
- **HTTP endpoints** — `apps/studio/backend/app/routers/llm.py`:
  - `/catalog/sync` — pulls the single-file remote suggestion source.
  - `/catalog/share` — returns `sharing_mode="local_export_only"`,
    `auto_upload_enabled=False`; `evidence_records_to_share` filters
    `evidence_type == "probe"`.
  - `/catalog/repository/ensure` — creates/initializes a repo using the **user's
    own** configured GitHub token (`github_catalog.ensure_repository`); seeds an
    **empty** library. This is a user-owned repo helper, NOT a community ingestion
    path.
- **GitHub repo helper** — `apps/studio/backend/app/services/github_catalog.py`:
  `ensure_repository` raises if no token configured; `_catalog_seed` seeds empty.
- **Gateway data layer** —
  `packages/graph-agent-gateway/src/graph_agent_gateway/import_draft_store.py`:
  merges remote evidence/route candidates into the local evidence library (it is
  NOT a disposable cache today).
- **Gateway catalog kernel** —
  `packages/graph-agent-gateway/src/graph_agent_gateway/probe_catalog.py`:
  `ProbeCatalogStore`, `materialize_probe_catalog_candidates`.
- **Schema truth** —
  `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`:
  `EvidenceRecord`, `ProviderImportDraft`, `ProbeResult`; the probe evidence type
  is the string `"probe"`.

## Source Documents

- `COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md` — full design; "Phase 2a:
  GitHub-Native Free-Tier Starting Shape" + "Phase 2a Draft Decisions" are the
  authority for this spec.
- `COMMUNITY_CATALOG_SERVICE_HANDOFF_PROMPT.md` — Non-Goals (no Import Draft
  revival, no auto-apply to credentials, no client-held catalog-write token, no
  secret/private-host upload, `provider-list-observed` never → `historical_ready`).
- `08-orch-test-status-ssot/mvp1-alignment.md` — owning MVP1 unit; F3 Probe
  Knowledge Catalog; the registered phase-2 decisions.

## Design Conclusions (locked by three-way review)

1. Ingestion has exactly one shape: a **serverless gate** exposing
   `POST /v1/evidence/batches`. The client-triggered GitHub Action lane is
   **rejected** (client would hold a write/dispatch channel + forks the upload
   contract).
2. The gate **holds no catalog-repo write token**. It authenticates, rate-limits,
   re-validates redaction, and enqueues. The **scheduled publishing Action** is the
   only component with repo-write capability (minimal `permissions: contents: write`).
3. Endpoint identity privacy: allowlisted public providers publish plaintext
   normalized base URL + fingerprint; everything else is **dropped client-side
   before upload**; raw un-salted SHA-256 is never published; cross-user matching
   of non-allowlisted public hosts (if ever needed) uses a server-side peppered
   HMAC — deferred, not in 2a baseline.
4. The client read path is a **migration**: manifest → ETag diff → shard download
   → signature/digest verify (fail-closed) → disposable cache **separate** from
   the local evidence store.
5. Boundaries preserved: `/catalog/share` stays `local_export_only`; auto-upload
   is per-upload opt-in (phase 2, not a global flag); `/catalog/repository/ensure`
   is not reused as the community upload path.

## Implementation Slice Selected

Phase 2a spans two domains. The slice boundary:

- **In this repo (testable here):** the desktop/Studio client side —
  redaction-before-upload + allowlist drop, the opt-in upload client that calls the
  gate's `POST /v1/evidence/batches`, the new manifest/shard/verify sync path into a
  disposable cache, the `probe_result`↔`probe` schema mapping, and keeping
  `/catalog/share` + `/catalog/repository/ensure` boundaries intact.
- **External infra (specified here, built/tested out-of-repo):** the serverless
  gate (Cloudflare Worker free tier), the ingestion buffer (KV/queue), and the
  scheduled publishing GitHub Action. This spec defines their contracts and
  red-lines so the in-repo client targets a fixed interface; their own code +
  tests live in the service repo, not the test suites gated by this repo's CI.

This spec is **phase-2 / post-MVP1**: it is recorded now so implementation is
ready when prioritized; it does not change MVP1 local-first behavior.
