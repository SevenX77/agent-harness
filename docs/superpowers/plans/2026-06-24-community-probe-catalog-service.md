# Community Probe Catalog Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first implementation slice for phase-2 Community Probe Catalog: reusable upload sanitization/contracts plus a Studio local preview endpoint, without remote upload or MVP1 behavior changes.

**Architecture:** Gateway owns storage-agnostic community upload DTOs, endpoint privacy classification, endpoint fingerprinting, and evidence sanitization. Studio backend owns local evidence loading, credentials lookup, preview assembly, and an additive read-only preview endpoint. The slice deliberately stops before hosted ingestion, upload retry queues, artifact sync, or any mutation of active credentials.

**Tech Stack:** Python 3.11, Pydantic v2, FastAPI router tests, existing `ProviderEndpoint` / `EvidenceRecord` / `ProviderImportDraft` schemas, `uv run pytest`.

## Global Constraints

- Do not restore Import Draft as a product feature; `ProviderImportDraft` remains a legacy storage container only.
- Do not change MVP1 local catalog behavior: `/catalog/sync` remains read-only suggestion sync and `/catalog/share` remains `local_export_only`.
- No remote evidence may write active `ready`, `route.status="verified"`, API keys, `credential_ref`, roles, or model profiles.
- Do not upload or preview as uploadable: API keys, `credential_ref`, local paths, raw prompt/input/output, user account/org info, raw request bodies, raw response bodies, or private endpoint originals.
- `provider-list-observed` is not connectivity evidence and cannot produce `historical_ready`.
- Follow TDD: write the failing test, verify it fails, then implement.

---

### Task 1: Add Gateway Community Catalog Sanitization Contracts

**Files:**
- Create: `packages/graph-agent-gateway/src/graph_agent_gateway/community_catalog.py`
- Test: `packages/graph-agent-gateway/tests/test_community_catalog.py`

**Interfaces:**
- Consumes: `ProviderEndpoint`, `EvidenceRecord`, `CapabilityValue`, `canonicalize_base_url`.
- Produces:
  - `EndpointShareClass = Literal["public_known", "fingerprint_only", "local_only"]`
  - `CommunityUploadRecord`
  - `CommunityUploadCandidate`
  - `classify_endpoint_for_community_upload(endpoint, public_base_url_hosts=frozenset()) -> EndpointShareDecision`
  - `prepare_community_upload_record(record, endpoint, public_base_url_hosts=frozenset()) -> CommunityUploadCandidate`

- [ ] **Step 1: Write the failing gateway tests**

Create `packages/graph-agent-gateway/tests/test_community_catalog.py` with tests that assert:

```python
from __future__ import annotations

from pydantic import SecretStr

from graph_agent_gateway.community_catalog import (
    classify_endpoint_for_community_upload,
    prepare_community_upload_record,
)
from graph_agent_gateway.registry.schema import EvidenceRecord, ProviderEndpoint


def _endpoint(base_url: str, endpoint_id: str = "openai-direct") -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id=endpoint_id,
        provider_id="openai",
        provider_kind="official",
        protocol="openai_compatible",
        base_url=base_url,
        api_key=SecretStr("sk-test-secret"),
        credential_ref="endpoint:openai-direct",
    )


def test_private_endpoint_is_local_only_and_not_uploadable() -> None:
    endpoint = _endpoint("http://127.0.0.1:8000/v1")
    evidence = EvidenceRecord(
        evidence_id="ev-local",
        evidence_type="probe",
        trust_state="probe-verified",
        endpoint_id="openai-direct",
        provider_id="openai",
        provider_model_id="gpt-4.1",
        method_id="chat_completions",
        request_mapper_id="openai_chat_completions",
        probe_status="ok",
    )

    decision = classify_endpoint_for_community_upload(endpoint)
    candidate = prepare_community_upload_record(evidence, endpoint)

    assert decision.share_class == "local_only"
    assert "private_endpoint" in decision.reasons
    assert candidate.status == "blocked"
    assert candidate.record is None
    assert "private_endpoint" in candidate.reasons


def test_public_probe_record_omits_secrets_and_keeps_safe_probe_summary() -> None:
    endpoint = _endpoint("https://api.openai.com/v1")
    evidence = EvidenceRecord(
        evidence_id="ev-public",
        evidence_type="probe",
        trust_state="probe-verified",
        observed_at="2026-06-24T00:00:00Z",
        endpoint_id="openai-direct",
        provider_id="openai",
        provider_model_id="gpt-4.1",
        method_id="chat_completions",
        request_mapper_id="openai_chat_completions",
        probe_status="ok",
        successful_probe={"latency_ms": 640, "status": "ok"},
        metadata={"credential_ref": "endpoint:openai-direct", "safe": "kept"},
    )

    candidate = prepare_community_upload_record(
        evidence,
        endpoint,
        public_base_url_hosts=frozenset({"api.openai.com"}),
    )

    assert candidate.status == "accepted"
    assert candidate.record is not None
    payload = candidate.record.model_dump(mode="json")
    assert payload["endpoint"]["base_url_share_class"] == "public_known"
    assert payload["endpoint"]["normalized_public_base_url"] == "https://api.openai.com/v1"
    assert payload["endpoint"]["endpoint_fingerprint"].startswith("sha256:")
    assert payload["local_evidence_ref"].startswith("sha256:")
    assert payload["probe"]["latency_bucket_ms"] == "500-1000"
    assert "sk-test-secret" not in str(payload)
    assert "credential_ref" not in str(payload)
    assert "ev-public" not in str(payload)
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest packages/graph-agent-gateway/tests/test_community_catalog.py -q`

Expected: FAIL because `graph_agent_gateway.community_catalog` does not exist.

- [ ] **Step 3: Implement minimal gateway module**

Create `community_catalog.py` with Pydantic DTOs and these behaviors:

- Canonicalize endpoint base URL before fingerprinting.
- Detect private/local/unqualified hosts as `local_only`.
- Publish normalized base URL only for hosts passed in `public_base_url_hosts`.
- Use `fingerprint_only` for syntactically public but not allowlisted hosts.
- Hash `evidence_id` into `local_evidence_ref`.
- Drop unsafe metadata and reject records with forbidden raw values.
- Convert latency milliseconds to buckets: `<250`, `250-500`, `500-1000`, `1000-2500`, `2500-5000`, `5000+`.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest packages/graph-agent-gateway/tests/test_community_catalog.py -q`

Expected: PASS.

---

### Task 2: Add Studio Local Community Upload Preview Service

**Files:**
- Create: `apps/studio/backend/app/services/llm_community_catalog.py`
- Test: `apps/studio/backend/tests/services/test_llm_community_catalog.py`

**Interfaces:**
- Consumes: gateway `prepare_community_upload_record`, `LLMCredentialsFile`, `ProviderImportDraft`.
- Produces:
  - `build_community_catalog_upload_preview(library, credentials, public_base_url_hosts=frozenset()) -> CommunityCatalogUploadPreview`
  - `CommunityCatalogUploadPreview` with `sharing_mode="preview_only"`, `auto_upload_enabled=False`, `accepted_count`, `blocked_count`, `records`, `blocked`.

- [ ] **Step 1: Write the failing service tests**

Create `apps/studio/backend/tests/services/test_llm_community_catalog.py` asserting:

```python
from __future__ import annotations

from pydantic import SecretStr

from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint
from app.services.llm_community_catalog import build_community_catalog_upload_preview
from graph_agent_gateway.registry.schema import EvidenceRecord, ProviderImportDraft


def _credentials() -> LLMCredentialsFile:
    return LLMCredentialsFile(
        provider_endpoints={
            "openai-direct": ProviderEndpoint(
                endpoint_id="openai-direct",
                provider_id="openai",
                provider_kind="official",
                protocol="openai_compatible",
                base_url="https://api.openai.com/v1",
                api_key=SecretStr("sk-test-secret"),
                credential_ref="endpoint:openai-direct",
            ),
            "local-proxy": ProviderEndpoint(
                endpoint_id="local-proxy",
                provider_id="local",
                provider_kind="custom",
                protocol="openai_compatible",
                base_url="http://localhost:11434/v1",
                api_key=SecretStr("local-secret"),
                credential_ref="endpoint:local-proxy",
            ),
        }
    )


def test_preview_accepts_public_evidence_and_blocks_private_endpoint() -> None:
    library = ProviderImportDraft(
        draft_id="studio-evidence-library",
        source={"kind": "studio_evidence_library"},
        status="pending",
        evidence_records=[
            EvidenceRecord(
                evidence_id="ev-public",
                evidence_type="probe",
                trust_state="probe-verified",
                endpoint_id="openai-direct",
                provider_id="openai",
                provider_model_id="gpt-4.1",
                method_id="chat_completions",
                request_mapper_id="openai_chat_completions",
                probe_status="ok",
                successful_probe={"latency_ms": 640},
            ),
            EvidenceRecord(
                evidence_id="ev-private",
                evidence_type="probe",
                trust_state="probe-verified",
                endpoint_id="local-proxy",
                provider_id="local",
                provider_model_id="llama3",
                method_id="chat_completions",
                request_mapper_id="openai_chat_completions",
                probe_status="ok",
            ),
        ],
    )

    preview = build_community_catalog_upload_preview(
        library,
        _credentials(),
        public_base_url_hosts=frozenset({"api.openai.com"}),
    )

    assert preview.sharing_mode == "preview_only"
    assert preview.auto_upload_enabled is False
    assert preview.accepted_count == 1
    assert preview.blocked_count == 1
    assert preview.records[0].provider_id == "openai"
    assert preview.blocked[0].local_evidence_ref == "ev-private"
    assert "private_endpoint" in preview.blocked[0].reasons
    assert "sk-test-secret" not in preview.model_dump_json()
    assert "endpoint:openai-direct" not in preview.model_dump_json()


def test_preview_blocks_evidence_when_endpoint_is_missing() -> None:
    library = ProviderImportDraft(
        draft_id="studio-evidence-library",
        source={"kind": "studio_evidence_library"},
        status="pending",
        evidence_records=[
            EvidenceRecord(
                evidence_id="ev-missing",
                evidence_type="probe",
                trust_state="probe-failed",
                endpoint_id="missing-endpoint",
                provider_id="openai",
                provider_model_id="gpt-4.1",
                probe_status="timeout",
            )
        ],
    )

    preview = build_community_catalog_upload_preview(library, _credentials())

    assert preview.accepted_count == 0
    assert preview.blocked_count == 1
    assert preview.blocked[0].local_evidence_ref == "ev-missing"
    assert "missing_endpoint" in preview.blocked[0].reasons
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/studio/backend/tests/services/test_llm_community_catalog.py -q`

Expected: FAIL because `app.services.llm_community_catalog` does not exist.

- [ ] **Step 3: Implement minimal preview service**

Create the service and keep it side-effect-free. It must not save credentials,
write catalog files, enqueue uploads, or call a remote service.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest apps/studio/backend/tests/services/test_llm_community_catalog.py -q`

Expected: PASS.

---

### Task 3: Add Read-Only Preview Endpoint

**Files:**
- Modify: `apps/studio/backend/app/routers/llm.py`
- Test: `apps/studio/backend/tests/routers/test_llm_registry_api.py`

**Interfaces:**
- Consumes: `load_evidence_library`, `load_credentials`, `build_community_catalog_upload_preview`.
- Produces: `GET /api/llm/catalog/community/preview`.

- [ ] **Step 1: Write the failing router test**

Append a test near existing catalog tests:

```python
def test_community_catalog_preview_endpoint_is_preview_only(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    response = client.get("/api/llm/catalog/community/preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sharing_mode"] == "preview_only"
    assert payload["auto_upload_enabled"] is False
    assert "records" in payload
    assert "blocked" in payload
    assert "sk-" not in response.text
    assert "credential_ref" not in response.text
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/studio/backend/tests/routers/test_llm_registry_api.py::test_community_catalog_preview_endpoint_is_preview_only -q`

Expected: FAIL with 404.

- [ ] **Step 3: Implement minimal endpoint**

Add imports and:

```python
@router.get("/catalog/community/preview")
async def preview_community_catalog_upload() -> dict[str, Any]:
    library = load_evidence_library()
    credentials = load_credentials()
    preview = build_community_catalog_upload_preview(library, credentials)
    return preview.model_dump(mode="json")
```

Do not add an upload endpoint in this task.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest apps/studio/backend/tests/routers/test_llm_registry_api.py::test_community_catalog_preview_endpoint_is_preview_only -q`

Expected: PASS.

---

### Task 4: Carry Design Documentation into the Implementation Branch

**Files:**
- Create: `docs/development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md`
- Modify: `docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md`
- Modify: `docs/graph-agent-gateway/mvp1/DESIGN_UNITS_INDEX.md`

**Interfaces:**
- Consumes: phase-2 design created in the main workspace.
- Produces: a branch-local design and MVP1 alignment pointer.

- [ ] **Step 1: Apply the existing design/alignment patch**

Use the uncommitted design from the main workspace as the source of truth, or recreate the same file content if the main workspace patch is unavailable.

- [ ] **Step 2: Verify documentation references**

Run: `rg -n 'COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN|阶段二托管|Community Probe Knowledge' docs/development docs/graph-agent-gateway/mvp1`

Expected: the design doc exists, the 08 alignment links to it, and the design unit index references it.

---

### Task 5: Focused Verification

**Files:**
- No new files.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: clean focused test evidence.

- [ ] **Step 1: Run gateway focused tests**

Run: `uv run pytest packages/graph-agent-gateway/tests/test_community_catalog.py packages/graph-agent-gateway/tests/test_import_draft_store.py -q`

Expected: PASS.

- [ ] **Step 2: Run backend focused tests**

Run: `uv run pytest apps/studio/backend/tests/services/test_llm_community_catalog.py apps/studio/backend/tests/routers/test_llm_registry_api.py::test_community_catalog_preview_endpoint_is_preview_only apps/studio/backend/tests/routers/test_llm_registry_api.py::test_share_catalog_endpoint -q`

Expected: PASS.

- [ ] **Step 3: Run lint on changed Python files**

Run: `uv run ruff check packages/graph-agent-gateway/src/graph_agent_gateway/community_catalog.py packages/graph-agent-gateway/tests/test_community_catalog.py apps/studio/backend/app/services/llm_community_catalog.py apps/studio/backend/tests/services/test_llm_community_catalog.py apps/studio/backend/app/routers/llm.py apps/studio/backend/tests/routers/test_llm_registry_api.py`

Expected: PASS.
