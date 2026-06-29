"""Phase 2a R4 (+ Phase 5/9): verified manifest/shard sync RETURNS records, no cache.

Read path is fail-closed: a bad signature, a shard digest mismatch, or an
incompatible manifest protocol version aborts the sync BEFORE anything is returned.
Phase 5/9: there is no disposable cache anymore — verified records are returned for
the caller to merge straight into credentials route.evidence.
"""

from __future__ import annotations

import json

import httpx
import pytest
from app.services.community_catalog import COMMUNITY_PROVENANCE
from app.services.community_catalog_sync import (
    CatalogManifest,
    FetchResult,
    ProtocolVersionRefused,
    ShardDigestMismatch,
    SignatureVerificationFailed,
    make_httpx_fetcher,
    sync_verified_catalog,
    verify_manifest_signature,
    verify_shard_digest,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


MANIFEST_URL = "https://cdn.example.org/catalog/manifest.json"
SIGNATURE_URL = "https://cdn.example.org/catalog/manifest.json.sig"
SHARD_BASE = "https://cdn.example.org/catalog/"


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key().public_bytes_raw().hex()


def _wire_probe(evidence_id: str = "cat-1") -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "evidence_type": "probe_result",
        "trust_state": "probe-verified",
        "provider_id": "openai",
        "provider_model_id": "gpt-4o",
        "capability_family": "chat",
        "normalized_public_base_url": "https://api.openai.com/v1",
    }


def _build_world(
    priv: Ed25519PrivateKey,
    *,
    protocol_major: int = 1,
    tamper_signature: bool = False,
    tamper_shard: bool = False,
    manifest_etag: str = '"v1"',
) -> dict[str, FetchResult]:
    shard_body = json.dumps({"records": [_wire_probe()]}, sort_keys=True).encode("utf-8")
    if tamper_shard:
        shard_digest = "0" * 64
    else:
        import hashlib

        shard_digest = hashlib.sha256(shard_body).hexdigest()
    manifest_dict = {
        "protocol_major": protocol_major,
        "generated_at": "2026-06-26T00:00:00+00:00",
        "shards": [{"path": "shards/shard-0.json", "sha256": shard_digest, "record_count": 1}],
    }
    manifest_bytes = json.dumps(manifest_dict, sort_keys=True).encode("utf-8")
    signature = priv.sign(manifest_bytes)
    if tamper_signature:
        signature = bytes(b ^ 0xFF for b in signature)
    return {
        MANIFEST_URL: FetchResult(content=manifest_bytes, etag=manifest_etag),
        SIGNATURE_URL: FetchResult(content=signature.hex().encode("utf-8"), etag=None),
        SHARD_BASE + "shards/shard-0.json": FetchResult(content=shard_body, etag=None),
    }


def _fetcher(world: dict[str, FetchResult]):
    async def fetch(url: str) -> FetchResult:
        return world[url]

    return fetch


# --- pure verification -----------------------------------------------------------


def test_verify_shard_digest_matches() -> None:
    import hashlib

    body = b"hello"
    assert verify_shard_digest(body, hashlib.sha256(body).hexdigest()) is True


def test_verify_shard_digest_rejects_mismatch() -> None:
    assert verify_shard_digest(b"hello", "0" * 64) is False


def test_verify_manifest_signature_accepts_valid() -> None:
    priv, pub_hex = _keypair()
    payload = b'{"protocol_major":1}'
    sig_hex = priv.sign(payload).hex()
    assert verify_manifest_signature(manifest_bytes=payload, signature_hex=sig_hex, public_key_hex=pub_hex) is True


def test_verify_manifest_signature_rejects_tampered_payload() -> None:
    priv, pub_hex = _keypair()
    sig_hex = priv.sign(b"original").hex()
    assert verify_manifest_signature(manifest_bytes=b"tampered", signature_hex=sig_hex, public_key_hex=pub_hex) is False


def test_verify_manifest_signature_fails_closed_on_garbage() -> None:
    # Malformed key/sig must return False, never raise.
    assert verify_manifest_signature(manifest_bytes=b"x", signature_hex="zz", public_key_hex="nothex") is False


# --- disposable cache + orchestrator --------------------------------------------


@pytest.mark.anyio
async def test_sync_returns_verified_records_without_cache() -> None:
    priv, pub_hex = _keypair()
    world = _build_world(priv)
    outcome = await sync_verified_catalog(
        manifest_url=MANIFEST_URL,
        signature_url=SIGNATURE_URL,
        shard_base_url=SHARD_BASE,
        public_key_hex=pub_hex,
        client_protocol_major=1,
        fetch=_fetcher(world),
    )
    assert outcome.status == "updated"
    assert outcome.record_count == 1
    # Phase 5: records are RETURNED (no disk cache), with the FORMAL endpoint identity.
    assert len(outcome.records) == 1
    assert outcome.records[0].evidence_type == "probe"
    assert outcome.records[0].normalized_public_base_url == "https://api.openai.com/v1"
    assert outcome.records[0].metadata["provenance"] == COMMUNITY_PROVENANCE
    assert outcome.generated_at == "2026-06-26T00:00:00+00:00"


@pytest.mark.anyio
async def test_sync_refuses_incompatible_protocol() -> None:
    priv, pub_hex = _keypair()
    world = _build_world(priv, protocol_major=2)
    with pytest.raises(ProtocolVersionRefused):
        await sync_verified_catalog(
            manifest_url=MANIFEST_URL,
            signature_url=SIGNATURE_URL,
            shard_base_url=SHARD_BASE,
            public_key_hex=pub_hex,
            client_protocol_major=1,
            fetch=_fetcher(world),
        )


@pytest.mark.anyio
async def test_sync_fails_closed_on_bad_signature() -> None:
    priv, pub_hex = _keypair()
    world = _build_world(priv, tamper_signature=True)
    with pytest.raises(SignatureVerificationFailed):
        await sync_verified_catalog(
            manifest_url=MANIFEST_URL,
            signature_url=SIGNATURE_URL,
            shard_base_url=SHARD_BASE,
            public_key_hex=pub_hex,
            client_protocol_major=1,
            fetch=_fetcher(world),
        )


@pytest.mark.anyio
async def test_sync_fails_closed_on_shard_digest_mismatch() -> None:
    priv, pub_hex = _keypair()
    world = _build_world(priv, tamper_shard=True)
    with pytest.raises(ShardDigestMismatch):
        await sync_verified_catalog(
            manifest_url=MANIFEST_URL,
            signature_url=SIGNATURE_URL,
            shard_base_url=SHARD_BASE,
            public_key_hex=pub_hex,
            client_protocol_major=1,
            fetch=_fetcher(world),
        )


@pytest.mark.anyio
async def test_sync_unchanged_etag_still_fetches_and_returns_records() -> None:
    # Phase 5 (locked constraint): with no cache, a matching prev_etag may REPORT
    # status="unchanged", but the sync MUST still fetch + parse + return records, so a
    # route added after a prior sync can still go blue. etag never short-circuits records.
    priv, pub_hex = _keypair()
    fetched: list[str] = []
    world = _build_world(priv, manifest_etag='"same"')

    async def counting_fetch(url: str) -> FetchResult:
        fetched.append(url)
        return world[url]

    outcome = await sync_verified_catalog(
        manifest_url=MANIFEST_URL,
        signature_url=SIGNATURE_URL,
        shard_base_url=SHARD_BASE,
        public_key_hex=pub_hex,
        client_protocol_major=1,
        fetch=counting_fetch,
        prev_etag='"same"',
    )
    assert outcome.status == "unchanged"
    assert outcome.record_count == 1  # records STILL returned despite unchanged etag
    assert len(outcome.records) == 1
    # Every resource was fetched — no etag short-circuit.
    assert MANIFEST_URL in fetched
    assert SIGNATURE_URL in fetched
    assert SHARD_BASE + "shards/shard-0.json" in fetched


def test_manifest_model_tolerates_unknown_fields() -> None:
    manifest = CatalogManifest.model_validate(
        {"protocol_major": 1, "shards": [], "future_field": "ok"}
    )
    assert manifest.protocol_major == 1


@pytest.mark.anyio
async def test_make_httpx_fetcher_returns_content_and_etag() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"payload", headers={"ETag": '"abc"'})

    fetch = make_httpx_fetcher(transport=httpx.MockTransport(handle))
    result = await fetch("https://cdn.example.org/x")
    assert result.content == b"payload"
    assert result.etag == '"abc"'
