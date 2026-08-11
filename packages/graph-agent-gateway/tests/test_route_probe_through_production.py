"""The route probe asks the way a run asks.

A probe exists to predict a call. While it hand-rolled its own request it was
predicting a request nobody was going to send: production builds a LangChain
model through `RouteChatModelFactory` for every protocol a route can declare.
So the probe builds its model the same way and pays for one token, and what it
learns from a failure it learns from the exception that call raises.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from graph_agent_gateway.probing import probe_provider_route
from graph_agent_gateway.registry import ProviderEndpoint, ProviderRoute
from pydantic import SecretStr


def _endpoint(protocol: str = "openai_compatible") -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id="endpoint-one",
        protocol=protocol,  # type: ignore[arg-type]
        base_url="https://host.example/v1",
        api_key=SecretStr("SECRET"),
    )


def _route() -> ProviderRoute:
    return ProviderRoute(
        route_id="endpoint-one:m-1",
        endpoint_id="endpoint-one",
        route_slug="m-1",
        provider_model_id="m-1",
    )


class _FactorySpy:
    """Stands in for `RouteChatModelFactory`, and records what it was asked for."""

    def __init__(self, model: Any) -> None:
        self.model = model
        self.builds: list[dict[str, Any]] = []

    def build(self, route: Any, **kwargs: Any) -> Any:
        self.builds.append({"route_id": route.route_id, "kwargs": kwargs})
        return self.model


class _RaisingModel:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        raise self.exc


@pytest.mark.anyio
async def test_the_probe_builds_its_model_through_the_factory() -> None:
    import openai

    request = httpx.Request("POST", "https://host.example/v1/chat/completions")
    exc = openai.AuthenticationError(
        "bad key",
        response=httpx.Response(401, json={"error": {"message": "bad key"}}, request=request),
        body=None,
    )
    factory = _FactorySpy(_RaisingModel(exc))

    result = await probe_provider_route(_endpoint(), _route(), factory=factory)

    assert [build["route_id"] for build in factory.builds] == ["endpoint-one:m-1"]
    assert result.status == "invalid_key"


@pytest.mark.anyio
async def test_a_probe_pays_for_one_token() -> None:
    import openai

    request = httpx.Request("POST", "https://host.example/v1/chat/completions")
    exc = openai.AuthenticationError(
        "bad key",
        response=httpx.Response(401, json={}, request=request),
        body=None,
    )
    factory = _FactorySpy(_RaisingModel(exc))

    await probe_provider_route(_endpoint(), _route(), factory=factory)

    assert factory.builds[0]["kwargs"]["max_tokens"] == 1
