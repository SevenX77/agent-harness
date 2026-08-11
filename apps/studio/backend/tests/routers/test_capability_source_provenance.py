"""A capability's source says where that capability came from.

`source` answers "how do we know this?" for one capability — a provider doc, the
endpoint's list-models response, or an actual measurement. It is not a property
of the route. Deriving it from `route.status` says instead "this route answered
one generation request, so treat everything it claims as measured", which is the
same mistake as reading evidence out of a request body: the answer is recorded
without the question ever being asked.

It also defeats a real check. `resolve/lint.py` blocks an error-severity
requirement whose capability is not `manual` or `probed_verified`, precisely so a
role cannot silently depend on an unverified claim. Stamping list-derived claims
`probed_verified` walks the role straight past it.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
D3 (one write entry for measurements) and the P4e note under D5.
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
from graph_agent_gateway.probing import RouteProbeResult


def _seed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "vendor": ProviderEndpoint(
                    endpoint_id="vendor",
                    display_name="Vendor",
                    protocol="openai_compatible",
                    base_url="https://vendor.example/v1",
                    api_key="secret",
                    provider_kind="third_party",
                )
            },
        ),
        credentials_path(),
    )


def _generation_succeeds(monkeypatch) -> None:
    async def fake_probe_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, Any] | None = None,
    ) -> RouteProbeResult:
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=llm_router._provider_backend_for_endpoint(endpoint),
            base_url=llm_router._endpoint_probe_base_url(endpoint),
            model_id=route.provider_model_id,
            status="ok",
            message=None,
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_probe_route)


def test_what_the_list_api_claimed_stays_credited_to_the_list_api(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """One text generation does not measure vision, or anything else listed."""
    _seed(tmp_path, monkeypatch)
    _generation_succeeds(monkeypatch)

    async def fake_list(endpoint: ProviderEndpoint) -> dict[str, dict[str, Any]]:
        return {"seer": {"input_modalities": ["text", "image"]}}

    monkeypatch.setattr(llm_router, "_list_model_capabilities_for_endpoint", fake_list)

    response = client.post(
        "/api/llm/endpoints/vendor/models/test",
        json={"model_ids": ["seer"]},
    )

    assert response.status_code == 200, response.text
    route = next(iter(load_credentials().provider_routes.values()))
    assert route.status == "verified"
    modalities = route.capabilities["input_modalities"]
    assert modalities.value == ["text", "image"]
    assert modalities.source == "api_list", (
        "the list API claimed it; the probe only asked for one text generation"
    )
