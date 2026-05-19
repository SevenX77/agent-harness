from __future__ import annotations

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


def test_render_auth_headers_anthropic_multiline() -> None:
    from app.services.llm_provider_test import _render_auth_headers

    template = "x-api-key: ${key}\nanthropic-version: 2023-06-01"

    headers = _render_auth_headers(template, "sk-ant-test")

    assert headers == {
        "x-api-key": "sk-ant-test",
        "anthropic-version": "2023-06-01",
    }


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
        ("gemini_official", "_probe_gemini_1token"),
        ("wavespeed_any_llm", "_probe_wavespeed_1token"),
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
