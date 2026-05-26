from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from services.llm_provider_meta import ProviderMeta


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "expected_in"),
    [
        (200, True),
        (400, True),
        (422, True),
        (401, False),
        (403, False),
        (500, False),
    ],
)
async def test_probe_compatible_sdks_status_code_to_inclusion(
    status: int,
    expected_in: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="openai",
        compatible_sdks=["openai_compatible"],
        models_endpoint_path="/v1/models",
        auth_header_format="Authorization: Bearer ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)

    async def fake_send(
        sdk: str,
        api_key: str,
        base_url: str,
        auth_header_template: str,
    ) -> int:
        assert sdk == "openai_compatible"
        assert api_key == "sk-test"
        assert base_url == "https://api.openai.com/v1"
        assert auth_header_template == "Authorization: Bearer ${key}"
        return status

    monkeypatch.setattr(llm_provider_test, "_send_1_token_request", fake_send)

    result = await llm_provider_test.probe_compatible_sdks(
        "openai", "sk-test", "https://api.openai.com/v1"
    )

    assert ("openai_compatible" in result) is expected_in


@pytest.mark.anyio
async def test_probe_compatible_sdks_uses_models_endpoint_when_probe_model_is_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="openai",
        compatible_sdks=["openai_compatible"],
        models_endpoint_path="/v1/models",
        auth_header_format="Authorization: Bearer ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)

    async def fake_send(*_args: object, **_kwargs: object) -> int:
        return 404

    monkeypatch.setattr(llm_provider_test, "_send_1_token_request", fake_send)
    _patch_async_client_get(
        monkeypatch,
        expected_url="https://api.openai.com/v1/models",
        expected_headers={"Authorization": "Bearer sk-test"},
        response=httpx.Response(
            200,
            json={"data": [{"id": "gpt-5"}]},
            request=httpx.Request("GET", "https://api.openai.com/v1/models"),
        ),
    )

    result = await llm_provider_test.probe_compatible_sdks(
        "openai", "sk-test", "https://api.openai.com"
    )

    assert result == ["openai_compatible"]


def test_render_auth_headers_anthropic_multiline() -> None:
    from app.services.llm_provider_test import _render_auth_headers

    template = "x-api-key: ${key}\nanthropic-version: 2023-06-01"

    headers = _render_auth_headers(template, "sk-ant-test")

    assert headers == {
        "x-api-key": "sk-ant-test",
        "anthropic-version": "2023-06-01",
    }


def test_join_base_url_and_endpoint_deduplicates_version_prefix() -> None:
    from app.services.llm_provider_test import _join_base_url_and_endpoint

    assert (
        _join_base_url_and_endpoint(
            "https://llm.wavespeed.ai/v1",
            "/v1/chat/completions",
        )
        == "https://llm.wavespeed.ai/v1/chat/completions"
    )
    assert (
        _join_base_url_and_endpoint(
            "https://openrouter.ai/api/v1",
            "/v1/chat/completions",
        )
        == "https://openrouter.ai/api/v1/chat/completions"
    )


@pytest.mark.anyio
async def test_probe_compatible_sdks_unknown_sdk_is_handled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="x",
        compatible_sdks=["unknown_sdk"],
        models_endpoint_path=None,
        auth_header_format="x-api-key: ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)

    result = await llm_provider_test.probe_compatible_sdks("x", "k", "https://x.test")

    assert result == []


@pytest.mark.anyio
async def test_probe_compatible_sdks_send_exception_is_handled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="openai",
        compatible_sdks=["openai_compatible"],
        models_endpoint_path="/v1/models",
        auth_header_format="Authorization: Bearer ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)

    async def raises(*_args: object, **_kwargs: object) -> int:
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(llm_provider_test, "_send_1_token_request", raises)

    result = await llm_provider_test.probe_compatible_sdks(
        "openai", "sk-test", "https://api.openai.com/v1"
    )

    assert result == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("sdk", "probe_name"),
    [
        ("openai_compatible", "_probe_openai_1token"),
        ("anthropic_compatible", "_probe_anthropic_1token"),
        ("google_genai", "_probe_google_genai_1token"),
    ],
)
async def test_send_1_token_request_dispatches_to_sdk_probe(
    sdk: str,
    probe_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    calls: list[tuple[str, dict[str, str]]] = []

    async def fake_probe(base_url: str, headers: dict[str, str]) -> int:
        calls.append((base_url, headers))
        return 200

    monkeypatch.setattr(llm_provider_test, probe_name, fake_probe)

    status = await llm_provider_test._send_1_token_request(
        sdk,
        "sk-test",
        "https://provider.test",
        "Authorization: Bearer ${key}",
    )

    assert status == 200
    assert calls == [("https://provider.test", {"Authorization": "Bearer sk-test"})]


@pytest.mark.anyio
async def test_probe_available_models_openai_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="openai",
        compatible_sdks=["openai_compatible"],
        models_endpoint_path="/v1/models",
        auth_header_format="Authorization: Bearer ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)
    _patch_async_client_get(
        monkeypatch,
        expected_url="https://api.openai.com/v1/models",
        expected_headers={"Authorization": "Bearer sk-test"},
        response=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "gpt-4",
                        "max_context_tokens": 8192,
                        "capabilities": {"function_calling": True},
                    },
                    {"id": "gpt-5", "context_length": 128000},
                ]
            },
            request=httpx.Request("GET", "https://api.openai.com/v1/models"),
        ),
    )

    result = await llm_provider_test.probe_available_models(
        "openai", "sk-test", "https://api.openai.com"
    )

    assert [model.id for model in result] == ["gpt-4", "gpt-5"]
    assert result[0].capabilities["max_context_tokens"] == 8192
    assert result[0].capabilities["function_calling"] is True
    assert result[1].capabilities["max_context_tokens"] == 128000


@pytest.mark.anyio
async def test_probe_available_models_does_not_duplicate_endpoint_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="openai",
        compatible_sdks=["openai_compatible"],
        models_endpoint_path="/v1/models",
        auth_header_format="Authorization: Bearer ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)
    _patch_async_client_get(
        monkeypatch,
        expected_url="https://api.openai.com/v1/models",
        expected_headers={"Authorization": "Bearer sk-test"},
        response=httpx.Response(
            200,
            json={"data": [{"id": "gpt-4"}]},
            request=httpx.Request("GET", "https://api.openai.com/v1/models"),
        ),
    )

    result = await llm_provider_test.probe_available_models(
        "openai", "sk-test", "https://api.openai.com/v1"
    )

    assert [model.id for model in result] == ["gpt-4"]


@pytest.mark.anyio
async def test_probe_available_models_gemini_format_strips_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="gemini",
        compatible_sdks=["google_genai"],
        models_endpoint_path="/v1beta/models",
        auth_header_format="x-goog-api-key: ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)
    _patch_async_client_get(
        monkeypatch,
        expected_url="https://generativelanguage.googleapis.com/v1beta/models",
        expected_headers={"x-goog-api-key": "gemini-key"},
        response=httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-2.0-flash",
                        "inputTokenLimit": 1048576,
                        "outputTokenLimit": 8192,
                    },
                    {"name": "models/gemini-2.5-pro"},
                ]
            },
            request=httpx.Request("GET", "https://generativelanguage.googleapis.com/v1beta/models"),
        ),
    )

    result = await llm_provider_test.probe_available_models(
        "gemini", "gemini-key", "https://generativelanguage.googleapis.com"
    )

    assert [model.id for model in result] == ["gemini-2.0-flash", "gemini-2.5-pro"]
    assert result[0].capabilities["max_context_tokens"] == 1048576
    assert result[0].capabilities["max_output_tokens"] == 8192
    assert result[0].capabilities["inputTokenLimit"] == 1048576


@pytest.mark.anyio
async def test_probe_available_models_anthropic_collects_token_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="anthropic",
        compatible_sdks=["anthropic_compatible"],
        models_endpoint_path="/v1/models",
        auth_header_format="x-api-key: ${key}\nanthropic-version: 2023-06-01",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)
    _patch_async_client_get(
        monkeypatch,
        expected_url="https://api.anthropic.com/v1/models",
        expected_headers={
            "x-api-key": "sk-ant",
            "anthropic-version": "2023-06-01",
        },
        response=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "claude-sonnet-4-7",
                        "display_name": "Claude Sonnet 4.7",
                        "max_input_tokens": 200000,
                        "max_tokens": 64000,
                    }
                ]
            },
            request=httpx.Request("GET", "https://api.anthropic.com/v1/models"),
        ),
    )

    result = await llm_provider_test.probe_available_models(
        "anthropic", "sk-ant", "https://api.anthropic.com"
    )

    assert [model.id for model in result] == ["claude-sonnet-4-7"]
    assert result[0].capabilities["display_name"] == "Claude Sonnet 4.7"
    assert result[0].capabilities["max_context_tokens"] == 200000
    assert result[0].capabilities["max_output_tokens"] == 64000


@pytest.mark.anyio
async def test_probe_available_models_openrouter_context_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="openrouter",
        compatible_sdks=["openai_compatible"],
        models_endpoint_path="/api/v1/models",
        auth_header_format="Authorization: Bearer ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)
    _patch_async_client_get(
        monkeypatch,
        expected_url="https://openrouter.ai/api/v1/models",
        expected_headers={"Authorization": "Bearer or-key"},
        response=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "openai/gpt-4o",
                        "context_length": 128000,
                        "architecture": {"modality": "text+image->text"},
                    },
                    {
                        "id": "~openai/gpt-4o",
                        "context_length": 128000,
                    },
                    {
                        "id": "~anthropic/claude-sonnet-latest",
                        "context_length": 200000,
                    },
                ]
            },
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/models"),
        ),
    )

    result = await llm_provider_test.probe_available_models(
        "openrouter", "or-key", "https://openrouter.ai"
    )

    assert [model.id for model in result] == ["gpt-4o", "claude-sonnet-latest"]
    assert result[0].capabilities["provider_model_id"] == "openai/gpt-4o"
    assert result[0].capabilities["max_context_tokens"] == 128000
    assert result[0].capabilities["architecture"] == {"modality": "text+image->text"}


@pytest.mark.anyio
async def test_probe_available_models_uses_doc_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="anthropic",
        compatible_sdks=["anthropic_compatible"],
        models_endpoint_path=None,
        auth_header_format="x-api-key: ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)
    monkeypatch.setattr(llm_provider_test, "DOCS_DIR", tmp_path)
    (tmp_path / "anthropic.md").write_text(
        """## §3 Endpoint

Ignored.

## §4. Notable Model IDs

- `claude-opus-4-5-20251101`
- `claude-haiku-4-5-20251001`
- `claude-opus-4-5-20251101`

## §5 Capabilities
""",
        encoding="utf-8",
    )

    result = await llm_provider_test.probe_available_models(
        "anthropic", "sk-ant-test", "https://api.anthropic.com"
    )

    assert [model.id for model in result] == [
        "claude-opus-4-5-20251101",
        "claude-haiku-4-5-20251001",
    ]


@pytest.mark.anyio
async def test_probe_available_models_http_error_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="openai",
        compatible_sdks=["openai_compatible"],
        models_endpoint_path="/v1/models",
        auth_header_format="Authorization: Bearer ${key}",
    )
    url = "https://api.openai.com/v1/models"
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)
    _patch_async_client_get(
        monkeypatch,
        expected_url=url,
        expected_headers={"Authorization": "Bearer bad-key"},
        response=httpx.Response(
            401,
            json={"error": "auth"},
            request=httpx.Request("GET", url),
        ),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await llm_provider_test.probe_available_models(
            "openai", "bad-key", "https://api.openai.com"
        )


@pytest.mark.anyio
async def test_probe_available_models_unknown_response_format_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_provider_test

    fake_meta = ProviderMeta(
        vendor="x",
        compatible_sdks=[],
        models_endpoint_path="/list",
        auth_header_format="x-api-key: ${key}",
    )
    monkeypatch.setattr(llm_provider_test, "load_provider_meta", lambda _vendor: fake_meta)
    _patch_async_client_get(
        monkeypatch,
        expected_url="https://x.test/list",
        expected_headers={"x-api-key": "k"},
        response=httpx.Response(
            200,
            json={"items": [{"id": "m1"}]},
            request=httpx.Request("GET", "https://x.test/list"),
        ),
    )

    result = await llm_provider_test.probe_available_models("x", "k", "https://x.test")

    assert result == []


def _patch_async_client_get(
    monkeypatch: pytest.MonkeyPatch,
    *,
    expected_url: str,
    expected_headers: dict[str, str],
    response: httpx.Response,
) -> None:
    from app.services import llm_provider_test

    class FakeAsyncClient:
        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            timeout: float,
        ) -> httpx.Response:
            assert url == expected_url
            assert headers == expected_headers
            assert timeout == 15.0
            return response

    monkeypatch.setattr(llm_provider_test.httpx, "AsyncClient", FakeAsyncClient)
