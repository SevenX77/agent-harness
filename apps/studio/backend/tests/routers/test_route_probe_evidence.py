"""A route is marked verified because it answered, never because someone said so.

`source="probed_verified"` is the strongest claim the registry can carry: it
means this exact route was asked and this exact answer came back. The one thing
that must never be able to produce it is the request body, because a caller
naming a capability has measured nothing.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
B7 / D6 ("有一个不发请求就写实测证据的接口" — delete the branch).
"""

from __future__ import annotations

from pathlib import Path

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
                )
            },
            provider_routes={
                "vendor:model": ProviderRoute(
                    route_id="vendor:model",
                    endpoint_id="vendor",
                    route_slug="model",
                    provider_model_id="model",
                    canonical_id="model",
                    status="unverified_manual",
                )
            },
        ),
        credentials_path(),
    )


def _count_asks(monkeypatch, *, status: str = "ok") -> list[str]:
    """Stand in for the provider, remembering every route it was asked about."""
    asked: list[str] = []

    async def fake_probe_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        asked.append(route.route_id)
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=llm_router._provider_backend_for_endpoint(endpoint),
            base_url=llm_router._endpoint_probe_base_url(endpoint),
            model_id=route.provider_model_id,
            status=status,  # type: ignore[arg-type]
            message=None if status == "ok" else "refused",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_probe_route)
    return asked


def test_probing_a_route_asks_the_provider(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """There is no way to reach this endpoint without a request going out."""
    _seed(tmp_path, monkeypatch)
    asked = _count_asks(monkeypatch)

    response = client.post("/api/llm/routes/vendor:model/probe")

    assert response.status_code == 200, response.text
    assert asked == ["vendor:model"]


def test_a_caller_naming_a_capability_does_not_make_it_measured(
    tmp_path: Path,
    monkeypatch,
    client: TestClient,
) -> None:
    """The old non-force branch turned this body into `probed_verified` evidence."""
    _seed(tmp_path, monkeypatch)
    asked = _count_asks(monkeypatch, status="invalid_model")

    response = client.post(
        "/api/llm/routes/vendor:model/probe",
        json={"capabilities": ["tool_calling"], "runtime_settings": {"seed": {"supported": True}}},
    )

    assert response.status_code == 200, response.text
    assert asked == ["vendor:model"], "the body must not be a substitute for asking"
    saved = load_credentials().provider_routes["vendor:model"]
    assert saved.status == "failed"
    assert "tool_protocol" not in saved.capabilities
    assert "seed" not in saved.capabilities
