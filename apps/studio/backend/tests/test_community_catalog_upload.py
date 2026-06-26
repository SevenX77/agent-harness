"""Phase 2a R1/R3/R6: opt-in upload client.

- R1: upload only happens with an explicit ingestion-scoped token (opt-in); the
  body carries only sanitized records, never credentials or a repo write token.
- R3: every batch carries an Idempotency-Key so the gate can dedupe; the key is
  preserved across offline retries.
- R6: failures (network / 5xx) park the batch in an offline queue for retry.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from app.core.adapters.gateway import EvidenceRecord, ProviderImportDraft
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint
from app.services.community_catalog import build_upload_record
from app.services.community_catalog_upload import (
    EVIDENCE_BATCH_PATH,
    CommunityUploadClient,
    OfflineUploadQueue,
    UploadDeferred,
    batch_idempotency_key,
    collect_uploadable_uploads,
    community_upload_configured,
)

from tests.helpers_community_catalog import probe_record  # type: ignore[import-not-found]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _upload() -> object:
    return build_upload_record(probe_record(), base_url="https://api.openai.com/v1")


def _transport(captured: list[httpx.Request], *, status: int = 200, body: dict | None = None) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, json=body or {"accepted": 1, "rejected": 0, "receipt_token": "rcpt-1"})
    return httpx.MockTransport(handle)


def _client(transport: httpx.MockTransport, *, token: str = "ingestion-token-abc") -> CommunityUploadClient:
    return CommunityUploadClient(
        gate_url="https://gate.example.org",
        ingestion_token=token,
        transport=transport,
    )


@pytest.mark.anyio
async def test_upload_batch_posts_to_gate_with_token_and_idempotency_key() -> None:
    captured: list[httpx.Request] = []
    client = _client(_transport(captured))
    await client.upload_batch([_upload()], idempotency_key="batch-1")
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == EVIDENCE_BATCH_PATH
    assert request.headers["Authorization"] == "Bearer ingestion-token-abc"
    assert request.headers["Idempotency-Key"] == "batch-1"


@pytest.mark.anyio
async def test_upload_batch_returns_ack_with_receipt_token() -> None:
    captured: list[httpx.Request] = []
    client = _client(_transport(captured, body={"accepted": 2, "rejected": 1, "receipt_token": "rcpt-9"}))
    ack = await client.upload_batch([_upload()], idempotency_key="batch-1")
    assert ack.accepted == 2
    assert ack.rejected == 1
    assert ack.receipt_token == "rcpt-9"


@pytest.mark.anyio
async def test_upload_batch_body_carries_only_sanitized_record_fields() -> None:
    captured: list[httpx.Request] = []
    client = _client(_transport(captured))
    await client.upload_batch([_upload()], idempotency_key="batch-1")
    import json

    body = json.loads(captured[0].content)
    record = body["records"][0]
    # Sanitized upload fields only — no free-form blob keys may leak.
    for forbidden in ("metadata", "successful_probe", "probe_attempts", "scope", "api_key"):
        assert forbidden not in record


def test_client_refuses_empty_ingestion_token() -> None:
    with pytest.raises(ValueError):
        CommunityUploadClient(gate_url="https://gate.example.org", ingestion_token="   ")


@pytest.mark.anyio
async def test_upload_batch_enqueues_on_server_error(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []
    client = _client(_transport(captured, status=503))
    queue = OfflineUploadQueue(tmp_path / "queue.json")
    with pytest.raises(UploadDeferred):
        await client.upload_batch([_upload()], idempotency_key="batch-1", queue=queue)
    parked = queue.load()
    assert len(parked) == 1
    assert parked[0].idempotency_key == "batch-1"


@pytest.mark.anyio
async def test_upload_batch_enqueues_on_network_error(tmp_path: Path) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = _client(httpx.MockTransport(boom))
    queue = OfflineUploadQueue(tmp_path / "queue.json")
    with pytest.raises(UploadDeferred):
        await client.upload_batch([_upload()], idempotency_key="batch-2", queue=queue)
    assert len(queue.load()) == 1


@pytest.mark.anyio
async def test_drain_queue_retries_and_clears_on_success(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []
    # Park a batch first via a failing upload.
    fail_client = _client(_transport([], status=503))
    queue = OfflineUploadQueue(tmp_path / "queue.json")
    with pytest.raises(UploadDeferred):
        await fail_client.upload_batch([_upload()], idempotency_key="k1", queue=queue)

    ok_client = _client(_transport(captured))
    result = await ok_client.drain_queue(queue)
    assert result.succeeded == 1
    assert result.remaining == 0
    assert queue.load() == []
    # R3: the retried request reuses the original idempotency key.
    assert captured[0].headers["Idempotency-Key"] == "k1"


@pytest.mark.anyio
async def test_drain_queue_keeps_batch_on_repeated_failure(tmp_path: Path) -> None:
    queue = OfflineUploadQueue(tmp_path / "queue.json")
    fail_client = _client(_transport([], status=503))
    with pytest.raises(UploadDeferred):
        await fail_client.upload_batch([_upload()], idempotency_key="k1", queue=queue)
    result = await fail_client.drain_queue(queue)
    assert result.succeeded == 0
    assert result.remaining == 1
    assert len(queue.load()) == 1


# --- Phase 0 dormancy + Phase 3 service assembly --------------------------------


def test_community_upload_dormant_by_default() -> None:
    assert community_upload_configured(gate_url="", ingestion_token="", enabled=False) is False


def test_community_upload_requires_enabled_and_gate_and_token() -> None:
    assert community_upload_configured(gate_url="https://g", ingestion_token="t", enabled=False) is False
    assert community_upload_configured(gate_url="", ingestion_token="t", enabled=True) is False
    assert community_upload_configured(gate_url="https://g", ingestion_token="", enabled=True) is False
    assert community_upload_configured(gate_url="https://g", ingestion_token="t", enabled=True) is True


def _credentials_with_openai() -> LLMCredentialsFile:
    endpoint = ProviderEndpoint.model_validate(
        {
            "endpoint_id": "openai-main",
            "protocol": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "display_name": "OpenAI",
        }
    )
    return LLMCredentialsFile(provider_endpoints={"openai-main": endpoint})


def _library_with(records: list[EvidenceRecord]) -> ProviderImportDraft:
    return ProviderImportDraft.model_validate(
        {
            "draft_id": "evidence-library",
            "source": {"kind": "studio_evidence_library"},
            "status": "pending",
            "evidence_records": [r.model_dump(mode="json") for r in records],
        }
    )


def test_collect_uploadable_uploads_joins_base_url_from_credentials() -> None:
    record = probe_record(endpoint_id="openai-main", provider_id="openai", provider_model_id="gpt-4o")
    uploads = collect_uploadable_uploads(_library_with([record]), _credentials_with_openai())
    assert len(uploads) == 1
    assert uploads[0].normalized_public_base_url == "https://api.openai.com/v1"


def test_collect_uploadable_uploads_skips_non_uploadable() -> None:
    good = probe_record(evidence_id="e-good", endpoint_id="openai-main")
    bad = probe_record(evidence_id="e-bad", evidence_type="model_list_observation", trust_state="provider-list-observed")
    uploads = collect_uploadable_uploads(_library_with([good, bad]), _credentials_with_openai())
    assert len(uploads) == 1


def test_batch_idempotency_key_is_stable_for_same_records() -> None:
    record = probe_record(endpoint_id="openai-main", provider_id="openai", provider_model_id="gpt-4o")
    uploads = collect_uploadable_uploads(_library_with([record]), _credentials_with_openai())
    assert batch_idempotency_key(uploads) == batch_idempotency_key(uploads)


def test_batch_idempotency_key_differs_for_different_records() -> None:
    a = collect_uploadable_uploads(
        _library_with([probe_record(endpoint_id="openai-main", provider_model_id="gpt-4o")]),
        _credentials_with_openai(),
    )
    b = collect_uploadable_uploads(
        _library_with([probe_record(endpoint_id="openai-main", provider_model_id="gpt-3.5")]),
        _credentials_with_openai(),
    )
    assert batch_idempotency_key(a) != batch_idempotency_key(b)
