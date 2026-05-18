from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest
from app.main import create_app
from app.routers import llm as llm_router
from app.services.copilot_test import (
    PingResult,
    _NetworkError,
    _QuotaExceeded,
    _RateLimited,
    _Unauthorized,
)
from app.services.llm_provider_test import (
    PingResultExtended,
    ProviderType,
    ping_provider,
)
from fastapi.testclient import TestClient


def test_get_credentials_returns_has_key_without_api_key(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {
                    "provider_code": "OC_CL",
                    "api_key": "sk-secret",
                    "base_url": "https://base.test",
                }
            ]
        },
    )

    response = client.get("/api/llm/credentials")

    assert response.status_code == 200
    body = response.json()
    assert len(body["providers"]) == 1
    provider = body["providers"][0]
    assert provider["provider_code"] == "OC_CL"
    assert provider["has_key"] is True
    assert provider["base_url"] == "https://base.test"
    assert provider["last_test_status"] == "untested"
    assert provider["available_models"] == []
    assert "sk-secret" not in response.text
    assert "api_key" not in response.text


def test_put_credentials_requires_bearer_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    with TestClient(create_app()) as unauthenticated:
        response = unauthenticated.put(
            "/api/llm/credentials",
            json={"providers": [{"provider_code": "OC_CL", "api_key": "secret"}]},
        )

    assert response.status_code == 401


def test_put_credentials_writes_and_get_reads_sanitized(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.put(
        "/api/llm/credentials",
        json={"providers": [{"provider_code": "OC_CL", "api_key": "secret"}]},
    )

    assert response.status_code == 200
    assert response.json()["providers"][0]["has_key"] is True
    assert client.get("/api/llm/credentials").json()["providers"][0]["has_key"] is True
    assert "secret" not in response.text


@pytest.mark.parametrize(
    ("provider_type", "expected_kind"),
    [
        ("anthropic_compatible", "anthropic"),
        ("openai_compatible", "openai"),
        ("wavespeed_any_llm", "openai"),
        ("gemini_official", "gemini"),
    ],
)
def test_provider_test_uses_provider_type_to_select_client(
    provider_type: ProviderType,
    expected_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str], dict[str, str] | None]] = []

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"data": [{"id": "seen-model"}]}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            assert timeout == 8.0

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
        ) -> FakeResponse:
            calls.append((url, headers or {}, params))
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider_test.httpx.AsyncClient", FakeClient)

    result = asyncio.run(
        ping_provider(
            "PROV",
            provider_type,
            "secret",
            "https://base.test/v1",
        )
    )

    url, headers, params = calls[0]
    assert result.model_seen == "seen-model"
    if expected_kind == "anthropic":
        assert url == "https://base.test/v1/models"
        assert headers["x-api-key"] == "secret"
        assert "anthropic-version" in headers
    elif expected_kind == "openai":
        assert url == "https://base.test/v1/models"
        assert headers["Authorization"] == "Bearer secret"
    else:
        assert url == "https://base.test/v1/models"
        assert params == {"key": "secret"}


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (_Unauthorized(), "invalid_key"),
        (_RateLimited(), "rate_limited"),
        (_QuotaExceeded(), "quota_exceeded"),
        (_NetworkError("dns failure"), "network_error"),
        (TimeoutError(), "timeout"),
    ],
)
def test_provider_test_maps_errors(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc: Exception,
    status: str,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    async def fake_ping(
        _provider_code: str,
        _provider_type: ProviderType,
        _api_key: str,
        _base_url: str | None,
    ) -> PingResultExtended:
        raise exc

    monkeypatch.setattr(llm_router, "ping_provider_extended", fake_ping)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "provider_code": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == status


def test_provider_test_requires_token() -> None:
    with TestClient(create_app()) as unauthenticated:
        response = unauthenticated.post(
            "/api/llm/providers/test",
            json={
                "provider_code": "OC_CL",
                "provider_type": "anthropic_compatible",
                "api_key": "secret",
            },
        )

    assert response.status_code == 401


def test_provider_test_masks_key_in_response_and_logs(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    async def fake_ping(
        _provider_code: str,
        _provider_type: ProviderType,
        _api_key: str,
        _base_url: str | None,
    ) -> PingResultExtended:
        return PingResultExtended(
            latency_ms=12,
            model_seen="seen-model",
            model_ids=["seen-model"],
            raw_payload={"data": [{"id": "seen-model"}]},
        )

    monkeypatch.setattr(llm_router, "ping_provider_extended", fake_ping)
    caplog.set_level(logging.INFO, logger="app.routers.llm")

    response = client.post(
        "/api/llm/providers/test",
        json={
            "provider_code": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "sk-secret-1234",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["latency_ms"] == 12
    assert body["model_seen"] == "seen-model"
    assert body["message"] is None
    assert body["error_code"] is None
    assert "sk-secret-1234" not in response.text
    assert "sk-secret-1234" not in caplog.text
    assert "last4=1234" in caplog.text


# ---------------------------------------------------------------------------
# B3 — PUT semantics (full-replace, api_key preservation, Test single-write).
# ---------------------------------------------------------------------------


def test_put_credentials_full_replace_deletes_omitted_providers(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {"provider_code": "OC_CL", "api_key": "k1", "base_url": "https://a"},
                {"provider_code": "OC_OAI", "api_key": "k2", "base_url": "https://b"},
            ]
        },
    )
    # Second PUT omits OC_OAI → must delete it (full-replace semantics).
    response = client.put(
        "/api/llm/credentials",
        json={"providers": [{"provider_code": "OC_CL", "api_key": "k1", "base_url": "https://a"}]},
    )

    assert response.status_code == 200
    codes = sorted(p["provider_code"] for p in response.json()["providers"])
    assert codes == ["OC_CL"]


def test_put_credentials_preserves_existing_api_key_when_body_blank(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {"provider_code": "OC_CL", "api_key": "sk-original", "base_url": "https://a"}
            ]
        },
    )
    # Second PUT omits api_key (empty string) — original key must be preserved.
    response = client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {"provider_code": "OC_CL", "api_key": "", "base_url": "https://updated"}
            ]
        },
    )

    assert response.status_code == 200
    provider = response.json()["providers"][0]
    assert provider["has_key"] is True
    assert provider["base_url"] == "https://updated"

    # Verify on disk via load_credentials (round-trip)
    from app.services.llm_credentials import load_credentials

    saved = load_credentials()
    assert saved.providers[0].api_key == "sk-original"


def test_put_credentials_rejects_test_outcome_fields_in_body(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {
                    "provider_code": "OC_CL",
                    "api_key": "k",
                    "last_test_status": "ok",  # forbidden — Test fields are single-write
                }
            ]
        },
    )

    assert response.status_code == 422
    assert "last_test_status" in response.text


def test_put_credentials_preserves_test_outcome_fields(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test outcome fields written by POST must survive a subsequent PUT."""
    monkeypatch.setenv("HOME", str(tmp_path))

    client.put(
        "/api/llm/credentials",
        json={"providers": [{"provider_code": "OC_CL", "api_key": "k", "base_url": ""}]},
    )

    # Simulate a POST test writeback by directly invoking _persist_test_outcome.
    from app.models.llm_config import ModelCapabilities, ModelInfo
    from app.services.llm_credentials import _persist_test_outcome

    _persist_test_outcome(
        "OC_CL",
        last_test_status="ok",
        last_test_at="2026-05-18T12:00:00+00:00",
        last_test_message="",
        last_error_code="",
        available_models=[ModelInfo(id="claude-opus-4-1", capabilities=ModelCapabilities())],
    )

    # PUT only sends the 6 editable fields — Test fields must survive.
    response = client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {"provider_code": "OC_CL", "api_key": "k", "base_url": "https://updated"}
            ]
        },
    )

    assert response.status_code == 200
    provider = response.json()["providers"][0]
    assert provider["last_test_status"] == "ok"
    assert provider["last_test_at"] == "2026-05-18T12:00:00+00:00"
    assert provider["available_models"] == [
        {
            "id": "claude-opus-4-1",
            "capabilities": {
                "text": True,
                "function_calling": False,
                "vision": False,
                "reasoning": False,
            },
        }
    ]


# ---------------------------------------------------------------------------
# B4 — POST test missing_api_key + atomic writeback.
# ---------------------------------------------------------------------------


def test_provider_test_returns_missing_api_key_without_call(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    called: list[bool] = []

    async def fake_ping(*_args: object, **_kwargs: object) -> PingResultExtended:
        called.append(True)
        return PingResultExtended(latency_ms=0, model_seen=None, model_ids=[], raw_payload=None)

    monkeypatch.setattr(llm_router, "ping_provider_extended", fake_ping)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "provider_code": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "missing_api_key"
    assert body["error_code"] == "missing_api_key"
    assert called == [], "ping_provider_extended must not be called when api_key is blank"


def test_provider_test_missing_api_key_does_not_dirty_last_test_status(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: `missing_api_key` is a synthetic short-circuit code, not a
    TestStatus literal. Persisting it as `last_test_status` makes every later
    GET /api/llm/credentials fail with 422 (Literal validation) — frontend
    can't load the list at all. The empty-key path must keep
    `last_test_status="untested"` and stash the synthetic code in
    `last_error_code` only."""

    monkeypatch.setenv("HOME", str(tmp_path))

    # Seed a provider that has been used before so writeback has a target.
    client.put(
        "/api/llm/credentials",
        json={"providers": [{"provider_code": "OC_CL", "api_key": "sk-once", "base_url": ""}]},
    )

    # Empty-key Test (sonner toast still shows missing_api_key).
    response = client.post(
        "/api/llm/providers/test",
        json={"provider_code": "OC_CL", "provider_type": "openai_compatible", "api_key": ""},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "missing_api_key"

    # GET must NOT 422 — `last_test_status` must remain a valid TestStatus.
    get_response = client.get("/api/llm/credentials")
    assert get_response.status_code == 200, get_response.text
    providers = {p["provider_code"]: p for p in get_response.json()["providers"]}
    oc_cl = providers["OC_CL"]
    assert oc_cl["last_test_status"] == "untested"


def test_provider_test_persists_outcome_to_credentials(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    # Seed an existing provider so writeback has a target.
    client.put(
        "/api/llm/credentials",
        json={"providers": [{"provider_code": "OC_CL", "api_key": "sk", "base_url": ""}]},
    )

    async def fake_ping(*_args: object, **_kwargs: object) -> PingResultExtended:
        return PingResultExtended(
            latency_ms=42,
            model_seen="claude-opus-4-1",
            model_ids=["claude-opus-4-1", "claude-haiku-4-5"],
            raw_payload=None,
        )

    monkeypatch.setattr(llm_router, "ping_provider_extended", fake_ping)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "provider_code": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "sk",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["latency_ms"] == 42
    assert [m["id"] for m in body["available_models"]] == [
        "claude-opus-4-1",
        "claude-haiku-4-5",
    ]

    # Verify the writeback is now visible on a GET.
    get_response = client.get("/api/llm/credentials")
    provider = get_response.json()["providers"][0]
    assert provider["last_test_status"] == "ok"
    assert [m["id"] for m in provider["available_models"]] == [
        "claude-opus-4-1",
        "claude-haiku-4-5",
    ]


def test_provider_test_no_provider_silent_noop(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test writeback when the provider is not in credentials must not error."""
    monkeypatch.setenv("HOME", str(tmp_path))

    async def fake_ping(*_args: object, **_kwargs: object) -> PingResultExtended:
        return PingResultExtended(latency_ms=5, model_seen=None, model_ids=[], raw_payload=None)

    monkeypatch.setattr(llm_router, "ping_provider_extended", fake_ping)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "provider_code": "NEW_CODE",
            "provider_type": "anthropic_compatible",
            "api_key": "sk",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # No credentials file is created when there's nothing to update.
