"""Runtime helpers for the verified community catalog read path."""

from __future__ import annotations

from typing import Any

from app.core.adapters.gateway import EvidenceRecord
from app.core.backends import get_backend_config
from app.services.community_catalog_sync import (
    DisposableCatalogCacheStore,
    make_httpx_fetcher,
    sync_verified_catalog,
)
from app.services.llm_paths import community_catalog_cache_path
from app.services.runtime_activity import record_runtime_activity

_MAX_LOGGED_ROUTES = 500


async def sync_verified_community_catalog_cache(*, trigger: str) -> dict[str, Any]:
    """Pull the signed community catalog into the disposable local cache."""
    cfg = get_backend_config()
    manifest_url = cfg.community_catalog_manifest_url.strip()
    public_key_hex = cfg.community_catalog_signing_pubkey.strip()
    if not manifest_url or not public_key_hex:
        record_runtime_activity(
            source_id="community_catalog_cache",
            action="sync_verified_catalog_skipped",
            message="Skipped verified community catalog sync because manifest URL or signing key is missing.",
            changes={"verified_sync_enabled": False, "trigger": trigger},
        )
        return {
            "status": "disabled",
            "verified_sync_enabled": False,
            "message": (
                "Verified community sync is not configured. Set a manifest URL and a signing "
                "public key to enable the verified read path."
            ),
        }

    cache_store = DisposableCatalogCacheStore(community_catalog_cache_path())
    prev_etag = cache_store.load().manifest_etag
    signature_url = f"{manifest_url}.sig"
    shard_base_url = manifest_url.rsplit("/", 1)[0] + "/"
    outcome = await sync_verified_catalog(
        manifest_url=manifest_url,
        signature_url=signature_url,
        shard_base_url=shard_base_url,
        public_key_hex=public_key_hex,
        client_protocol_major=cfg.community_protocol_major,
        cache_store=cache_store,
        fetch=make_httpx_fetcher(),
        prev_etag=prev_etag,
    )
    cached = cache_store.load()
    route_entries = _format_catalog_route_entries(cached.records)
    record_runtime_activity(
        source_id="community_catalog_cache",
        action="sync_verified_catalog",
        message="Downloaded or checked the verified community catalog cache.",
        changes={
            "trigger": trigger,
            "sync_status": outcome.status,
            "record_count": outcome.record_count,
            "cached_record_count": len(cached.records),
            "manifest_etag": outcome.manifest_etag,
            "protocol_major": outcome.protocol_major,
            "generated_at": cached.generated_at,
            "catalog_routes": route_entries,
            "catalog_routes_omitted": max(0, len(cached.records) - len(route_entries)),
            "promoted_route_count": 0,
        },
    )
    return {
        "status": "success",
        "verified_sync_enabled": True,
        "sync_status": outcome.status,
        "record_count": outcome.record_count,
        "cached_record_count": len(cached.records),
        "manifest_etag": outcome.manifest_etag,
        "protocol_major": outcome.protocol_major,
        "promoted_route_count": 0,
    }


def _format_catalog_route_entries(records: list[EvidenceRecord]) -> list[str]:
    entries: list[str] = []
    for record in records[:_MAX_LOGGED_ROUTES]:
        endpoint = record.metadata.get("normalized_public_base_url")
        if not isinstance(endpoint, str) or not endpoint:
            endpoint = record.metadata.get("route_key")
        if not isinstance(endpoint, str) or not endpoint:
            endpoint = "(unknown endpoint)"
        model_id = record.provider_model_id or record.model_id or "(unknown model)"
        capability = record.capability_family or record.model_type or "(unknown capability)"
        if record.method_id:
            entries.append(f"{endpoint} | {model_id} | {capability} | {record.method_id}")
        else:
            entries.append(f"{endpoint} | {model_id} | {capability}")
    return entries


__all__ = ["sync_verified_community_catalog_cache"]
