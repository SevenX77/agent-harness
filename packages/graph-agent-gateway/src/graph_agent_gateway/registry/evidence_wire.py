"""What a piece of probe evidence looks like once it leaves this machine.

The Probe Knowledge Catalog is worth sharing, so this module owns the rule for
what may cross that line — the same package that owns the catalog owns the
red-line guarding it:

- :class:`EvidenceUpload` is a strict allowlist (``extra="forbid"``), so secrets,
  credential refs, local paths, raw prompt/IO and free-form probe blobs cannot
  reach the wire by construction rather than by remembering to strip them.
- Endpoint identity is published only when the host is safe to publish — a public
  DNS name or globally-routable IP with no userinfo. A private / LAN /
  identity-bearing host drops its identity entirely; a bare un-salted hash of a
  private host is never emitted, because a hash of a guessable name is not
  anonymous.
- Only ``probe``-type, ``probe-verified`` evidence is shareable at all, and both
  wire mappings fail closed on anything else.

``published_base_url`` is NOT ``registry/base_url.py:canonicalize_base_url`` and
the two must not be confused. That one answers "which URL do I actually call",
and is protocol-aware — it appends ``/anthropic`` for DeepSeek's
anthropic-compatible endpoint, ``/api/v3`` for Ark. This one answers "which
string do two different people publish so the same endpoint matches", and so
lowercases the host, drops default ports and discards query/fragment. Feeding
either one to the other's job produces a wrong answer that looks right.
"""

from __future__ import annotations

import hashlib
import ipaddress
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict

from graph_agent_gateway.registry.schema import EvidenceRecord

WIRE_EVIDENCE_TYPE: Literal["probe_result"] = "probe_result"
INTERNAL_PROBE_EVIDENCE_TYPE = "probe"
UPLOADABLE_TRUST_STATE = "probe-verified"
# Provenance marker so ingested community evidence is never confused with
# locally verified evidence (and is never auto-applied to credentials).
COMMUNITY_PROVENANCE = "community-catalog"

_DEFAULT_PORTS = {"http": 80, "https": 443}


def published_base_url(base_url: str) -> str:
    """Return the form of a base URL that is published and fingerprinted:
    lowercase scheme/host, default port and trailing slash stripped, collapsed
    path slashes, query/fragment discarded."""
    split = urlsplit(base_url.strip())
    scheme = split.scheme.lower()
    host = (split.hostname or "").lower()
    netloc = host
    if split.port is not None and split.port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{split.port}"
    segments = [segment for segment in split.path.split("/") if segment]
    path = "/" + "/".join(segments) if segments else ""
    return urlunsplit((scheme, netloc, path, "", ""))


def endpoint_host(base_url: str) -> str | None:
    """Return the lowercase hostname of a base URL, or ``None`` if unparsable."""
    return (urlsplit(base_url.strip()).hostname or "").lower() or None


_NON_PUBLIC_HOST_SUFFIXES = (
    # Private / LAN / corporate-intranet host suffixes.
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".corp",
    ".intranet",
    # RFC 6761 special-use TLDs that never resolve publicly — publishing them is
    # noise, never a real provider endpoint.
    ".test",
    ".example",
    ".invalid",
    ".localhost",
)


def _is_publishable_public_host(host: str) -> bool:
    """Whether a hostname is a public DNS name (or globally-routable IP) safe to
    publish — not localhost / a private-or-LAN host / a bare single-label host."""
    normalized = host.strip().lower().rstrip(".")
    if (
        not normalized
        or normalized == "localhost"
        or normalized.endswith(_NON_PUBLIC_HOST_SUFFIXES)
    ):
        return False
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        # A DNS name: require a dot so a bare single-label intranet host is dropped.
        return "." in normalized
    # A raw IP literal: only a globally-routable public address may be published.
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def is_safe_to_publish(base_url: str) -> bool:
    """Whether a base URL's endpoint identity is safe to publish to the community
    catalog (R-C1/R-C2): a public DNS host (or public IP) with no embedded
    userinfo. Replaces the old fixed host allowlist so ANY public provider can
    contribute connectivity evidence, while private / LAN / identity-bearing
    endpoints are never leaked."""
    split = urlsplit(base_url.strip())
    if split.username or split.password:
        return False
    host = (split.hostname or "").lower()
    return bool(host) and _is_publishable_public_host(host)


def endpoint_fingerprint(normalized_base_url: str) -> str:
    """Return a SHA-256 fingerprint of an already-normalized base URL.

    Only ever published alongside the plaintext URL (safe-to-publish hosts), so it
    never leaks a private host as a bare hash.
    """
    return hashlib.sha256(normalized_base_url.encode("utf-8")).hexdigest()


class EvidenceUpload(BaseModel):
    """Sanitized, wire-safe evidence record for community ingestion.

    Strict allowlist: ``extra="forbid"`` guarantees no unexpected (possibly
    sensitive) field can ride along.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_type: Literal["probe_result"]
    trust_state: str
    provider_id: str | None = None
    normalized_public_base_url: str | None = None
    endpoint_fingerprint: str | None = None
    route_key: str | None = None
    provider_model_id: str | None = None
    model_id: str | None = None
    method_id: str | None = None
    request_mapper_id: str | None = None
    capability_family: str | None = None
    model_type: str | None = None
    input_modalities: list[str] = []
    output_modalities: list[str] = []
    probe_status: str | None = None
    observed_at: str | None = None


def is_uploadable(record: EvidenceRecord) -> bool:
    """Only probe-verified probe evidence may be shared with the community.

    ``provider-list-observed`` and other non-probe evidence are never uploadable.
    """
    return (
        record.evidence_type == INTERNAL_PROBE_EVIDENCE_TYPE
        and record.trust_state == UPLOADABLE_TRUST_STATE
    )


def build_upload_record(
    record: EvidenceRecord,
    *,
    base_url: str | None,
) -> EvidenceUpload:
    """Build a sanitized upload payload from a local probe evidence record.

    Endpoint identity (normalized URL + fingerprint) is included only when
    ``base_url`` is safe to publish — a public DNS host / public IP with no
    embedded userinfo (see ``is_safe_to_publish``); private / LAN / identity-bearing
    endpoints drop it. Only an explicit set of safe scalar fields is copied —
    free-form blobs (metadata/probe attempts/agent notes/URLs/local IDs) are never copied.
    """
    normalized_url: str | None = None
    fingerprint: str | None = None
    if base_url and is_safe_to_publish(base_url):
        normalized_url = published_base_url(base_url)
        fingerprint = endpoint_fingerprint(normalized_url)

    route_key: str | None = None
    if fingerprint is not None:
        route_key = f"{fingerprint}:{record.provider_model_id or ''}:{record.method_id or ''}"

    return EvidenceUpload(
        evidence_type=WIRE_EVIDENCE_TYPE,
        trust_state=record.trust_state,
        provider_id=record.provider_id,
        normalized_public_base_url=normalized_url,
        endpoint_fingerprint=fingerprint,
        route_key=route_key,
        provider_model_id=record.provider_model_id,
        model_id=record.model_id,
        method_id=record.method_id,
        request_mapper_id=record.request_mapper_id,
        capability_family=record.capability_family,
        model_type=record.model_type,
        input_modalities=list(record.input_modalities),
        output_modalities=list(record.output_modalities),
        probe_status=record.probe_status,
        observed_at=record.observed_at,
    )


def to_wire_evidence_type(internal_type: str) -> str:
    """Map the gateway's internal evidence type to the wire type.

    Only ``probe`` is shareable; anything else raises (fail closed).
    """
    if internal_type == INTERNAL_PROBE_EVIDENCE_TYPE:
        return WIRE_EVIDENCE_TYPE
    raise ValueError(f"evidence type not shareable to community catalog: {internal_type!r}")


def from_wire_evidence_type(wire_type: str) -> str:
    """Map a wire evidence type back to the gateway's internal type.

    The probe catalog only ships ``probe_result``; anything else raises.
    """
    if wire_type == WIRE_EVIDENCE_TYPE:
        return INTERNAL_PROBE_EVIDENCE_TYPE
    raise ValueError(f"unexpected community catalog evidence type: {wire_type!r}")


def parse_catalog_evidence(wire_record: dict[str, Any]) -> EvidenceRecord:
    """Map a downloaded community catalog record into an internal EvidenceRecord.

    The wire type ``probe_result`` is mapped to ``probe``; community provenance
    plus the published endpoint identity are recorded in ``metadata`` so the
    record is advisory and never confused with locally verified evidence.
    Unknown wire fields are dropped (forward compatible); a missing evidence_id
    or unexpected evidence type fails closed.
    """
    evidence_id = wire_record.get("evidence_id")
    if not evidence_id:
        raise ValueError("community catalog record missing evidence_id")
    internal_type = from_wire_evidence_type(str(wire_record.get("evidence_type")))

    metadata: dict[str, Any] = {"provenance": COMMUNITY_PROVENANCE}
    for carried in ("endpoint_fingerprint", "route_key"):
        value = wire_record.get(carried)
        if value is not None:
            metadata[carried] = value

    return EvidenceRecord.model_validate(
        {
            "evidence_id": evidence_id,
            "evidence_type": internal_type,
            "trust_state": wire_record.get("trust_state", UPLOADABLE_TRUST_STATE),
            "observed_at": wire_record.get("observed_at"),
            "provider_id": wire_record.get("provider_id"),
            "provider_model_id": wire_record.get("provider_model_id"),
            "model_id": wire_record.get("model_id"),
            "method_id": wire_record.get("method_id"),
            "request_mapper_id": wire_record.get("request_mapper_id"),
            "capability_family": wire_record.get("capability_family"),
            "model_type": wire_record.get("model_type"),
            "input_modalities": list(wire_record.get("input_modalities", [])),
            "output_modalities": list(wire_record.get("output_modalities", [])),
            "probe_status": wire_record.get("probe_status"),
            # Phase 5: endpoint public identity is a FORMAL field so content_hash and
            # route matching read it from the record, not from free-form metadata.
            "normalized_public_base_url": wire_record.get("normalized_public_base_url"),
            "metadata": metadata,
        }
    )


__all__ = [
    "COMMUNITY_PROVENANCE",
    "UPLOADABLE_TRUST_STATE",
    "WIRE_EVIDENCE_TYPE",
    "EvidenceUpload",
    "build_upload_record",
    "endpoint_fingerprint",
    "endpoint_host",
    "from_wire_evidence_type",
    "is_safe_to_publish",
    "is_uploadable",
    "published_base_url",
    "parse_catalog_evidence",
    "to_wire_evidence_type",
]
