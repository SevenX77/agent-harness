"""Gateway-owned provider endpoint and route probe contract tests."""

from __future__ import annotations

import json

import httpx
import pytest
from graph_agent_gateway.registry import provider_probe
from graph_agent_gateway.registry.schema import ProviderEndpoint, ProviderRoute
from pydantic import SecretStr


@pytest.mark.anyio
async def test_gateway_endpoint_test_accepts_third_party_provider() -> None:
    from graph_agent_gateway.registry.provider_probe import test_provider_endpoint

    endpoint = ProviderEndpoint(
        endpoint_id="openrouter",
        protocol="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )
    requests: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((str(request.url), request.headers.get("authorization")))
        return httpx.Response(
            200,
            json={"data": [{"id": "anthropic/claude-sonnet"}, {"id": "openai/gpt-5"}]},
            request=request,
        )

    result = await test_provider_endpoint(
        endpoint,
        transport=httpx.MockTransport(handler),
    )

    assert result.endpoint_id == "openrouter"
    assert result.provider_kind == "third_party"
    assert result.status == "ok"
    assert result.model_ids == ("anthropic/claude-sonnet", "openai/gpt-5")
    assert requests == [("https://openrouter.ai/api/v1/models", "Bearer secret")]


@pytest.mark.anyio
async def test_gateway_route_test_is_scoped_to_provider_route() -> None:
    from graph_agent_gateway.registry.provider_probe import test_provider_route

    endpoint = ProviderEndpoint(
        endpoint_id="openrouter",
        protocol="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )
    route = ProviderRoute(
        route_id="openrouter:anthropic.claude-sonnet",
        endpoint_id="openrouter",
        route_slug="anthropic.claude-sonnet",
        provider_model_id="anthropic/claude-sonnet",
        canonical_id="claude-sonnet",
    )
    requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((str(request.url), json.loads(request.content.decode())))
        return httpx.Response(200, json={"id": "chatcmpl-ok"}, request=request)

    result = await test_provider_route(
        endpoint,
        route,
        transport=httpx.MockTransport(handler),
    )

    assert result.endpoint_id == "openrouter"
    assert result.route_id == "openrouter:anthropic.claude-sonnet"
    assert result.provider_kind == "third_party"
    assert result.model_id == "anthropic/claude-sonnet"
    assert result.status == "ok"
    assert requests == [
        (
            "https://openrouter.ai/api/v1/chat/completions",
            {
                "model": "anthropic/claude-sonnet",
                "messages": [{"role": "user", "content": "."}],
                "max_completion_tokens": 1,
            },
        )
    ]


@pytest.mark.anyio
async def test_gateway_route_probe_billing_400_is_quota_exceeded_not_invalid_model() -> None:
    """An exhausted account balance must classify as structural quota_exceeded.

    Anthropic reports "credit balance is too low" as HTTP 400 invalid_request_error,
    which the plain status-code mapping would misread as a model-level
    invalid_model. Billing failures hit every model on the endpoint, so they must
    surface as quota_exceeded (endpoint-structural), not invalid_model.
    """
    from graph_agent_gateway.registry.provider_probe import test_provider_route

    endpoint = ProviderEndpoint(
        endpoint_id="anthropic-official",
        protocol="anthropic_compatible",
        base_url="https://api.anthropic.com",
        api_key=SecretStr("secret"),
        provider_kind="official",
    )
    route = ProviderRoute(
        route_id="anthropic-official:claude-opus-4.8",
        endpoint_id="anthropic-official",
        route_slug="claude-opus-4.8",
        provider_model_id="claude-opus-4.8",
        canonical_id="claude-opus-4.8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": (
                        "Your credit balance is too low to access the Anthropic API. "
                        "Please go to Plans & Billing to upgrade or purchase credits."
                    ),
                },
            },
            request=request,
        )

    result = await test_provider_route(
        endpoint,
        route,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "quota_exceeded"
    assert result.message is not None
    assert "credit balance" in result.message


@pytest.mark.anyio
async def test_gateway_route_probe_capability_400_stays_invalid_model() -> None:
    """A genuine model-level 400 (bad model id / unsupported param) stays invalid_model."""
    from graph_agent_gateway.registry.provider_probe import test_provider_route

    endpoint = ProviderEndpoint(
        endpoint_id="anthropic-official",
        protocol="anthropic_compatible",
        base_url="https://api.anthropic.com",
        api_key=SecretStr("secret"),
        provider_kind="official",
    )
    route = ProviderRoute(
        route_id="anthropic-official:claude-fable-5",
        endpoint_id="anthropic-official",
        route_slug="claude-fable-5",
        provider_model_id="claude-fable-5",
        canonical_id="claude-fable-5",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "type": "error",
                "error": {
                    "type": "not_found_error",
                    "message": "Claude Fable 5 is not available. Please use Opus 4.8.",
                },
            },
            request=request,
        )

    result = await test_provider_route(
        endpoint,
        route,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "invalid_model"


@pytest.mark.anyio
async def test_gateway_route_probe_path_404_is_protocol_unsupported() -> None:
    """A path-level 404 (no provider-shaped error payload) means the URL does not
    speak this protocol at all — it must classify as protocol_unsupported, never
    as a model-level invalid_model. Live signature (qiniu, 2026-07-02):
    google_genai probe of api.qnaigc.com/v1 answered a plain-text
    "not found or method not allowed"."""
    from graph_agent_gateway.registry.provider_probe import test_provider_route

    endpoint = ProviderEndpoint(
        endpoint_id="qiniu-google",
        protocol="google_genai",
        base_url="https://api.qnaigc.com/v1",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )
    route = ProviderRoute(
        route_id="qiniu-google:gemini-2.5-pro",
        endpoint_id="qiniu-google",
        route_slug="gemini-2.5-pro",
        provider_model_id="gemini-2.5-pro",
        canonical_id="gemini-2.5-pro",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found or method not allowed", request=request)

    result = await test_provider_route(
        endpoint,
        route,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "protocol_unsupported"


@pytest.mark.anyio
async def test_gateway_route_probe_model_shaped_404_stays_invalid_model() -> None:
    """A 404 wrapped in the provider's own error schema proves the protocol
    reached the provider — the model id is what failed, so invalid_model."""
    from graph_agent_gateway.registry.provider_probe import test_provider_route

    endpoint = ProviderEndpoint(
        endpoint_id="openai-official",
        protocol="openai_compatible",
        base_url="https://api.openai.com",
        api_key=SecretStr("secret"),
        provider_kind="official",
    )
    route = ProviderRoute(
        route_id="openai-official:gpt-nonexistent",
        endpoint_id="openai-official",
        route_slug="gpt-nonexistent",
        provider_model_id="gpt-nonexistent",
        canonical_id="gpt-nonexistent",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "message": "The model `gpt-nonexistent` does not exist or you do not have access to it.",
                    "type": "invalid_request_error",
                    "code": "model_not_found",
                }
            },
            request=request,
        )

    result = await test_provider_route(
        endpoint,
        route,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "invalid_model"


@pytest.mark.anyio
async def test_gateway_route_probe_wrong_protocol_guidance_is_protocol_unsupported() -> None:
    """Explicit wrong-endpoint guidance is a protocol mismatch regardless of the
    HTTP status. Live signature (design §1.2 / live-verified 2026-06-02):
    POST /v1/chat/completions on anthropic.qnaigc.com answers HTTP 500
    "Use /v1/messages instead"."""
    from graph_agent_gateway.registry.provider_probe import test_provider_route

    endpoint = ProviderEndpoint(
        endpoint_id="qiniu-anthropic-host-openai",
        protocol="openai_compatible",
        base_url="https://anthropic.qnaigc.com",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )
    route = ProviderRoute(
        route_id="qiniu-anthropic-host-openai:z-ai.glm-5.1",
        endpoint_id="qiniu-anthropic-host-openai",
        route_slug="z-ai.glm-5.1",
        provider_model_id="z-ai/glm-5.1",
        canonical_id="z-ai.glm-5.1",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"error": {"message": "Use /v1/messages instead", "type": "invalid_request_error"}},
            request=request,
        )

    result = await test_provider_route(
        endpoint,
        route,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "protocol_unsupported"


@pytest.mark.anyio
async def test_gateway_endpoint_test_path_404_is_protocol_unsupported() -> None:
    """The get-models call hitting a path-level 404 is the same protocol-mismatch
    fact at the endpoint level — not a generic error."""
    from graph_agent_gateway.registry.provider_probe import test_provider_endpoint

    endpoint = ProviderEndpoint(
        endpoint_id="qiniu-google",
        protocol="google_genai",
        base_url="https://api.qnaigc.com/v1",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found or method not allowed", request=request)

    result = await test_provider_endpoint(
        endpoint,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "protocol_unsupported"
    assert result.error_code == "protocol_unsupported"


@pytest.mark.anyio
async def test_gateway_route_probe_405_is_protocol_unsupported() -> None:
    """405 Method Not Allowed = the path exists but not for this protocol's verb."""
    from graph_agent_gateway.registry.provider_probe import test_provider_route

    endpoint = ProviderEndpoint(
        endpoint_id="qiniu-google",
        protocol="google_genai",
        base_url="https://api.qnaigc.com/v1",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )
    route = ProviderRoute(
        route_id="qiniu-google:gemini-2.5-pro",
        endpoint_id="qiniu-google",
        route_slug="gemini-2.5-pro",
        provider_model_id="gemini-2.5-pro",
        canonical_id="gemini-2.5-pro",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(405, text="method not allowed", request=request)

    result = await test_provider_route(
        endpoint,
        route,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "protocol_unsupported"


def test_gateway_official_call_method_timeout_allows_slow_openai_pro_responses() -> None:
    timeout = provider_probe._official_call_method_timeout(
        "openai_responses",
        "gpt-5-pro-2025-10-06",
        {"reasoning": {"effort": "high"}},
    )

    assert timeout == 180.0


# ── 多模态能力真探测(#11 slice A) ──────────────────────────────────────────
# 判据:多模态探测 = 在文本探测的用户消息里加一张测试图,provider 接受(2xx)=
# 该模型接受图像输入(input_modalities 含 image);不支持 vision 的模型会 4xx。
# 各协议图块格式不同,逐协议断言 payload 结构正确。


def _capture_multimodal_payload(method_id: str, model_id: str = "vision-model") -> dict[str, object]:
    import asyncio

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode()))
        return httpx.Response(200, json={"id": "ok"}, request=request)

    result = asyncio.run(
        provider_probe.probe_official_call_method(
            method_id,  # type: ignore[arg-type]
            "secret",
            "https://api.example.com",
            model_id,
            transport=httpx.MockTransport(handler),
            multimodal=True,
        )
    )
    assert result.status == "ok"
    return captured


def test_multimodal_probe_openai_chat_embeds_image_url_block() -> None:
    payload = _capture_multimodal_payload("openai_chat_completions")
    content = payload["messages"][0]["content"]  # type: ignore[index]
    assert isinstance(content, list)
    kinds = {block["type"] for block in content}
    assert kinds == {"text", "image_url"}
    image_block = next(b for b in content if b["type"] == "image_url")
    assert image_block["image_url"]["url"].startswith("data:image/png;base64,")


def test_multimodal_probe_anthropic_embeds_image_block() -> None:
    payload = _capture_multimodal_payload("anthropic_messages")
    content = payload["messages"][0]["content"]  # type: ignore[index]
    assert isinstance(content, list)
    image_block = next(b for b in content if b["type"] == "image")
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    assert image_block["source"]["data"]


def test_multimodal_probe_gemini_embeds_inline_data_part() -> None:
    payload = _capture_multimodal_payload("gemini_generate_content")
    parts = payload["contents"][0]["parts"]  # type: ignore[index]
    inline = next(p for p in parts if "inline_data" in p)
    assert inline["inline_data"]["mime_type"] == "image/png"
    assert inline["inline_data"]["data"]


def test_multimodal_probe_openai_responses_embeds_input_image() -> None:
    payload = _capture_multimodal_payload("openai_responses")
    content = payload["input"][0]["content"]  # type: ignore[index]
    kinds = {block["type"] for block in content}
    assert kinds == {"input_text", "input_image"}


def test_multimodal_probe_rejects_completions_method() -> None:
    import asyncio

    # 老式 /v1/completions 无多模态能力 → 诚实报错,不静默发一个没图的探测。
    with pytest.raises(ValueError, match="completions"):
        asyncio.run(
            provider_probe.probe_official_call_method(
                "openai_completions",
                "secret",
                "https://api.example.com",
                "text-model",
                transport=httpx.MockTransport(lambda r: httpx.Response(200, request=r)),
                multimodal=True,
            )
        )


def test_text_probe_unchanged_when_not_multimodal() -> None:
    # 回归:multimodal=False 时 payload 与既有文本探测完全一致(不带图)。
    import asyncio

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode()))
        return httpx.Response(200, json={"id": "ok"}, request=request)

    asyncio.run(
        provider_probe.probe_official_call_method(
            "openai_chat_completions",
            "secret",
            "https://api.example.com",
            "text-model",
            transport=httpx.MockTransport(handler),
        )
    )
    assert captured["messages"][0]["content"] == "Reply with one short word."  # type: ignore[index]
