"""Runtime helpers for the verified community catalog read path."""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.adapters.gateway import UPLOADABLE_TRUST_STATE, EvidenceRecord, endpoint_host
from app.core.backends import get_backend_config, get_metadata
from app.models.llm_config import LLMCredentialsFile, RemoteCatalogSyncMarker
from app.services.community_catalog_sync import make_httpx_fetcher, sync_verified_catalog
from app.services.llm_credentials_evidence import merge_route_evidence
from app.services.runtime_activity import record_runtime_activity

_MAX_LOGGED_ROUTES = 500


def merge_community_evidence_into_credentials(
    credentials: LLMCredentialsFile,
    records: list[EvidenceRecord],
) -> int:
    """Merge probe-verified community evidence into EXISTING credential routes (Phase 5).

    The community catalog is a data carrier, not a parallel truth: each probe-verified
    record is matched to an existing route by endpoint host + ``provider_model_id`` and
    merged ONTO ``route.evidence`` via ``merge_route_evidence`` (community provenance
    preserved, so the UI projects blue but ``collect_uploadable`` never re-uploads it).
    It never creates endpoints/routes and never sets a route green. Mutates
    ``credentials`` in place; returns the number of routes whose evidence ACTUALLY
    changed (an unchanged re-sync returns 0, not the match-attempt count).
    """
    routes_by_key: dict[tuple[str, str], list[str]] = {}
    for route_id, route in credentials.provider_routes.items():
        endpoint = credentials.provider_endpoints.get(route.endpoint_id)
        if endpoint is None:
            continue
        host = endpoint_host(endpoint.base_url)
        if host is None:
            continue
        routes_by_key.setdefault((host, route.provider_model_id), []).append(route_id)

    updated = 0
    for record in records:
        if record.trust_state != UPLOADABLE_TRUST_STATE:  # probe-verified only
            continue
        model_id = record.provider_model_id or record.model_id
        published = record.normalized_public_base_url  # FORMAL field (Phase 5)
        if not model_id or not published:
            continue
        host = endpoint_host(published)
        if host is None:
            continue
        for route_id in routes_by_key.get((host, model_id), []):
            before = credentials.provider_routes[route_id]
            after = merge_route_evidence(before, record)
            # Count the ACTUAL changed-route count, not match attempts: ``merge_route_evidence``
            # dedups by content_hash, so a re-sync of the same catalog yields an identical
            # route → no change, not counted (keeps ``merged_route_count`` honest).
            if after != before:
                credentials.provider_routes[route_id] = after
                updated += 1
    return updated


def promote_community_evidence_into_credentials(
    *,
    community_records: list[EvidenceRecord],
    path: Path | None = None,
) -> int:
    """Load credentials, merge community evidence into matching routes (see
    :func:`merge_community_evidence_into_credentials`), persist once on change, and
    return the number of route merges. The single write door for community evidence."""
    from app.services.llm_credentials import (
        credentials_path,
        load_credentials,
        save_credentials,
    )

    target = path or credentials_path()
    credentials = load_credentials(target)
    updated = merge_community_evidence_into_credentials(credentials, community_records)
    if updated:
        save_credentials(credentials, target)
    return updated


async def merge_synced_catalog_into_created_routes(
    credentials: LLMCredentialsFile,
    *,
    created_route_ids: Collection[str],
    trigger: str,
) -> int:
    """J-01.I (批示轮三 R3-4): merge verified community evidence into the caller's
    IN-MEMORY credentials right after a Test/probe created new routes, so the SAME
    save that persists the routes also persists their community evidence — the
    write response already projects Previously-Connected blue, no restart needed.

    Phase 5 keeps no local cache of unmatched evidence, so the records for a route
    that did not exist at the last sync live only in the remote catalog — this is
    why the merge must re-fetch here instead of reading anything local. Gating
    mirrors :func:`sync_verified_community_catalog_into_credentials` (an explicit
    "declined" stops the read; a missing manifest URL / signing key keeps the
    whole read path dormant) — a second occurrence, kept inline per the
    three-strikes rule. Best-effort by design: this call enriches the caller's
    primary write, so a fetch/verify failure is logged as runtime activity and
    returns 0 — it must never fail the endpoint test that triggered it. Returns
    the number of routes whose evidence actually changed.
    """
    if not created_route_ids:
        return 0
    settings = await get_metadata().read_app_settings()
    if settings.community_sharing_choice == "declined":
        return 0
    cfg = get_backend_config()
    manifest_url = cfg.community_catalog_manifest_url.strip()
    public_key_hex = cfg.community_catalog_signing_pubkey.strip()
    if not manifest_url or not public_key_hex:
        return 0
    try:
        outcome = await sync_verified_catalog(
            manifest_url=manifest_url,
            signature_url=f"{manifest_url}.sig",
            shard_base_url=manifest_url.rsplit("/", 1)[0] + "/",
            public_key_hex=public_key_hex,
            client_protocol_major=cfg.community_protocol_major,
            fetch=make_httpx_fetcher(),
            prev_etag=(
                credentials.last_remote_catalog_sync.etag
                if credentials.last_remote_catalog_sync
                else None
            ),
        )
    except Exception as error:
        record_runtime_activity(
            source_id="llm_credentials",
            action="sync_verified_catalog_failed",
            message=(
                "Community catalog fetch after route creation failed; "
                "the write proceeds without community evidence."
            ),
            changes={
                "trigger": trigger,
                "error": str(error),
                "created_route_count": len(created_route_ids),
            },
        )
        return 0
    merged = merge_community_evidence_into_credentials(credentials, list(outcome.records))
    credentials.last_remote_catalog_sync = RemoteCatalogSyncMarker(
        etag=outcome.manifest_etag,
        generated_at=outcome.generated_at,
        last_synced_at=datetime.now(tz=UTC).isoformat(),
    )
    record_runtime_activity(
        source_id="llm_credentials",
        action="sync_verified_catalog",
        message="Merged verified community evidence in the same write that created new routes.",
        changes={
            "trigger": trigger,
            "created_route_count": len(created_route_ids),
            "merged_route_count": merged,
            "record_count": outcome.record_count,
        },
    )
    return merged


async def sync_verified_community_catalog_into_credentials(*, trigger: str) -> dict[str, Any]:
    """Pull the signed community catalog and merge verified evidence into credentials.

    Phase 5: there is no disposable cache anymore. Verified records are merged straight
    onto ``route.evidence`` (SSOT); only a tiny last-sync marker is persisted. All
    runtime-activity here is logged under the ``llm_credentials`` source — the single
    truth this sync reads-from and writes-to.

    Gated on ``AppSettings.community_sharing_choice``: only ``"declined"`` stops the
    read (the user explicitly asked for both reading and sharing to stop). ``"unset"``
    (the first-run consent dialog has not fired yet) still reads — the read side takes
    nothing from this machine, and refusing it would only make a fresh install worse
    for no consent reason (design: docs/studio/mvp1/01_workflows/00_settings.md §5).
    """
    settings = await get_metadata().read_app_settings()
    if settings.community_sharing_choice == "declined":
        record_runtime_activity(
            source_id="llm_credentials",
            action="sync_verified_catalog_skipped",
            message="Skipped verified community catalog sync because the user declined community sharing.",
            changes={"verified_sync_enabled": False, "trigger": trigger},
        )
        return {
            "status": "disabled",
            "verified_sync_enabled": False,
            "message": "Community sharing is off, so the verified catalog is not read.",
        }

    cfg = get_backend_config()
    manifest_url = cfg.community_catalog_manifest_url.strip()
    public_key_hex = cfg.community_catalog_signing_pubkey.strip()
    if not manifest_url or not public_key_hex:
        record_runtime_activity(
            source_id="llm_credentials",
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

    from app.services.llm_credentials import (
        credentials_path,
        load_credentials,
        save_credentials,
    )

    target = credentials_path()
    credentials = load_credentials(target)
    # etag is ONLY a status hint (R9.6/Phase 5): never skip the fetch, because we keep
    # no cache of unmatched evidence — a route added after a prior sync must still merge.
    prev_etag = (
        credentials.last_remote_catalog_sync.etag if credentials.last_remote_catalog_sync else None
    )
    signature_url = f"{manifest_url}.sig"
    shard_base_url = manifest_url.rsplit("/", 1)[0] + "/"
    outcome = await sync_verified_catalog(
        manifest_url=manifest_url,
        signature_url=signature_url,
        shard_base_url=shard_base_url,
        public_key_hex=public_key_hex,
        client_protocol_major=cfg.community_protocol_major,
        fetch=make_httpx_fetcher(),
        prev_etag=prev_etag,
    )

    # Phase 5: merge verified evidence DIRECTLY into credentials route.evidence (no disk
    # cache), then persist a tiny last-sync marker. One save.
    merged = merge_community_evidence_into_credentials(credentials, list(outcome.records))
    credentials.last_remote_catalog_sync = RemoteCatalogSyncMarker(
        etag=outcome.manifest_etag,
        generated_at=outcome.generated_at,
        last_synced_at=datetime.now(tz=UTC).isoformat(),
    )
    save_credentials(credentials, target)

    route_entries = _format_catalog_route_entries(list(outcome.records))
    record_runtime_activity(
        source_id="llm_credentials",
        action="sync_verified_catalog",
        message="Verified community catalog synced and merged into credentials route.evidence.",
        changes={
            "trigger": trigger,
            "sync_status": outcome.status,
            "record_count": outcome.record_count,
            "merged_route_count": merged,
            "manifest_etag": outcome.manifest_etag,
            "protocol_major": outcome.protocol_major,
            "generated_at": outcome.generated_at,
            "catalog_routes": route_entries,
            "catalog_routes_omitted": max(0, len(outcome.records) - len(route_entries)),
        },
    )
    return {
        "status": "success",
        "verified_sync_enabled": True,
        "sync_status": outcome.status,
        "record_count": outcome.record_count,
        "merged_route_count": merged,
        "manifest_etag": outcome.manifest_etag,
        "protocol_major": outcome.protocol_major,
    }


def _format_catalog_route_entries(records: list[EvidenceRecord]) -> list[str]:
    entries: list[str] = []
    for record in records[:_MAX_LOGGED_ROUTES]:
        endpoint = record.normalized_public_base_url
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


__all__ = [
    "merge_community_evidence_into_credentials",
    "promote_community_evidence_into_credentials",
    "sync_verified_community_catalog_into_credentials",
]
