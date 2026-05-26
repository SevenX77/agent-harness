from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest
from app.main import create_app
from app.models.llm_config import ModelInfo
from app.routers import llm as llm_router
from app.services.llm_provider_test import (
    ProviderType,
    ping_provider,
)
from fastapi.testclient import TestClient


def _model(model_id: str) -> ModelInfo:
    return ModelInfo(id=model_id)


def _model_with_capabilities(model_id: str, capabilities: dict[str, Any]) -> ModelInfo:
    return ModelInfo(id=model_id, capabilities=capabilities)


def _model_ids(models: list[dict[str, Any]]) -> list[str]:
    return [model["id"] for model in models]


def test_get_credentials_returns_api_key_plaintext(
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
                    "id": "OC_CL",
                    "name": "Claude",
                    "api_key": "sk-test-fake-key",
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
    assert provider["id"] == "OC_CL"
    assert provider["api_key"] == "sk-test-fake-key"
    assert provider["base_url"] == "https://base.test"
    assert provider["last_test_status"] == "untested"
    assert provider["available_models"] == []
    assert "has_key" not in provider


def test_put_credentials_requires_bearer_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    with TestClient(create_app()) as unauthenticated:
        response = unauthenticated.put(
            "/api/llm/credentials",
            json={"providers": [{"id": "OC_CL", "name": "Claude", "api_key": "secret"}]},
        )

    assert response.status_code == 401


def test_put_credentials_writes_and_get_reads_plaintext(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.put(
        "/api/llm/credentials",
        json={"providers": [{"id": "OC_CL", "name": "Claude", "api_key": "sk-test-fake-key"}]},
    )

    assert response.status_code == 200
    assert response.json()["providers"][0]["api_key"] == "sk-test-fake-key"
    assert (
        client.get("/api/llm/credentials").json()["providers"][0]["api_key"] == "sk-test-fake-key"
    )


@pytest.mark.parametrize(
    ("provider_type", "expected_kind"),
    [
        ("anthropic_compatible", "anthropic"),
        ("openai_compatible", "openai"),
        ("google_genai", "gemini"),
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
    ("exc", "expected_status", "expected_error_code"),
    [
        (RuntimeError("provider rejected the request"), "error", "model_list_unavailable"),
        (TimeoutError(), "timeout", "timeout"),
    ],
)
def test_provider_test_model_list_errors_return_human_test_status(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc: Exception,
    expected_status: str,
    expected_error_code: str,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    async def fake_models(*_args: object, **_kwargs: object) -> list[ModelInfo]:
        raise exc

    async def fake_sdks(*_args: object, **_kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)
    monkeypatch.setattr(llm_router, "probe_compatible_sdks", fake_sdks)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "secret",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_status
    assert body["error_code"] == expected_error_code
    assert body["available_sdks"] == []


def test_provider_test_requires_token() -> None:
    with TestClient(create_app()) as unauthenticated:
        response = unauthenticated.post(
            "/api/llm/providers/test",
            json={
                "id": "OC_CL",
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

    async def fake_sdks(*_args: object, **_kwargs: object) -> list[str]:
        return ["anthropic_compatible"]

    async def fake_models(*_args: object, **_kwargs: object) -> list[ModelInfo]:
        return [_model("seen-model")]

    monkeypatch.setattr(llm_router, "probe_compatible_sdks", fake_sdks)
    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)
    caplog.set_level(logging.INFO, logger="app.routers.llm")

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "sk-secret-1234",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["latency_ms"], int)
    assert body["model_seen"] is None
    assert body["message"] is None
    assert body["error_code"] is None
    assert body["available_sdks"] == ["anthropic_compatible"]
    assert _model_ids(body["available_models"]) == ["seen-model"]
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
                {"id": "OC_CL", "name": "Claude", "api_key": "k1", "base_url": "https://a"},
                {"id": "OC_OAI", "name": "OpenAI", "api_key": "k2", "base_url": "https://b"},
            ]
        },
    )
    # Second PUT omits OC_OAI → must delete it (full-replace semantics).
    response = client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {"id": "OC_CL", "name": "Claude", "api_key": "k1", "base_url": "https://a"}
            ]
        },
    )

    assert response.status_code == 200
    codes = sorted(p["id"] for p in response.json()["providers"])
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
                {"id": "OC_CL", "name": "Claude", "api_key": "sk-original", "base_url": "https://a"}
            ]
        },
    )
    # Second PUT omits api_key (empty string) — original key must be preserved.
    response = client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {"id": "OC_CL", "name": "Claude", "api_key": "", "base_url": "https://updated"}
            ]
        },
    )

    assert response.status_code == 200
    provider = response.json()["providers"][0]
    assert provider["api_key"] == "sk-original"
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
                    "id": "OC_CL",
                    "name": "Claude",
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
    """Test outcome fields written by POST survive PUT when test params match."""
    monkeypatch.setenv("HOME", str(tmp_path))

    client.put(
        "/api/llm/credentials",
        json={"providers": [{"id": "OC_CL", "name": "Claude", "api_key": "k", "base_url": ""}]},
    )

    # Simulate a POST test writeback by directly invoking _persist_test_outcome.
    from app.services.llm_credentials import _persist_test_outcome

    _persist_test_outcome(
        "OC_CL",
        last_test_status="ok",
        last_test_at="2026-05-18T12:00:00+00:00",
        last_test_message="",
        last_error_code="",
        available_models=[_model("claude-opus-4-1")],
    )

    # PUT only sends the 6 editable fields — Test fields must survive.
    response = client.put(
        "/api/llm/credentials",
        json={
            "providers": [{"id": "OC_CL", "name": "Claude renamed", "api_key": "", "base_url": ""}]
        },
    )

    assert response.status_code == 200
    provider = response.json()["providers"][0]
    assert provider["name"] == "Claude renamed"
    assert provider["api_key"] == "k"
    assert provider["last_test_status"] == "ok"
    assert provider["last_test_at"] == "2026-05-18T12:00:00+00:00"
    assert _model_ids(provider["available_models"]) == ["claude-opus-4-1"]


def test_put_credentials_resets_test_outcome_when_test_params_change(
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
                    "id": "OC_CL",
                    "name": "Claude",
                    "api_key": "k",
                    "base_url": "",
                    "provider_type": "anthropic_compatible",
                }
            ]
        },
    )

    from app.services.llm_credentials import _persist_test_outcome

    _persist_test_outcome(
        "OC_CL",
        last_test_status="ok",
        last_test_at="2026-05-18T12:00:00+00:00",
        last_test_message="Connected.",
        last_error_code="",
        available_sdks=["anthropic_compatible"],
        available_models=[_model("claude-opus-4-1")],
    )

    response = client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {
                    "id": "OC_CL",
                    "name": "Claude",
                    "api_key": "",
                    "base_url": "https://api.anthropic.test",
                    "provider_type": "anthropic_compatible",
                }
            ]
        },
    )

    assert response.status_code == 200
    provider = response.json()["providers"][0]
    assert provider["api_key"] == "k"
    assert provider["base_url"] == "https://api.anthropic.test"
    assert provider["last_test_status"] == "untested"
    assert provider["last_test_at"] == ""
    assert provider["last_test_message"] == ""
    assert provider["last_error_code"] == ""
    assert provider["available_sdks"] == []
    assert provider["available_models"] == []


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

    async def fake_sdks(*_args: object, **_kwargs: object) -> list[str]:
        called.append(True)
        return ["should-not-run"]

    monkeypatch.setattr(llm_router, "probe_compatible_sdks", fake_sdks)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "missing_api_key"
    assert body["error_code"] == "missing_api_key"
    assert called == [], "probe_compatible_sdks must not be called when api_key is blank"


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
        json={
            "providers": [{"id": "OC_CL", "name": "Claude", "api_key": "sk-once", "base_url": ""}]
        },
    )

    # Empty-key Test (sonner toast still shows missing_api_key).
    response = client.post(
        "/api/llm/providers/test",
        json={"id": "OC_CL", "provider_type": "openai_compatible", "api_key": ""},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "missing_api_key"

    # GET must NOT 422 — `last_test_status` must remain a valid TestStatus.
    get_response = client.get("/api/llm/credentials")
    assert get_response.status_code == 200, get_response.text
    providers = {p["id"]: p for p in get_response.json()["providers"]}
    oc_cl = providers["OC_CL"]
    assert oc_cl["last_test_status"] == "untested"


def test_provider_test_calls_probes_and_returns_string_lists(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    calls: list[tuple[str, str, str]] = []

    async def fake_sdks(vendor: str, api_key: str, base_url: str) -> list[str]:
        calls.append(("sdks", vendor, base_url))
        assert api_key == "sk-test"
        return ["openai_compatible"]

    async def fake_models(vendor: str, api_key: str, base_url: str) -> list[ModelInfo]:
        calls.append(("models", vendor, base_url))
        assert api_key == "sk-test"
        return [_model("gpt-5"), _model("gpt-4o")]

    monkeypatch.setattr(llm_router, "probe_compatible_sdks", fake_sdks)
    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "openai-default",
            "provider_type": "openai_compatible",
            "api_key": "sk-test",
            "base_url": "https://api.openai.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["error_code"] is None
    assert body["available_sdks"] == ["openai_compatible"]
    assert _model_ids(body["available_models"]) == ["gpt-5", "gpt-4o"]
    assert calls == [
        ("models", "openai", "https://api.openai.com"),
    ]


def test_provider_test_persists_string_probe_results_to_credentials(
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
                    "id": "openai-default",
                    "name": "OpenAI",
                    "api_key": "sk",
                    "base_url": "https://api.openai.com",
                    "provider_type": "openai_compatible",
                }
            ]
        },
    )

    async def fake_sdks(*_args: object, **_kwargs: object) -> list[str]:
        return ["openai_compatible"]

    async def fake_models(*_args: object, **_kwargs: object) -> list[ModelInfo]:
        return [_model("gpt-5"), _model("gpt-4o")]

    monkeypatch.setattr(llm_router, "probe_compatible_sdks", fake_sdks)
    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "openai-default",
            "provider_type": "openai_compatible",
            "api_key": "sk",
            "base_url": "https://api.openai.com",
        },
    )
    assert response.status_code == 200

    get_response = client.get("/api/llm/credentials")
    provider = get_response.json()["providers"][0]
    assert provider["last_test_status"] == "ok"
    assert provider["available_sdks"] == ["openai_compatible"]
    assert _model_ids(provider["available_models"]) == ["gpt-5", "gpt-4o"]


def test_provider_test_does_not_write_back_after_parameters_change(
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
                    "id": "openai-default",
                    "name": "OpenAI",
                    "api_key": "sk-old",
                    "base_url": "https://api.old.test",
                    "provider_type": "openai_compatible",
                }
            ]
        },
    )

    async def fake_models(*_args: object, **_kwargs: object) -> list[ModelInfo]:
        from app.models.llm_config import LLMCredentialsFile, ProviderCredential
        from app.services.llm_credentials import save_credentials

        save_credentials(
            LLMCredentialsFile(
                providers=[
                    ProviderCredential(
                        id="openai-default",
                        name="OpenAI",
                        api_key="sk-new",
                        base_url="https://api.new.test",
                        provider_type="openai_compatible",
                    )
                ]
            )
        )
        return [_model("gpt-5")]

    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "openai-default",
            "provider_type": "openai_compatible",
            "api_key": "sk-old",
            "base_url": "https://api.old.test",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    provider = client.get("/api/llm/credentials").json()["providers"][0]
    assert provider["api_key"] == "sk-new"
    assert provider["base_url"] == "https://api.new.test"
    assert provider["last_test_status"] == "untested"
    assert provider["available_models"] == []

    restored = client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {
                    "id": "openai-default",
                    "name": "OpenAI",
                    "api_key": "sk-old",
                    "base_url": "https://api.old.test",
                    "provider_type": "openai_compatible",
                }
            ]
        },
    )
    restored_provider = restored.json()["providers"][0]
    assert restored_provider["last_test_status"] == "ok"
    assert _model_ids(restored_provider["available_models"]) == ["gpt-5"]


def test_provider_test_persists_model_capabilities_to_credentials(
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
                    "id": "openai-default",
                    "name": "OpenAI",
                    "api_key": "sk",
                    "base_url": "https://api.openai.com",
                    "provider_type": "openai_compatible",
                }
            ]
        },
    )

    async def fake_sdks(*_args: object, **_kwargs: object) -> list[str]:
        return ["openai_compatible"]

    async def fake_models(*_args: object, **_kwargs: object) -> list[ModelInfo]:
        return [
            _model_with_capabilities(
                "gpt-5",
                {"max_context_tokens": 128000, "custom_vendor_flag": True},
            )
        ]

    monkeypatch.setattr(llm_router, "probe_compatible_sdks", fake_sdks)
    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "openai-default",
            "provider_type": "openai_compatible",
            "api_key": "sk",
            "base_url": "https://api.openai.com",
        },
    )
    assert response.status_code == 200
    assert response.json()["available_models"][0]["capabilities"] == {
        "max_context_tokens": 128000,
        "custom_vendor_flag": True,
    }

    provider = client.get("/api/llm/credentials").json()["providers"][0]
    assert provider["available_models"][0]["capabilities"] == {
        "max_context_tokens": 128000,
        "custom_vendor_flag": True,
    }


def test_provider_test_model_list_success_does_not_require_sdk_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    sdk_calls: list[bool] = []

    async def empty_sdks(*_args: object, **_kwargs: object) -> list[str]:
        sdk_calls.append(True)
        return []

    async def fake_models(*_args: object, **_kwargs: object) -> list[ModelInfo]:
        return [_model("gpt-5")]

    monkeypatch.setattr(llm_router, "probe_compatible_sdks", empty_sdks)
    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "openai-default",
            "provider_type": "openai_compatible",
            "api_key": "sk",
            "base_url": "https://api.openai.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["error_code"] is None
    assert body["available_sdks"] == ["openai_compatible"]
    assert _model_ids(body["available_models"]) == ["gpt-5"]
    assert sdk_calls == []


def test_provider_test_persists_outcome_to_credentials(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    # Seed an existing provider so writeback has a target.
    client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {
                    "id": "OC_CL",
                    "name": "Claude",
                    "api_key": "sk",
                    "base_url": "",
                    "provider_type": "anthropic_compatible",
                }
            ]
        },
    )

    async def fake_sdks(*_args: object, **_kwargs: object) -> list[str]:
        return ["anthropic_compatible"]

    async def fake_models(*_args: object, **_kwargs: object) -> list[ModelInfo]:
        return [_model("claude-opus-4-1"), _model("claude-haiku-4-5")]

    monkeypatch.setattr(llm_router, "probe_compatible_sdks", fake_sdks)
    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "sk",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["available_sdks"] == ["anthropic_compatible"]
    assert _model_ids(body["available_models"]) == [
        "claude-opus-4-1",
        "claude-haiku-4-5",
    ]

    # Verify the writeback is now visible on a GET.
    get_response = client.get("/api/llm/credentials")
    provider = get_response.json()["providers"][0]
    assert provider["last_test_status"] == "ok"
    assert provider["available_sdks"] == ["anthropic_compatible"]
    assert _model_ids(provider["available_models"]) == [
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

    async def fake_sdks(*_args: object, **_kwargs: object) -> list[str]:
        return ["anthropic_compatible"]

    async def fake_models(*_args: object, **_kwargs: object) -> list[ModelInfo]:
        return []

    monkeypatch.setattr(llm_router, "probe_compatible_sdks", fake_sdks)
    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "NEW_CODE",
            "provider_type": "anthropic_compatible",
            "api_key": "sk",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # No credentials file is created when there's nothing to update.


def test_get_provider_notable_models_reads_section_4(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_dir = tmp_path / "llm_providers"
    docs_dir.mkdir()
    (docs_dir / "anthropic.md").write_text(
        """# Anthropic

## §3 Endpoint

Ignored.

## §4. Notable Model IDs

- `claude-opus-4-1`
- `claude-sonnet-4-7`
- `claude-opus-4-1`

## §5 Capabilities
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_router, "DOCS_DIR", docs_dir)

    response = client.get("/api/llm/providers/notable-models?provider_key=anthropic")

    assert response.status_code == 200
    assert response.json() == {"notable_models": ["claude-opus-4-1", "claude-sonnet-4-7"]}


def test_get_provider_notable_models_unknown_provider_returns_404(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_router, "DOCS_DIR", tmp_path)

    response = client.get("/api/llm/providers/notable-models?provider_key=missing")

    assert response.status_code == 404


def test_provider_test_models_appends_ok_models_and_dedupes(
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
                    "id": "openai-default",
                    "name": "OpenAI",
                    "api_key": "sk",
                    "base_url": "https://api.openai.com/v1",
                    "provider_type": "openai_compatible",
                }
            ]
        },
    )

    async def fake_probe(
        provider_type: str,
        api_key: str,
        base_url: str,
        model_id: str,
        auth_header_template: str | None = None,
    ) -> Any:
        del auth_header_template
        assert provider_type == "openai_compatible"
        assert api_key == "sk"
        assert base_url == "https://api.openai.com/v1"
        from app.services.llm_provider_test import ModelProbeResult

        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=3)

    monkeypatch.setattr(llm_router, "probe_model_id", fake_probe)

    response = client.post(
        "/api/llm/providers/test-models",
        json={"provider_id": "openai-default", "model_ids": ["gpt-5", "gpt-5", "gpt-4o"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert [result["model_id"] for result in body["results"]] == ["gpt-5", "gpt-4o"]
    assert [model["id"] for model in body["available_models"]] == ["gpt-5", "gpt-4o"]
    provider = client.get("/api/llm/credentials").json()["providers"][0]
    assert [model["id"] for model in provider["available_models"]] == ["gpt-5", "gpt-4o"]


def test_provider_test_models_partial_failures_append_only_ok(
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
                    "id": "openai-default",
                    "name": "OpenAI",
                    "api_key": "sk",
                    "provider_type": "openai_compatible",
                }
            ]
        },
    )

    async def fake_probe(*_args: object, **_kwargs: object) -> Any:
        from app.services.llm_provider_test import ModelProbeResult

        model_id = str(_args[3])
        if model_id == "bad-model":
            return ModelProbeResult(model_id=model_id, status="invalid_model", message="not found")
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=5)

    monkeypatch.setattr(llm_router, "probe_model_id", fake_probe)

    response = client.post(
        "/api/llm/providers/test-models",
        json={"provider_id": "openai-default", "model_ids": ["gpt-5", "bad-model"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert [result["status"] for result in body["results"]] == ["ok", "invalid_model"]
    assert [model["id"] for model in body["available_models"]] == ["gpt-5"]
    provider = client.get("/api/llm/credentials").json()["providers"][0]
    assert [model["id"] for model in provider["available_models"]] == ["gpt-5"]


def test_provider_test_models_unknown_provider_returns_404(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.post(
        "/api/llm/providers/test-models",
        json={"provider_id": "missing", "model_ids": ["gpt-5"]},
    )

    assert response.status_code == 404


def test_provider_test_models_preserves_existing_models(
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
                    "id": "openai-default",
                    "name": "OpenAI",
                    "api_key": "sk",
                    "provider_type": "openai_compatible",
                }
            ]
        },
    )
    from app.services.llm_credentials import _persist_test_outcome

    _persist_test_outcome(
        "openai-default",
        last_test_status="ok",
        last_test_at="2026-05-19T00:00:00+00:00",
        available_models=[ModelInfo(id="gpt-5")],
    )

    async def fake_probe(*_args: object, **_kwargs: object) -> Any:
        from app.services.llm_provider_test import ModelProbeResult

        return ModelProbeResult(model_id=str(_args[3]), status="ok", latency_ms=5)

    monkeypatch.setattr(llm_router, "probe_model_id", fake_probe)

    response = client.post(
        "/api/llm/providers/test-models",
        json={"provider_id": "openai-default", "model_ids": ["gpt-5", "claude-opus-4-7"]},
    )

    assert response.status_code == 200
    assert [model["id"] for model in response.json()["available_models"]] == [
        "gpt-5",
        "claude-opus-4-7",
    ]


def test_provider_test_models_normalizes_openrouter_model_prefixes(
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
                    "id": "openrouter-default",
                    "name": "OpenRouter",
                    "api_key": "sk",
                    "base_url": "https://openrouter.ai/api/v1",
                    "provider_type": "openai_compatible",
                }
            ]
        },
    )

    async def fake_probe(*_args: object, **_kwargs: object) -> Any:
        from app.services.llm_provider_test import ModelProbeResult

        return ModelProbeResult(model_id=str(_args[3]), status="ok", latency_ms=5)

    monkeypatch.setattr(llm_router, "probe_model_id", fake_probe)

    response = client.post(
        "/api/llm/providers/test-models",
        json={
            "provider_id": "openrouter-default",
            "model_ids": ["~anthropic/claude-sonnet-latest", "anthropic/claude-sonnet-latest"],
        },
    )

    assert response.status_code == 200
    assert [model["id"] for model in response.json()["available_models"]] == [
        "claude-sonnet-latest",
    ]
    provider = client.get("/api/llm/credentials").json()["providers"][0]
    assert [model["id"] for model in provider["available_models"]] == [
        "claude-sonnet-latest",
    ]
