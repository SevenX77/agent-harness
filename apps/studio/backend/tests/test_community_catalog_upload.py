"""Phase 2a R1/R3 + Phase 6: opt-in upload client — clean open API, NO offline queue.

- R1: the request is a clean open API — the body carries only sanitized records,
  never a token, credentials, or a repo write key. All auth/abuse control is
  server-side (the gate rate-limits; it takes no client token).
- R3: every batch carries an Idempotency-Key so the gate can dedupe.
- Phase 6: there is NO local pending/offline queue. A failed upload raises
  ``CommunityUploadError`` and writes nothing locally; the next probe / contribute
  re-derives candidates from credentials and retries with the SAME content-derived
  key (remote idempotency), so dropping the local queue loses nothing.
"""

from __future__ import annotations

import json

import httpx
import pytest
from app.core.backends import BackendConfig, clear_backend_caches
from app.services.community_catalog import EvidenceUpload, build_upload_record
from app.services.community_catalog_upload import (
    EVIDENCE_BATCH_PATH,
    CommunityUploadClient,
    CommunityUploadError,
    batch_idempotency_key,
    community_upload_configured,
)

from tests.helpers_community_catalog import probe_record  # type: ignore[import-not-found]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _upload(*, provider_model_id: str = "gpt-4o") -> object:
    return build_upload_record(
        probe_record(endpoint_id="openai-main", provider_id="openai", provider_model_id=provider_model_id),
        base_url="https://api.openai.com/v1",
    )


def _transport(captured: list[httpx.Request], *, status: int = 200, body: dict | None = None) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, json=body or {"accepted": 1, "rejected": 0, "receipt_token": "rcpt-1"})
    return httpx.MockTransport(handle)


def _client(transport: httpx.MockTransport) -> CommunityUploadClient:
    return CommunityUploadClient(gate_url="https://gate.example.org", transport=transport)


@pytest.mark.anyio
async def test_upload_batch_posts_to_gate_with_idempotency_key_and_no_token() -> None:
    captured: list[httpx.Request] = []
    client = _client(_transport(captured))
    await client.upload_batch([_upload()], idempotency_key="batch-1")
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == EVIDENCE_BATCH_PATH
    assert request.headers["Idempotency-Key"] == "batch-1"
    # Clean open API: the client sends NO Authorization/token header at all.
    assert "Authorization" not in request.headers


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
    body = json.loads(captured[0].content)
    record = body["records"][0]
    # Sanitized upload fields only — no free-form blob keys may leak.
    for forbidden in ("metadata", "successful_probe", "probe_attempts", "scope", "api_key"):
        assert forbidden not in record


def test_client_refuses_empty_gate_url() -> None:
    with pytest.raises(ValueError):
        CommunityUploadClient(gate_url="   ")


# --- Phase 6: failure raises, NEVER queues to disk ------------------------------


@pytest.mark.anyio
async def test_upload_batch_raises_on_server_error_and_writes_nothing(tmp_path: object) -> None:
    # Phase 6: a 5xx raises CommunityUploadError — there is no offline queue and the
    # upload path writes no local pending state (tmp_path stays empty).
    client = _client(_transport([], status=503))
    with pytest.raises(CommunityUploadError):
        await client.upload_batch([_upload()], idempotency_key="batch-1")
    assert list(tmp_path.iterdir()) == []  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_upload_batch_raises_on_network_error(tmp_path: object) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = _client(httpx.MockTransport(boom))
    with pytest.raises(CommunityUploadError):
        await client.upload_batch([_upload()], idempotency_key="batch-2")
    assert list(tmp_path.iterdir()) == []  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_upload_batch_rejects_queue_keyword() -> None:
    # The offline-queue parameter is gone (Phase 6): passing it is a TypeError, proving
    # the persistent-retry path was removed, not merely left unused.
    client = _client(_transport([]))
    with pytest.raises(TypeError):
        await client.upload_batch([_upload()], idempotency_key="k", queue=object())  # type: ignore[call-arg]


# --- Phase 0 dormancy + config -------------------------------------------------


def test_community_upload_off_when_disabled_or_no_gate() -> None:
    assert community_upload_configured(gate_url="", enabled=False) is False
    assert community_upload_configured(gate_url="https://g", enabled=False) is False
    assert community_upload_configured(gate_url="", enabled=True) is False


def test_community_upload_active_with_enabled_and_gate() -> None:
    assert community_upload_configured(gate_url="https://g", enabled=True) is True


def test_backend_config_ships_community_catalog_on_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Zero-config: the stock build ships the whole community catalog ON. Write path
    # (baked gate URL + flag, NO token) and read path (baked manifest + signing key)
    # are all active out of the box. Clear the neutralized test env to read defaults.
    for var in (
        "STUDIO_COMMUNITY_UPLOAD_ENABLED",
        "STUDIO_COMMUNITY_GATE_URL",
        "STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY",
        "STUDIO_COMMUNITY_CATALOG_MANIFEST_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    clear_backend_caches()
    cfg = BackendConfig()
    assert cfg.community_upload_enabled is True
    assert cfg.community_gate_url.startswith("https://")
    assert cfg.community_catalog_manifest_url.startswith("https://")
    assert len(cfg.community_catalog_signing_pubkey) == 64
    # The API is clean/open — there is no ingestion-token field at all.
    assert not hasattr(cfg, "community_ingestion_token")
    assert (
        community_upload_configured(gate_url=cfg.community_gate_url, enabled=cfg.community_upload_enabled)
        is True
    )


# --- idempotency key (content-derived → stable across credential re-derivation) -


def test_batch_idempotency_key_is_stable_for_same_records() -> None:
    uploads = [_upload(provider_model_id="gpt-4o")]
    assert batch_idempotency_key(uploads) == batch_idempotency_key(uploads)


def test_batch_idempotency_key_differs_for_different_records() -> None:
    a = [_upload(provider_model_id="gpt-4o")]
    b = [_upload(provider_model_id="gpt-3.5")]
    assert batch_idempotency_key(a) != batch_idempotency_key(b)


# --- drift fix: key derives from the FULL sanitized payload, not a 4-tuple ------


def _eu(**overrides: object) -> EvidenceUpload:
    base: dict[str, object] = dict(
        evidence_type="probe_result",
        trust_state="probe-verified",
        provider_id="openai",
        normalized_public_base_url="https://api.openai.com/v1",
        endpoint_fingerprint="fp-1",
        route_key="fp-1:gpt-4o:chat_completions",
        provider_model_id="gpt-4o",
        model_id="gpt-4o",
        method_id="chat_completions",
        request_mapper_id="mapper-a",
        capability_family="chat",
        model_type="text",
        input_modalities=["text"],
        output_modalities=["text"],
        probe_status="ok",
        observed_at="2026-06-01T00:00:00Z",
    )
    base.update(overrides)
    return EvidenceUpload(**base)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_mapper_id", "mapper-b"),
        ("capability_family", "embedding"),
        ("model_type", "vision"),
        ("input_modalities", ["text", "image"]),
        ("output_modalities", ["text", "image"]),
        ("probe_status", "degraded"),
        ("normalized_public_base_url", "https://api.other.example/v1"),
    ],
)
def test_idempotency_key_changes_when_any_upload_semantic_field_changes(
    field: str, value: object
) -> None:
    # The key must reflect the FULL sanitized upload content, not a 4-tuple subset:
    # changing ANY upload-meaningful field changes the key, so the gate never wrongly
    # dedupes semantically different evidence (e.g. same endpoint+model+method but a
    # different request_mapper_id / capability / modalities / probe_status).
    assert batch_idempotency_key([_eu()]) != batch_idempotency_key([_eu(**{field: value})])


def test_idempotency_key_is_order_independent() -> None:
    a, b = _eu(provider_model_id="gpt-4o"), _eu(provider_model_id="gpt-3.5")
    assert batch_idempotency_key([a, b]) == batch_idempotency_key([b, a])


def test_idempotency_key_ignores_observed_at_timestamp() -> None:
    # No timestamps enter the key: re-observing the same evidence (newer observed_at)
    # stays idempotent at the gate.
    assert batch_idempotency_key([_eu(observed_at="2026-06-01T00:00:00Z")]) == batch_idempotency_key(
        [_eu(observed_at="2026-12-31T23:59:59Z")]
    )


def test_idempotency_key_is_stable_when_rederived_from_same_evidence() -> None:
    # Re-deriving the SAME candidates (as contribute does from credentials next time)
    # yields the SAME key — content idempotency is what lets Phase 6 drop the queue.
    rec = probe_record(endpoint_id="openai-main", provider_id="openai", provider_model_id="gpt-4o")
    first = [build_upload_record(rec, base_url="https://api.openai.com/v1")]
    second = [build_upload_record(rec, base_url="https://api.openai.com/v1")]
    assert batch_idempotency_key(first) == batch_idempotency_key(second)
