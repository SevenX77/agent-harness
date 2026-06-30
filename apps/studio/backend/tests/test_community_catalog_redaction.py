"""Phase 2a R2 + W3-D: client-side redaction + safe-to-publish host gate.

Red-line: an upload payload must never carry secrets, private base URLs, local
paths, raw prompt/IO, or a bare un-salted hash of a private endpoint. Open
contribution (W3-D): ANY public provider host may publish its endpoint identity;
private / LAN / identity-bearing hosts drop it entirely before upload.
"""

from __future__ import annotations

import hashlib

import pytest
from app.services.community_catalog import (
    EvidenceUpload,
    build_upload_record,
    is_safe_to_publish,
    is_uploadable,
    normalize_base_url,
)

from tests.helpers_community_catalog import probe_record as _probe_record  # type: ignore[import-not-found]


def test_private_internal_host_drops_endpoint_identity() -> None:
    record = _probe_record()
    upload = build_upload_record(record, base_url="https://llm.mycompany.internal/v1")
    assert upload is not None
    assert upload.normalized_public_base_url is None
    assert upload.endpoint_fingerprint is None


def test_public_host_publishes_normalized_url_and_fingerprint() -> None:
    record = _probe_record()
    upload = build_upload_record(record, base_url="https://API.OpenAI.com/v1/")
    assert upload is not None
    assert upload.normalized_public_base_url == "https://api.openai.com/v1"
    expected = hashlib.sha256(b"https://api.openai.com/v1").hexdigest()
    assert upload.endpoint_fingerprint == expected


def test_public_transit_aggregator_hosts_publish() -> None:
    # A public AI transit/aggregator (anyone can register and connect) carries a
    # public domain with no user identity, so its connectivity evidence is
    # publishable — another client on the same transit can act on it. Under open
    # contribution (W3-D) such hosts keep their endpoint identity.
    for base in ("https://api.qnaigc.com/v1", "https://anthropic.qnaigc.com"):
        upload = build_upload_record(_probe_record(), base_url=base)
        assert upload is not None, base
        assert upload.normalized_public_base_url is not None, base
        assert upload.endpoint_fingerprint is not None, base


def test_fingerprint_never_published_without_plaintext() -> None:
    # A bare un-salted hash of a private host must never leak: for a private host
    # neither the plaintext URL nor any fingerprint is emitted.
    record = _probe_record()
    upload = build_upload_record(record, base_url="https://10.1.2.3/v1")
    assert upload is not None
    assert upload.endpoint_fingerprint is None
    assert upload.normalized_public_base_url is None


def test_forbidden_fields_never_reach_upload_payload() -> None:
    record = _probe_record(
        metadata={"api_key": "sk-LEAK", "credential_ref": "cred-1", "prompt": "secret"},
        source_url="https://llm.mycompany.internal/v1/chat",
        successful_probe={"raw_response": "user data", "base_url": "https://llm.mycompany.internal"},
    )
    upload = build_upload_record(record, base_url="https://llm.mycompany.internal/v1")
    assert upload is not None
    blob = upload.model_dump_json()
    for needle in ("sk-LEAK", "cred-1", "mycompany.internal", "raw_response", "secret"):
        assert needle not in blob


def test_upload_payload_uses_wire_evidence_type_probe_result() -> None:
    upload = build_upload_record(_probe_record(), base_url="https://api.openai.com/v1")
    assert upload is not None
    assert upload.evidence_type == "probe_result"


def test_provider_list_observed_is_not_uploadable() -> None:
    record = _probe_record(evidence_type="model_list_observation", trust_state="provider-list-observed")
    assert is_uploadable(record) is False


def test_probe_verified_probe_is_uploadable() -> None:
    assert is_uploadable(_probe_record()) is True


def test_upload_model_forbids_extra_fields() -> None:
    with pytest.raises(ValueError):
        EvidenceUpload.model_validate(
            {"evidence_type": "probe_result", "trust_state": "probe-verified", "leak": "x"}
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://API.OpenAI.com/v1/", "https://api.openai.com/v1"),
        ("https://api.openai.com:443/v1", "https://api.openai.com/v1"),
        ("http://Example.com:80/", "http://example.com"),
        ("https://host.tld///a//b/", "https://host.tld/a/b"),
    ],
)
def test_normalize_base_url(raw: str, expected: str) -> None:
    assert normalize_base_url(raw) == expected


@pytest.mark.parametrize(
    ("url", "publishable"),
    [
        # Open contribution (W3-D): any public provider host publishes — no fixed
        # allowlist. A brand-new provider (e.g. wavespeed.ai) is contributable.
        ("https://llm.wavespeed.ai/v1", True),
        ("https://api.openai.com/v1", True),
        ("https://some-new-provider.example.com/v1", True),
        # Private / LAN / loopback / raw private IP / bare single-label → dropped.
        ("https://llm.mycompany.internal/v1", False),
        ("http://localhost:8080/v1", False),
        ("https://10.1.2.3/v1", False),
        ("https://192.168.0.5:11434/v1", False),
        ("https://intranet/v1", False),
        # Userinfo (identity-bearing) → dropped even on a public host.
        ("https://user:tok@api.openai.com/v1", False),
    ],
)
def test_open_contribution_publish_safety_gate(url: str, publishable: bool) -> None:
    # R-C1+R-C2: the fixed host allowlist is replaced by a safety gate — public DNS
    # hosts / public IPs publish; private/LAN/loopback/raw private IPs, bare
    # single-label hosts, and userinfo-bearing URLs never do. (Param named `url`,
    # not `base_url`, to avoid colliding with the session-scoped pytest base_url fixture.)
    assert is_safe_to_publish(url) is publishable
    upload = build_upload_record(_probe_record(), base_url=url)
    assert (upload.normalized_public_base_url is not None) is publishable
    assert (upload.endpoint_fingerprint is not None) is publishable
