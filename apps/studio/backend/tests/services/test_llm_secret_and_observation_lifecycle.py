"""Endpoint secret writes and the test observations that ride on them.

Design source: `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §1.2 matrix
point 3 — "格子永不删除、永不手工 disable，状态 = 最近观察的投影". A stored status is a
projection of the LAST OBSERVATION, and every observation was made with one
specific API key. Swap the key and the observation is about a credential that no
longer exists, so it must not keep speaking for the new one.

Decision: `docs/design/2026-08-19-api-key-test-revive-and-secret-field-lifecycle.md`
(D4 + D5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.services.llm_credentials import (
    SECRET_REDACTION_PLACEHOLDER,
    EndpointInvariantViolation,
    load_credentials,
    upsert_endpoints,
)

_MASK_CHAR = "•"


def _seed(path: Path, **endpoint_overrides: Any) -> None:
    payload: dict[str, Any] = {
        "endpoint_id": "acme-openai",
        "display_name": "Acme",
        "protocol": "openai_compatible",
        "base_url": "https://api.acme.example/v1",
        "api_key": "sk-original-key",
    }
    upsert_endpoints({"acme-openai": payload}, path=path)
    if endpoint_overrides:
        data = load_credentials(path)
        endpoint_id = _endpoint_id(path)
        data.provider_endpoints[endpoint_id] = data.provider_endpoints[
            endpoint_id
        ].model_copy(update=endpoint_overrides)
        from app.services.llm_credentials import save_credentials

        save_credentials(data, path=path)


def _write(path: Path, api_key: str | None) -> None:
    payload: dict[str, Any] = {
        "endpoint_id": "acme-openai",
        "display_name": "Acme",
        "protocol": "openai_compatible",
        "base_url": "https://api.acme.example/v1",
    }
    if api_key is not None:
        payload["api_key"] = api_key
    upsert_endpoints({"acme-openai": payload}, path=path)


def _endpoint_id(path: Path) -> str:
    # upsert canonicalizes the endpoint id from (base_url, protocol); the tests
    # care about the record, not the name it settles on.
    endpoint_ids = list(load_credentials(path).provider_endpoints)
    assert len(endpoint_ids) == 1, endpoint_ids
    return endpoint_ids[0]


def _endpoint(path: Path) -> Any:
    return load_credentials(path).provider_endpoints[_endpoint_id(path)]


def test_changing_the_key_retires_the_previous_test_observation(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    _seed(
        path,
        status="verified",
        last_test_at="2026-08-12T16:34:38+00:00",
        last_test_message="Generation verified via openai_compatible.",
        last_error_code=None,
    )

    _write(path, "sk-a-brand-new-key")

    endpoint = _endpoint(path)
    assert endpoint.api_key is not None
    assert endpoint.api_key.get_secret_value() == "sk-a-brand-new-key"
    assert endpoint.status == "unverified_manual"
    assert endpoint.last_test_at is None
    assert endpoint.last_test_message is None
    assert endpoint.last_error_code is None


def test_changing_the_key_retires_a_failed_verdict_too(tmp_path: Path) -> None:
    # The whole point: a key rejected as invalid must not keep the replacement
    # key pre-condemned (live 2026-08-19 — deepseek-official stayed unusable
    # through every key change).
    path = tmp_path / "llm_credentials.json"
    _seed(
        path,
        status="failed",
        last_test_at="2026-08-12T16:34:38+00:00",
        last_test_message="Invalid API key (invalid_request_error).",
        last_error_code="invalid_request_error",
    )

    _write(path, "sk-a-brand-new-key")

    endpoint = _endpoint(path)
    assert endpoint.status == "unverified_manual"
    assert endpoint.last_error_code is None


def test_changing_the_key_keeps_a_protocol_unsupported_observation(tmp_path: Path) -> None:
    # `protocol_unsupported` is a fact about (base_url, protocol): this host does
    # not speak this protocol, whichever key you hold. It owns a 30-day half-life
    # (§1.2 matrix point 4), so a key swap must not silently reset that clock.
    path = tmp_path / "llm_credentials.json"
    _seed(
        path,
        status="failed",
        last_test_at="2026-08-12T16:34:38+00:00",
        last_test_message="Endpoint test failed (protocol_unsupported).",
        last_error_code="protocol_unsupported",
    )

    _write(path, "sk-a-brand-new-key")

    endpoint = _endpoint(path)
    assert endpoint.status == "failed"
    assert endpoint.last_test_at == "2026-08-12T16:34:38+00:00"
    assert endpoint.last_error_code == "protocol_unsupported"


def test_unchanged_key_keeps_the_observation(tmp_path: Path) -> None:
    # The pre-test upsert (`getProviderModels` PUTs the draft before probing)
    # replays the same key on every Test press. It must not look like a rotation.
    path = tmp_path / "llm_credentials.json"
    _seed(
        path,
        status="verified",
        last_test_at="2026-08-12T16:34:38+00:00",
        last_test_message="Generation verified via openai_compatible.",
    )

    _write(path, "sk-original-key")

    endpoint = _endpoint(path)
    assert endpoint.status == "verified"
    assert endpoint.last_test_at == "2026-08-12T16:34:38+00:00"


def test_omitted_key_keeps_both_the_secret_and_the_observation(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    _seed(path, status="verified", last_test_at="2026-08-12T16:34:38+00:00")

    _write(path, None)

    endpoint = _endpoint(path)
    assert endpoint.api_key is not None
    assert endpoint.api_key.get_secret_value() == "sk-original-key"
    assert endpoint.status == "verified"


def test_redaction_placeholder_is_never_taken_as_a_new_secret(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    _seed(path, status="verified", last_test_at="2026-08-12T16:34:38+00:00")

    _write(path, SECRET_REDACTION_PLACEHOLDER)

    endpoint = _endpoint(path)
    assert endpoint.api_key is not None
    assert endpoint.api_key.get_secret_value() == "sk-original-key"
    assert endpoint.status == "verified"


def test_partially_edited_mask_is_rejected_at_the_boundary(tmp_path: Path) -> None:
    # A field that renders a mask can only ever hand back mask characters. One
    # backspace on the 10-char placeholder used to arrive here as a nine-asterisk
    # "new key" and overwrite a working credential — the exact-match guard let
    # everything but the untouched placeholder through. Such a value cannot be a
    # secret, so it is refused with a diagnosis instead of being stored (or
    # silently dropped, which would leave the caller believing it saved a key).
    path = tmp_path / "llm_credentials.json"
    for edited in (
        "*********",
        "***",
        _MASK_CHAR * 35,
        _MASK_CHAR * 34 + "*",
        SECRET_REDACTION_PLACEHOLDER + "sk-live-key",
        "sk-live" + _MASK_CHAR + "key",
    ):
        _seed(path, status="verified")

        with pytest.raises(EndpointInvariantViolation) as excinfo:
            _write(path, edited)
        assert "mask" in str(excinfo.value).lower(), edited

        endpoint = _endpoint(path)
        assert endpoint.api_key is not None
        assert endpoint.api_key.get_secret_value() == "sk-original-key", edited
        assert endpoint.status == "verified", edited


def test_clearing_the_key_outright_still_works(tmp_path: Path) -> None:
    # Emptying the field is a real intent (drop this credential) and must stay
    # distinguishable from "the mask came back untouched".
    path = tmp_path / "llm_credentials.json"
    _seed(path, status="verified", last_test_at="2026-08-12T16:34:38+00:00")

    _write(path, "")

    endpoint = _endpoint(path)
    assert endpoint.api_key is None
    assert endpoint.status == "unverified_manual"
