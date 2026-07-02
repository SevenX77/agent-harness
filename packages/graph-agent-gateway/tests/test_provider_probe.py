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


def test_gateway_official_call_method_timeout_allows_slow_openai_pro_responses() -> None:
    timeout = provider_probe._official_call_method_timeout(
        "openai_responses",
        "gpt-5-pro-2025-10-06",
        {"reasoning": {"effort": "high"}},
    )

    assert timeout == 180.0
