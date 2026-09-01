"""Gateway-owned provider endpoint and route probe contract tests."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import openai
import pytest
from graph_agent_gateway.probing import wire as provider_probe
from graph_agent_gateway.registry import ProviderEndpoint, ProviderRoute
from langchain_core.messages import AIMessage
from pydantic import SecretStr


class _RaisingModel:
    """A model whose one call fails the way a provider SDK fails it."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def ainvoke(self, *args: object, **kwargs: object) -> object:
        raise self._exc


class _AnsweringModel:
    async def ainvoke(self, *args: object, **kwargs: object) -> object:
        return AIMessage(content="ok")


class _FactoryReturning:
    def __init__(self, model: object) -> None:
        self._model = model
        self.builds: list[tuple[object, dict[str, object]]] = []

    def build(self, route: object, **kwargs: object) -> object:
        self.builds.append((route, kwargs))
        return self._model


def _answering() -> _FactoryReturning:
    return _FactoryReturning(_AnsweringModel())


def _failing_with(handler: Callable[[httpx.Request], httpx.Response]) -> _FactoryReturning:
    """The factory a probe gets when the provider answers the way `handler` says.

    The route probe no longer sends its own request, so a refusal reaches it as
    the exception the provider's SDK raises — which carries that very response.
    Building the error from the same handler keeps these tests about what a given
    body means, which is the part the gateway owns.
    """

    response = handler(httpx.Request("POST", "https://provider.example/v1/messages"))
    return _FactoryReturning(
        _RaisingModel(openai.APIStatusError("provider refused", response=response, body=None))
    )


@pytest.mark.anyio
async def test_gateway_endpoint_test_accepts_third_party_provider() -> None:
    from graph_agent_gateway.probing import probe_provider_endpoint

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

    result = await probe_provider_endpoint(
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
    from graph_agent_gateway.probing import probe_provider_route

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
    factory = _answering()

    result = await probe_provider_route(endpoint, route, factory=factory)

    assert result.endpoint_id == "openrouter"
    assert result.route_id == "openrouter:anthropic.claude-sonnet"
    assert result.provider_kind == "third_party"
    assert result.model_id == "anthropic/claude-sonnet"
    assert result.status == "ok"

    # What the probe asks for is now the whole of what it sends: the request is
    # the factory's, and what the factory renders is measured in
    # tests/test_production_wire_contract.py.
    (asked_route, asked_kwargs), = factory.builds
    assert asked_route.route_id == "openrouter:anthropic.claude-sonnet"
    assert asked_route.provider_model_id == "anthropic/claude-sonnet"
    assert asked_route.protocol == "openai_compatible"
    assert asked_route.base_url == "https://openrouter.ai/api/v1"
    assert asked_kwargs["max_tokens"] == 1


@pytest.mark.anyio
async def test_gateway_route_probe_billing_400_is_quota_exceeded_not_invalid_model() -> None:
    """An exhausted account balance must classify as structural quota_exceeded.

    Anthropic reports "credit balance is too low" as HTTP 400 invalid_request_error,
    which the plain status-code mapping would misread as a model-level
    invalid_model. Billing failures hit every model on the endpoint, so they must
    surface as quota_exceeded (endpoint-structural), not invalid_model.
    """
    from graph_agent_gateway.probing import probe_provider_route

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

    result = await probe_provider_route(
        endpoint,
        route,
        factory=_failing_with(handler),
    )

    assert result.status == "quota_exceeded"
    assert result.message is not None
    assert "credit balance" in result.message


@pytest.mark.anyio
async def test_gateway_route_probe_capability_400_stays_invalid_model() -> None:
    """A genuine model-level 400 (bad model id / unsupported param) stays invalid_model."""
    from graph_agent_gateway.probing import probe_provider_route

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

    result = await probe_provider_route(
        endpoint,
        route,
        factory=_failing_with(handler),
    )

    assert result.status == "invalid_model"


@pytest.mark.anyio
async def test_gateway_route_probe_path_404_is_protocol_unsupported() -> None:
    """A path-level 404 (no provider-shaped error payload) means the URL does not
    speak this protocol at all — it must classify as protocol_unsupported, never
    as a model-level invalid_model. Live signature (qiniu, 2026-07-02):
    google_genai probe of api.qnaigc.com/v1 answered a plain-text
    "not found or method not allowed"."""
    from graph_agent_gateway.probing import probe_provider_route

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

    result = await probe_provider_route(
        endpoint,
        route,
        factory=_failing_with(handler),
    )

    assert result.status == "protocol_unsupported"


@pytest.mark.anyio
async def test_gateway_route_probe_model_shaped_404_stays_invalid_model() -> None:
    """A 404 wrapped in the provider's own error schema proves the protocol
    reached the provider — the model id is what failed, so invalid_model."""
    from graph_agent_gateway.probing import probe_provider_route

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

    result = await probe_provider_route(
        endpoint,
        route,
        factory=_failing_with(handler),
    )

    assert result.status == "invalid_model"


@pytest.mark.anyio
async def test_gateway_route_probe_wrong_protocol_guidance_is_protocol_unsupported() -> None:
    """Explicit wrong-endpoint guidance is a protocol mismatch regardless of the
    HTTP status. Live signature (design §1.2 / live-verified 2026-06-02):
    POST /v1/chat/completions on anthropic.qnaigc.com answers HTTP 500
    "Use /v1/messages instead"."""
    from graph_agent_gateway.probing import probe_provider_route

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

    result = await probe_provider_route(
        endpoint,
        route,
        factory=_failing_with(handler),
    )

    assert result.status == "protocol_unsupported"


@pytest.mark.anyio
async def test_gateway_endpoint_test_path_404_is_protocol_unsupported() -> None:
    """The get-models call hitting a path-level 404 is the same protocol-mismatch
    fact at the endpoint level — not a generic error."""
    from graph_agent_gateway.probing import probe_provider_endpoint

    endpoint = ProviderEndpoint(
        endpoint_id="qiniu-google",
        protocol="google_genai",
        base_url="https://api.qnaigc.com/v1",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found or method not allowed", request=request)

    result = await probe_provider_endpoint(
        endpoint,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "protocol_unsupported"
    assert result.error_code == "protocol_unsupported"


@pytest.mark.anyio
async def test_gateway_route_probe_405_is_protocol_unsupported() -> None:
    """405 Method Not Allowed = the path exists but not for this protocol's verb."""
    from graph_agent_gateway.probing import probe_provider_route

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

    result = await probe_provider_route(
        endpoint,
        route,
        factory=_failing_with(handler),
    )

    assert result.status == "protocol_unsupported"


@pytest.mark.anyio
async def test_gateway_endpoint_test_unsupported_fixed_route_is_protocol_unsupported() -> None:
    """A host that has no handler for the probed protocol's path answers with a
    route-level rejection, not a model error. Live signature (2026-07-02,
    anthropic.qnaigc.com × google): GET /v1beta/models -> HTTP 500
    {"type":"error","error":{"message":"Unsupported fixed route: /v1beta/models"}}.
    That is a (URL, protocol) fact, not a transient error."""
    from graph_agent_gateway.probing import probe_provider_endpoint

    endpoint = ProviderEndpoint(
        endpoint_id="qiniu-anthropic-host-google",
        protocol="google_genai",
        base_url="https://anthropic.qnaigc.com",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"type": "error", "error": {"type": "error", "message": "Unsupported fixed route: /v1beta/models"}},
            request=request,
        )

    result = await probe_provider_endpoint(endpoint, transport=httpx.MockTransport(handler))

    assert result.status == "protocol_unsupported"
    assert result.error_code == "protocol_unsupported"


@pytest.mark.anyio
async def test_gateway_endpoint_test_misrouted_to_foreign_protocol_is_protocol_unsupported() -> None:
    """A host with no backend for the probed protocol may silently misroute the
    request to a DIFFERENT protocol's upstream and surface that upstream's error.
    Live signature (2026-07-02, anthropic.qnaigc.com × google): the gemini probe
    500s wrapping "OpenAI API error: 401 invalid api key" — a google endpoint that
    answers with an OpenAI error proves it does not speak google."""
    from graph_agent_gateway.probing import probe_provider_endpoint

    endpoint = ProviderEndpoint(
        endpoint_id="qiniu-anthropic-host-google",
        protocol="google_genai",
        base_url="https://anthropic.qnaigc.com",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "type": "error",
                "error": {
                    "type": "error",
                    "message": 'OpenAI API error: 401 {"error":{"message":"invalid api key","type":"authentication_error"}}',
                },
            },
            request=request,
        )

    result = await probe_provider_endpoint(endpoint, transport=httpx.MockTransport(handler))

    assert result.status == "protocol_unsupported"
    assert result.error_code == "protocol_unsupported"


@pytest.mark.anyio
async def test_gateway_openai_probe_own_auth_error_stays_invalid_key() -> None:
    """A genuine OpenAI endpoint returning its OWN auth error must stay invalid_key —
    the misroute heuristic only fires when a DIFFERENT protocol's error surfaces, so
    it must not swallow real auth failures on the matching protocol."""
    from graph_agent_gateway.probing import probe_provider_route

    endpoint = ProviderEndpoint(
        endpoint_id="openai-real",
        protocol="openai_compatible",
        base_url="https://api.openai.example",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )
    route = ProviderRoute(
        route_id="openai-real:gpt-x",
        endpoint_id="openai-real",
        route_slug="gpt-x",
        provider_model_id="gpt-x",
        canonical_id="gpt-x",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "OpenAI API error: invalid api key", "type": "authentication_error"}},
            request=request,
        )

    result = await probe_provider_route(endpoint, route, factory=_failing_with(handler))

    assert result.status == "invalid_key"


@pytest.mark.anyio
async def test_deepseek_anthropic_probe_keeps_canonical_anthropic_base_path() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, json={"id": "ok"}, request=request)

    result = await provider_probe.probe_official_call_method(
        "deepseek_anthropic_messages",
        "secret",
        "https://api.deepseek.com/anthropic",
        "deepseek-v4-pro",
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "ok"
    assert requests == ["https://api.deepseek.com/anthropic/v1/messages"]


@pytest.mark.anyio
async def test_ark_openai_compatible_endpoint_probe_uses_existing_api_v3_models_path() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="ark-openai-official",
        protocol="openai_compatible",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key=SecretStr("secret"),
        provider_kind="official",
    )
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, json={"data": [{"id": "doubao-seed-2-0-pro-260215"}]}, request=request)

    result = await provider_probe.probe_provider_endpoint(
        endpoint,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "ok"
    assert result.model_ids == ("doubao-seed-2-0-pro-260215",)
    assert requests == ["https://ark.cn-beijing.volces.com/api/v3/models"]


@pytest.mark.anyio
async def test_ark_openai_compatible_route_probe_uses_existing_api_v3_chat_path() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="ark-openai-official",
        protocol="openai_compatible",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key=SecretStr("secret"),
        provider_kind="official",
    )
    route = ProviderRoute(
        route_id="ark-openai-official:doubao-seed-2-0-pro-260215",
        endpoint_id="ark-openai-official",
        route_slug="doubao-seed-2-0-pro-260215",
        provider_model_id="doubao-seed-2-0-pro-260215",
        canonical_id="doubao-seed-2-0-pro-260215",
    )
    factory = _answering()

    result = await provider_probe.probe_provider_route(endpoint, route, factory=factory)

    assert result.status == "ok"
    # An ARK host declared openai_compatible keeps the path the user gave: the
    # /api/v3 suffix belongs to the ark_runtime protocol's canonicalization, and
    # appending it again here would probe a URL that does not exist. The factory
    # is handed the base url untouched, and where it goes from there is
    # tests/test_route_chat_model_factory.py's to say.
    (asked_route, _), = factory.builds
    assert asked_route.base_url == "https://ark.cn-beijing.volces.com/api/v3"
    assert asked_route.protocol == "openai_compatible"


@pytest.mark.anyio
async def test_openai_official_call_method_uses_existing_api_v3_chat_path() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, json={"id": "chatcmpl-ok"}, request=request)

    result = await provider_probe.probe_official_call_method(
        "openai_chat_completions",
        "secret",
        "https://ark.cn-beijing.volces.com/api/v3",
        "doubao-seed-2-0-pro-260215",
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "ok"
    assert requests == ["https://ark.cn-beijing.volces.com/api/v3/chat/completions"]


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


@pytest.mark.anyio
async def test_official_method_probe_misrouted_to_foreign_protocol_is_protocol_unsupported() -> None:
    """The official-method probe must apply the same foreign-protocol correction the
    other two probe channels do.

    Design §1.2 protocol matrix point 2 supplement (PM 2026-07-02): "探 X 协议却收到
    Y 协议的 API 错误 = 该 URL 不说 X", and "此判据须早于 401 分支,否则异协议的 401
    会被误当成'我这把 key 失效'". `probe_provider_endpoint` and `probe_provider_route`
    both hand `probe_status` the wire they probed so it can make that call; the
    official channel did not, which silently turned the correction OFF for every
    official-method probe — a misroute there was reported as this key being invalid.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        # An anthropic_messages probe (backend `claude`) answered by an OpenAI
        # upstream: the host does not speak Anthropic's wire.
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": 'OpenAI API error: 401 {"error":{"message":"invalid api key"}}',
                    "type": "authentication_error",
                }
            },
            request=request,
        )

    result = await provider_probe.probe_official_call_method(
        "anthropic_messages",
        "secret",
        "https://anthropic.qnaigc.example",
        "claude-x",
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "protocol_unsupported"


@pytest.mark.anyio
@pytest.mark.parametrize(
    # NOT `base_url`: that name collides with pytest-base-url's session-scoped
    # fixture and the parametrized cases error out with ScopeMismatch.
    ("method_id", "probe_base_url", "model_id"),
    [
        ("ark_anthropic_messages", "https://ark.cn-beijing.volces.com", "doubao-x"),
        ("deepseek_anthropic_messages", "https://api.deepseek.com/anthropic", "deepseek-x"),
    ],
)
async def test_official_method_probe_uses_the_wire_not_the_vendor(
    method_id: str, probe_base_url: str, model_id: str
) -> None:
    """The correction must key off the WIRE the method speaks, not the vendor that
    publishes it.

    Ark and DeepSeek both publish Anthropic's `/v1/messages` wire. Their
    `provider_backend` is "ark" / "deepseek", and an OpenAI-shaped error is NATIVE
    to those two backends (`_FOREIGN_API_ERROR_SIGNATURES`), so handing
    `probe_status` the vendor leaves precisely these misroutes looking native — the
    argument would be present and still do nothing. `wire_family` says
    `anthropic_messages`, whose owner is `claude`, and an OpenAI error on Anthropic's
    wire is foreign.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": 'OpenAI API error: 401 {"error":{"message":"invalid api key"}}',
                    "type": "authentication_error",
                }
            },
            request=request,
        )

    result = await provider_probe.probe_official_call_method(
        method_id,
        "secret",
        probe_base_url,
        model_id,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "protocol_unsupported"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method_id", "probe_base_url", "model_id"),
    [
        ("ark_anthropic_messages", "https://ark.cn-beijing.volces.com", "doubao-x"),
        ("deepseek_anthropic_messages", "https://api.deepseek.com/anthropic", "deepseek-x"),
    ],
)
async def test_vendor_hosted_anthropic_wire_keeps_a_real_bad_key_as_invalid_key(
    method_id: str, probe_base_url: str, model_id: str
) -> None:
    """Passing the WIRE must not turn every 401 on a vendor-hosted Anthropic
    surface into a protocol verdict.

    The correction keys off a body that NAMES another protocol's API, not off the
    brand mismatch between wire and vendor. Ark's and DeepSeek's own auth
    rejections carry no such name, so they stay `invalid_key` — which is what keeps
    "fix your key" reachable on exactly the two methods whose wire and vendor
    differ.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Authentication failed", "type": "authentication_error"}},
            request=request,
        )

    result = await provider_probe.probe_official_call_method(
        method_id,
        "secret",
        probe_base_url,
        model_id,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "invalid_key"


@pytest.mark.anyio
async def test_official_method_probe_own_auth_error_stays_invalid_key() -> None:
    """The correction must not swallow a real auth failure on the MATCHING protocol:
    an anthropic_messages probe answered by Anthropic's own 401 is an invalid key,
    not a protocol mismatch (the mirror of
    test_gateway_openai_probe_own_auth_error_stays_invalid_key, for this channel)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "type": "error",
                "error": {"type": "authentication_error", "message": "invalid x-api-key"},
            },
            request=request,
        )

    result = await provider_probe.probe_official_call_method(
        "anthropic_messages",
        "secret",
        "https://api.anthropic.example",
        "claude-x",
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "invalid_key"
