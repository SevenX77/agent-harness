"""Phase 2a R2: client-side redaction + public-host allowlist drop.

Red-line: an upload payload must never carry secrets, private base URLs, local
paths, raw prompt/IO, or a bare un-salted hash of a private endpoint. Non-
allowlisted hosts drop their endpoint identity entirely before upload.
"""

from __future__ import annotations

import hashlib

import pytest
from app.services.community_catalog import (
    PUBLIC_PROVIDER_HOST_ALLOWLIST,
    EvidenceUpload,
    build_upload_record,
    is_uploadable,
    normalize_base_url,
)

from tests.helpers_community_catalog import probe_record as _probe_record  # type: ignore[import-not-found]


def test_non_allowlisted_host_drops_endpoint_identity() -> None:
    record = _probe_record()
    upload = build_upload_record(record, base_url="https://llm.mycompany.internal/v1")
    assert upload is not None
    assert upload.normalized_public_base_url is None
    assert upload.endpoint_fingerprint is None


def test_allowlisted_host_publishes_normalized_url_and_fingerprint() -> None:
    record = _probe_record()
    upload = build_upload_record(record, base_url="https://API.OpenAI.com/v1/")
    assert upload is not None
    assert upload.normalized_public_base_url == "https://api.openai.com/v1"
    expected = hashlib.sha256(b"https://api.openai.com/v1").hexdigest()
    assert upload.endpoint_fingerprint == expected


def test_fingerprint_never_published_without_plaintext() -> None:
    # A bare un-salted hash of a private host must never leak. When the host is
    # not allowlisted, neither the plaintext nor any fingerprint is present.
    record = _probe_record()
    upload = build_upload_record(record, base_url="https://secret-host.example.org/v1")
    assert upload is not None
    if upload.endpoint_fingerprint is not None:
        assert upload.normalized_public_base_url is not None


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


def test_allowlist_contains_known_public_providers() -> None:
    # Subset check via set operators rather than `str in ...`: membership in this
    # frozenset is exact and safe, but CodeQL misreads `"host" in <name>` as
    # URL-substring sanitization (a false positive). The production host check
    # (`is_public_allowlisted`) extracts the hostname via urlsplit and matches the
    # set exactly, so `api.openai.com.evil.com` cannot pass.
    assert {
        "api.openai.com",
        "api.anthropic.com",
        "api.deepseek.com",
    } <= PUBLIC_PROVIDER_HOST_ALLOWLIST
