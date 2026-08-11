"""What the endpoint and route probes put on the wire, pinned byte for byte.

``test_provider_endpoint`` and ``test_provider_route`` do not know which call
method they are testing. They infer a vendor from the endpoint's hostname and,
failing that, from the name the user typed — so the recorded matrix below is
protocol × host × endpoint id, and it shows the inference overruling the
declared protocol: an ``anthropic_compatible`` endpoint on a deepseek host is
probed with an OpenAI chat request, and an ``openai_compatible`` endpoint keeps
its wire but changes its token budget field when the user names it "deepseek".

Replacing that inference with the call-method catalog will change some of these
requests. That is the point, and it must be visible: re-record the baseline in
the same commit that changes it, so the diff on this fixture is the review of
the wire change.

Regenerate with: uv run python <scratchpad>/dump_endpoint_wire.py

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
(B3, D6)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from graph_agent_gateway.registry import ProviderEndpoint, ProviderRoute

# Aliased on import: these two are named `test_*`, so pytest collects them as
# tests wherever they are imported under their own names.
from graph_agent_gateway.registry.provider_probe import (
    test_provider_endpoint as probe_provider_endpoint,
)
from graph_agent_gateway.registry.provider_probe import (
    test_provider_route as probe_provider_route,
)

BASELINE = json.loads(
    (Path(__file__).parent / "data" / "endpoint_probe_wire_baseline.json").read_text(
        encoding="utf-8"
    )
)

_RECORDED_HEADERS = ("authorization", "x-api-key", "anthropic-version")
_HOSTS = {
    "neutral": "https://host.example/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "ark": "https://ark.cn-beijing.volces.com/api/v3",
    "openrouter": "https://openrouter.ai/api/v1",
}
_ENDPOINT_IDS = {"plain-id": "ep-one", "deepseek-id": "ep-deepseek-fast"}
_CASES: dict[str, dict[str, Any] | None] = {
    "plain": None,
    "effort_high": {"max_output_tokens": 16, "reasoning": {"enabled": True, "effort": "high"}},
    "reasoning_on_no_effort": {"max_output_tokens": 16, "reasoning": {"enabled": True}},
    "budget": {"max_output_tokens": 1025, "reasoning": {"enabled": True, "budget_tokens": 1024}},
}


def _endpoint(protocol: str, host: str, id_key: str) -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id=_ENDPOINT_IDS[id_key],
        protocol=protocol,  # type: ignore[arg-type]
        base_url=_HOSTS[host],
    )


async def _wire_for(case_key: str) -> dict[str, object]:
    probe, protocol, host, id_key, *rest = case_key.split("|")
    endpoint = _endpoint(protocol, host, id_key)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = {
            key: value for key, value in request.headers.items() if key in _RECORDED_HEADERS
        }
        captured["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(200, json={"data": []}, request=request)

    transport = httpx.MockTransport(handler)
    if probe == "endpoint":
        endpoint_result = await probe_provider_endpoint(
            endpoint, api_key="SECRET", transport=transport
        )
        return {**captured, "backend": endpoint_result.backend}

    route_result = await probe_provider_route(
        endpoint,
        ProviderRoute(
            route_id=f"{endpoint.endpoint_id}:m-1",
            endpoint_id=endpoint.endpoint_id,
            route_slug="m-1",
            provider_model_id="m-1",
        ),
        api_key="SECRET",
        runtime_settings=_CASES[rest[0]],
        transport=transport,
    )
    return {**captured, "backend": route_result.backend}


@pytest.mark.anyio
@pytest.mark.parametrize("case_key", sorted(BASELINE))
async def test_endpoint_probe_request_matches_the_recorded_wire(case_key: str) -> None:
    assert await _wire_for(case_key) == BASELINE[case_key]


def test_the_baseline_covers_every_protocol_on_every_recorded_host() -> None:
    from graph_agent_gateway.registry import Protocol

    protocols = {key.split("|")[1] for key in BASELINE}
    hosts = {key.split("|")[2] for key in BASELINE}

    assert protocols == set(Protocol.__args__)  # type: ignore[attr-defined]
    assert hosts == set(_HOSTS)
