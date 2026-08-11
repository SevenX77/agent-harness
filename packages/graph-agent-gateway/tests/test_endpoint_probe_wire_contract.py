"""What the endpoint probe puts on the wire, pinned byte for byte.

``probe_provider_endpoint`` asks for a model list with a request this package
builds, so the request is this package's to get right and worth recording:
protocol × host × endpoint id, showing that the declared protocol decides the
wire and the endpoint's name decides nothing.

The 80 route cases that used to live here are gone. The route probe no longer
builds a request — it asks through ``RouteChatModelFactory``, the same builder a
run uses, so what it sends is what a run sends and is measured directly off the
model in ``test_production_wire_contract.py``. Re-recording it here would mean
patching a private client on three different SDK objects to replay a wire whose
every field is already asserted somewhere it can be read without them. Of what those
cases covered: the body moved to the production wire contract, the base url is
asserted in ``test_route_chat_model_factory.py`` and ``test_registry_base_url.py``,
and the request path and auth headers are the provider SDK's doing — no gateway
code decides them any more, which is the whole point of the change.

Regenerate with: uv run python <scratchpad>/dump_endpoint_wire.py

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
(B3, D6, D8)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

# Aliased on import: these two are named `test_*`, so pytest collects them as
# tests wherever they are imported under their own names.
from graph_agent_gateway.probing import (
    probe_provider_endpoint as probe_provider_endpoint,
)
from graph_agent_gateway.registry import ProviderEndpoint

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
    _, protocol, host, id_key = case_key.split("|")
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

    endpoint_result = await probe_provider_endpoint(
        endpoint, api_key="SECRET", transport=httpx.MockTransport(handler)
    )
    return {**captured, "backend": endpoint_result.backend}


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
