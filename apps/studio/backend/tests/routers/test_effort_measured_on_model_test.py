"""A route that just verified gets measured, whichever button verified it.

Effort is the one setting no document answers per model, so it has to be asked.
It was asked in exactly one place -- the forced route probe -- whose only UI
trigger is the re-probe icon on a *deprecated* model. A model added the normal
way, through "test models", therefore never had its effort measured at all: that
path copies the list-models fields or falls back to a text-only default.

The rule is not "effort belongs to that button". It is: whenever a real
generation verifies a route, measure what only measuring can settle.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
D5 §"P4 开工补记" fact 2, and D7's P4 row ("effort 测量归位到测试模型").
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core import config
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
)
from app.routers import llm as llm_router
from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
from fastapi.testclient import TestClient
from graph_agent_gateway.probing import EFFORT_CONTROL_LEVEL, RouteProbeResult


def _seed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "vendor": ProviderEndpoint(
                    endpoint_id="vendor",
                    display_name="Vendor",
                    protocol="google_genai",
                    base_url="https://vendor.example/v1",
                    api_key="secret",
                    provider_kind="third_party",
                )
            },
        ),
        credentials_path(),
    )


def _answer_with(monkeypatch, accepted: set[str]) -> list[str | None]:
    """Stand in for the provider, remembering which effort each request named."""
    asked: list[str | None] = []

    async def fake_probe_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, Any] | None = None,
    ) -> RouteProbeResult:
        reasoning = (runtime_settings or {}).get("reasoning")
        effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
        asked.append(effort)
        refused = effort is not None and effort not in accepted
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=llm_router._provider_backend_for_endpoint(endpoint),
            base_url=llm_router._endpoint_probe_base_url(endpoint),
            model_id=route.provider_model_id,
            status="invalid_model" if refused else "ok",  # type: ignore[arg-type]
            message="unsupported reasoning effort" if refused else None,
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_probe_route)
    return asked


def _list_models_say_it_thinks(monkeypatch, model_id: str) -> None:
    async def fake_list(endpoint: ProviderEndpoint) -> dict[str, dict[str, Any]]:
        return {model_id: {"thinking": True}}

    monkeypatch.setattr(llm_router, "_list_model_capabilities_for_endpoint", fake_list)


def test_testing_a_thinking_model_measures_the_effort_levels_it_takes(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    _list_models_say_it_thinks(monkeypatch, "thinker")
    asked = _answer_with(monkeypatch, accepted={"low", "high"})

    response = client.post(
        "/api/llm/endpoints/vendor/models/test",
        json={"model_ids": ["thinker"]},
    )

    assert response.status_code == 200, response.text
    route = next(iter(load_credentials().provider_routes.values()))
    capability = route.capabilities["reasoning_effort"]
    assert capability.source == "probed_verified"
    assert capability.value == {"supported": True, "values": ["low", "high"]}
    # One generation with no effort named, then one request per candidate level;
    # google_genai pins its own vocabulary, so the ladder is not offered whole.
    assert asked[0] is None
    assert asked[1:] == ["minimal", "low", "medium", "high", EFFORT_CONTROL_LEVEL]


def test_a_model_that_does_not_think_is_not_asked_about_effort(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Every level would be refused, and each refusal is a request that costs money."""
    _seed(tmp_path, monkeypatch)

    async def fake_list(endpoint: ProviderEndpoint) -> dict[str, dict[str, Any]]:
        return {"plain": {}}

    monkeypatch.setattr(llm_router, "_list_model_capabilities_for_endpoint", fake_list)
    asked = _answer_with(monkeypatch, accepted=set())

    response = client.post(
        "/api/llm/endpoints/vendor/models/test",
        json={"model_ids": ["plain"]},
    )

    assert response.status_code == 200, response.text
    assert asked == [None], "only the one generation that verifies the route"
    route = next(iter(load_credentials().provider_routes.values()))
    assert "reasoning_effort" not in route.capabilities
