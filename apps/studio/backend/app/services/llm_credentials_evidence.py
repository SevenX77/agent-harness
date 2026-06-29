"""Route-embedded evidence merge for Studio LLM credentials (SSOT).

The single writer of ``route.evidence``: it stamps ``content_hash``, dedups by
it, and keeps the newest ``observed_at``. Every Test/probe/sync/migration path
funnels evidence through here so dedup stays consistent (requirements R2.2,
design §4.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.adapters.gateway import EvidenceRecord, compute_evidence_content_hash
from app.models.llm_config import LLMCredentialsFile, ProviderRoute
from app.services.community_catalog import (
    COMMUNITY_PROVENANCE,
    EvidenceUpload,
    build_upload_record,
    is_uploadable,
)

_PROBE_EVIDENCE_TYPE = "probe"
_PROBE_VERIFIED = "probe-verified"
_PROBE_FAILED = "probe-failed"


def _with_hash(record: EvidenceRecord) -> EvidenceRecord:
    """Return the record carrying its computed content_hash (stamped if absent)."""
    digest = compute_evidence_content_hash(record)
    if record.content_hash == digest:
        return record
    return record.model_copy(update={"content_hash": digest})


def _observed_at_instant(value: str | None) -> datetime:
    """Parse observed_at to an aware instant; unknown/unparseable sorts oldest.

    P3: compare by real instant, not string — mixed tz formats ("Z" vs "+00:00"
    vs other offsets) make a lexical compare wrong, and remote catalog evidence is
    external input whose format varies.
    """
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _is_newer(candidate: EvidenceRecord, existing: EvidenceRecord) -> bool:
    return _observed_at_instant(candidate.observed_at) >= _observed_at_instant(existing.observed_at)


def merge_route_evidence(route: ProviderRoute, record: EvidenceRecord) -> ProviderRoute:
    """Merge one evidence record into ``route.evidence``, deduped by content_hash.

    Same content_hash → replace, keeping the newer ``observed_at``; otherwise
    append. Returns a NEW route (immutable style); never mutates the input.
    """
    stamped = _with_hash(record)
    merged: list[EvidenceRecord] = []
    replaced = False
    for raw_existing in route.evidence:
        # Re-hash every existing record (P2): never trust a stale/missing
        # content_hash, and ensure each kept record ends up carrying a correct one.
        existing = _with_hash(raw_existing)
        if existing.content_hash == stamped.content_hash:
            merged.append(stamped if _is_newer(stamped, existing) else existing)
            replaced = True
        else:
            merged.append(existing)
    if not replaced:
        merged.append(stamped)
    return route.model_copy(update={"evidence": merged})


# --- Read door: scope-aware queries (design §4.2, requirements R9) ------------
# Every runtime evidence read derives from credentials route.evidence here — the
# single seam that replaces the scattered ``load_evidence_library()`` readers
# (research §4 reader table). The probe catalog is never consulted at runtime.


@dataclass(frozen=True)
class ProbeEvidenceCounts:
    """PROBE-evidence counts derived from credentials (R9.2).

    ``probe_records`` counts probe-type evidence ONLY — a legacy
    ``provider-list-observed`` record that migrates onto a route never inflates
    the Settings "Local probe evidence" figures.
    """

    probe_records: int
    verified: int
    failed: int
    routes: int


def route_is_probe_verified(route: ProviderRoute) -> bool:
    """Whether the route carries any probe-verified probe evidence (R9.3)."""
    return any(
        ev.evidence_type == _PROBE_EVIDENCE_TYPE and ev.trust_state == _PROBE_VERIFIED
        for ev in route.evidence
    )


def route_probe_history(route: ProviderRoute) -> list[EvidenceRecord]:
    """Probe evidence (verified + failed) on the route, for last-result/diagnostics."""
    return [ev for ev in route.evidence if ev.evidence_type == _PROBE_EVIDENCE_TYPE]


def probe_evidence_counts(credentials: LLMCredentialsFile) -> ProbeEvidenceCounts:
    """Aggregate LOCAL probe-evidence counts across all routes (R9.2).

    Replaces the probe-catalog summary's catalog scan with a credentials scan so
    the Settings UI counts read the same single truth. Non-probe evidence (e.g.
    legacy ``provider-list-observed``) is excluded — this is a probe count — and
    **community-provenance evidence is excluded too**: it is advisory (downloaded,
    not locally probed) and must never inflate the "Local probe evidence" figures
    (Phase 5). Community evidence still projects blue via ``route_is_probe_verified``.
    """
    probe_records = 0
    verified = 0
    failed = 0
    for route in credentials.provider_routes.values():
        for ev in route.evidence:
            if ev.evidence_type != _PROBE_EVIDENCE_TYPE:
                continue
            if ev.metadata.get("provenance") == COMMUNITY_PROVENANCE:
                continue  # advisory community evidence is NOT a local probe count
            probe_records += 1
            if ev.trust_state == _PROBE_VERIFIED:
                verified += 1
            elif ev.trust_state == _PROBE_FAILED:
                failed += 1
    return ProbeEvidenceCounts(
        probe_records=probe_records,
        verified=verified,
        failed=failed,
        routes=len(credentials.provider_routes),
    )


def endpoint_listed_model_ids(credentials: LLMCredentialsFile, endpoint_id: str) -> list[str]:
    """Provider model ids an endpoint currently lists = its routes (R3.4).

    Model-list truth is the routes themselves (point 6 ruling); this replaces the
    retired ``known_model_ids_for_endpoint(library, ...)``. Order follows
    ``provider_routes`` insertion order, deduped.
    """
    model_ids: list[str] = []
    seen: set[str] = set()
    for route in credentials.provider_routes.values():
        if route.endpoint_id == endpoint_id and route.provider_model_id not in seen:
            model_ids.append(route.provider_model_id)
            seen.add(route.provider_model_id)
    return model_ids


def collect_uploadable(credentials: LLMCredentialsFile) -> list[EvidenceUpload]:
    """Sanitized upload candidates derived from credentials route.evidence (R9.1/R5).

    Includes only uploadable (probe + probe-verified) evidence that is (a) NOT
    community-provenance (R5.1-AC3: never re-upload remote-downloaded evidence,
    which would form a remote→local→remote loop) and (b) attributable to a PUBLIC
    endpoint — a record whose endpoint identity was redacted (non-allowlisted or
    empty base_url) carries no fingerprint, is unmatchable by the community gate,
    and is dropped (R5.1-AC2).
    """
    uploads: list[EvidenceUpload] = []
    for route in credentials.provider_routes.values():
        endpoint = credentials.provider_endpoints.get(route.endpoint_id)
        base_url = endpoint.base_url if endpoint is not None else None
        for ev in route.evidence:
            if not is_uploadable(ev):
                continue
            if ev.metadata.get("provenance") == COMMUNITY_PROVENANCE:
                continue
            upload = build_upload_record(ev, base_url=base_url)
            if upload.endpoint_fingerprint is None:
                continue
            uploads.append(upload)
    return uploads


def endpoint_probe_priority(
    credentials: LLMCredentialsFile,
    endpoint_id: str,
    candidate_model_ids: list[str],
) -> list[str]:
    """Order probe candidates so an endpoint Test reaches a green fastest (R9.4).

    Mirrors ``llm.py:_endpoint_probe_order`` — the endpoint-Test ordering, which
    leads with a known-good model and does NOT skip verified ones (that is the
    gateway's capability-discovery ``probe_priority``, a different goal):

    1. models on a currently-verified route (green) — surest bet,
    2. models with historical probe-verified evidence (blue),
    3. untried models,
    4. known-failed models last.

    Every tier is derived from credentials (``route.status`` + ``route.evidence``).
    """
    current_verified: set[str] = set()
    historical: set[str] = set()
    failed: set[str] = set()
    for route in credentials.provider_routes.values():
        if route.endpoint_id != endpoint_id:
            continue
        model_id = route.provider_model_id
        if route.status == "verified":
            current_verified.add(model_id)
        if route_is_probe_verified(route):
            historical.add(model_id)
        elif any(
            ev.evidence_type == _PROBE_EVIDENCE_TYPE and ev.trust_state == _PROBE_FAILED
            for ev in route.evidence
        ):
            failed.add(model_id)
    tier_current: list[str] = []
    tier_historical: list[str] = []
    tier_unknown: list[str] = []
    tier_failed: list[str] = []
    for model_id in candidate_model_ids:
        if model_id in current_verified:
            tier_current.append(model_id)
        elif model_id in historical:
            tier_historical.append(model_id)
        elif model_id in failed:
            tier_failed.append(model_id)
        else:
            tier_unknown.append(model_id)
    return [*tier_current, *tier_historical, *tier_unknown, *tier_failed]
