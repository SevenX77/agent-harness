"""Phase 2a R4: verified manifest/shard sync into a disposable cache.

Read path is fail-closed: a bad signature, a shard digest mismatch, or an
incompatible manifest protocol version aborts the sync BEFORE anything is
written, and verified records land only in a disposable cache that is isolated
from the local evidence store (never auto-applied to credentials).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from app.services.community_catalog import COMMUNITY_PROVENANCE
from app.services.community_catalog_sync import (
    CatalogManifest,
    DisposableCatalogCacheStore,
    FetchResult,
    ProtocolVersionRefused,
    ShardDigestMismatch,
    SignatureVerificationFailed,
    make_httpx_fetcher,
    sync_verified_catalog,
    verify_manifest_signature,
    verify_shard_digest,
)
from app.services.llm_paths import community_catalog_cache_path, probe_catalog_path
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
async def test_sync_writes_verified_records_to_disposable_cache(tmp_path: Path) -> None:
    priv, pub_hex = _keypair()
    world = _build_world(priv)
    cache = DisposableCatalogCacheStore(tmp_path / "cache.json")
    outcome = await sync_verified_catalog(
        manifest_url=MANIFEST_URL,
        signature_url=SIGNATURE_URL,
        shard_base_url=SHARD_BASE,
        public_key_hex=pub_hex,
        client_protocol_major=1,
        cache_store=cache,
        fetch=_fetcher(world),
    )
    assert outcome.status == "updated"
    assert outcome.record_count == 1
    stored = cache.load()
    assert len(stored.records) == 1
    assert stored.records[0].evidence_type == "probe"
    assert stored.records[0].metadata["provenance"] == COMMUNITY_PROVENANCE


@pytest.mark.anyio
async def test_sync_refuses_incompatible_protocol_and_writes_nothing(tmp_path: Path) -> None:
    priv, pub_hex = _keypair()
    world = _build_world(priv, protocol_major=2)
    cache = DisposableCatalogCacheStore(tmp_path / "cache.json")
    with pytest.raises(ProtocolVersionRefused):
        await sync_verified_catalog(
            manifest_url=MANIFEST_URL,
            signature_url=SIGNATURE_URL,
            shard_base_url=SHARD_BASE,
            public_key_hex=pub_hex,
            client_protocol_major=1,
            cache_store=cache,
            fetch=_fetcher(world),
        )
    assert cache.load().records == []


@pytest.mark.anyio
async def test_sync_fails_closed_on_bad_signature(tmp_path: Path) -> None:
    priv, pub_hex = _keypair()
    world = _build_world(priv, tamper_signature=True)
    cache = DisposableCatalogCacheStore(tmp_path / "cache.json")
    with pytest.raises(SignatureVerificationFailed):
        await sync_verified_catalog(
            manifest_url=MANIFEST_URL,
            signature_url=SIGNATURE_URL,
            shard_base_url=SHARD_BASE,
            public_key_hex=pub_hex,
            client_protocol_major=1,
            cache_store=cache,
            fetch=_fetcher(world),
        )
    assert cache.load().records == []


@pytest.mark.anyio
async def test_sync_fails_closed_on_shard_digest_mismatch(tmp_path: Path) -> None:
    priv, pub_hex = _keypair()
    world = _build_world(priv, tamper_shard=True)
    cache = DisposableCatalogCacheStore(tmp_path / "cache.json")
    with pytest.raises(ShardDigestMismatch):
        await sync_verified_catalog(
            manifest_url=MANIFEST_URL,
            signature_url=SIGNATURE_URL,
            shard_base_url=SHARD_BASE,
            public_key_hex=pub_hex,
            client_protocol_major=1,
            cache_store=cache,
            fetch=_fetcher(world),
        )
    assert cache.load().records == []


@pytest.mark.anyio
async def test_sync_skips_when_etag_unchanged(tmp_path: Path) -> None:
    priv, pub_hex = _keypair()
    fetched: list[str] = []
    world = _build_world(priv, manifest_etag='"same"')

    async def counting_fetch(url: str) -> FetchResult:
        fetched.append(url)
        return world[url]

    cache = DisposableCatalogCacheStore(tmp_path / "cache.json")
    outcome = await sync_verified_catalog(
        manifest_url=MANIFEST_URL,
        signature_url=SIGNATURE_URL,
        shard_base_url=SHARD_BASE,
        public_key_hex=pub_hex,
        client_protocol_major=1,
        cache_store=cache,
        fetch=counting_fetch,
        prev_etag='"same"',
    )
    assert outcome.status == "unchanged"
    # Only the manifest was fetched; no signature/shard download happened.
    assert fetched == [MANIFEST_URL]


def test_disposable_cache_path_is_isolated_from_evidence_store() -> None:
    assert community_catalog_cache_path() != probe_catalog_path()


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
