"""Which effort levels a route sells, measured by asking it.

Every other bound a setting has is a documented constant, so probing it
re-learns a published number. Effort is the exception: providers name different
levels and their own models take different subsets — DeepSeek v4-pro folds
`medium` into `high` while its siblings take three others, and OpenAI's set
moves between model versions. No document answers "which of them does THIS
route take", so a forced route probe asks it.

Asking costs one request per level, so it is only asked of a route that says it
reasons at all: a model with no thinking to spend effort on would refuse every
level and charge for the privilege.

Decision: docs/design/2026-08-10-preferences-fit-the-route-decision.md D-A
"""

from __future__ import annotations

from pathlib import Path

from app.core import config
from app.models.llm_config import (
    CapabilityValue,
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
)
from app.routers import llm as llm_router
from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
from fastapi.testclient import TestClient
from graph_agent_gateway.probing import RouteProbeResult


def _seed(tmp_path: Path, monkeypatch, *, thinking: bool, protocol: str) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    capabilities: dict[str, CapabilityValue] = {}
    if thinking:
        capabilities["thinking_protocol"] = CapabilityValue(value=True, source="provider_doc")
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "vendor": ProviderEndpoint(
                    endpoint_id="vendor",
                    display_name="Vendor",
                    protocol=protocol,  # type: ignore[arg-type]
                    base_url="https://vendor.example/v1",
                    api_key="secret",
                )
            },
            provider_routes={
                "vendor:thinker": ProviderRoute(
                    route_id="vendor:thinker",
                    endpoint_id="vendor",
                    route_slug="thinker",
                    provider_model_id="thinker",
                    canonical_id="thinker",
                    capabilities=capabilities,
                )
            },
        ),
        credentials_path(),
    )


def _record_asked(
    monkeypatch,
    accepted: set[str],
    *,
    refusal_status: str = "invalid_model",
) -> list[str | None]:
    """Stand in for the provider, remembering which effort each request named."""
    asked: list[str | None] = []

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
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
            status=refusal_status if refused else "ok",  # type: ignore[arg-type]
            message="unsupported reasoning effort" if refused else None,
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)
    return asked


def test_a_forced_probe_records_the_levels_the_route_accepted(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch, thinking=True, protocol="anthropic_compatible")
    asked = _record_asked(monkeypatch, accepted={"low", "high", "max"})

    response = client.post("/api/llm/routes/vendor:thinker/probe?force=true", json={})

    assert response.status_code == 200, response.text
    capability = load_credentials().provider_routes["vendor:thinker"].capabilities[
        "reasoning_effort"
    ]
    assert capability.value == {"supported": True, "values": ["low", "high", "max"]}
    assert capability.source == "probed_verified"
    # One generation probe with no effort named, then one request per candidate.
    assert asked[0] is None
    assert asked[1:] == ["low", "medium", "high", "xhigh", "max"]


def test_a_protocol_that_pins_its_vocabulary_is_not_asked_beyond_it(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Asking Gemini for `xhigh` spends a request to be told what its API already says."""
    _seed(tmp_path, monkeypatch, thinking=True, protocol="google_genai")
    asked = _record_asked(monkeypatch, accepted={"minimal", "low", "medium", "high"})

    client.post("/api/llm/routes/vendor:thinker/probe?force=true", json={})

    assert asked[1:] == ["minimal", "low", "medium", "high"]


def test_a_protocol_that_pins_nothing_is_asked_the_whole_ladder(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """OpenAI's set moves per model version, so this is exactly the case only
    measuring can answer."""
    _seed(tmp_path, monkeypatch, thinking=True, protocol="openai_compatible")
    asked = _record_asked(monkeypatch, accepted={"low", "high"})

    client.post("/api/llm/routes/vendor:thinker/probe?force=true", json={})

    assert asked[1:] == ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
    capability = load_credentials().provider_routes["vendor:thinker"].capabilities[
        "reasoning_effort"
    ]
    assert capability.value == {"supported": True, "values": ["low", "high"]}


def test_a_route_that_does_not_reason_is_never_asked_about_effort(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Effort is how hard to think; a model that does not think has nothing to
    spend, and every level would be a paid refusal."""
    _seed(tmp_path, monkeypatch, thinking=False, protocol="anthropic_compatible")
    asked = _record_asked(monkeypatch, accepted={"low", "high", "max"})

    client.post("/api/llm/routes/vendor:thinker/probe?force=true", json={})

    assert asked == [None]
    assert "reasoning_effort" not in load_credentials().provider_routes[
        "vendor:thinker"
    ].capabilities


def test_a_route_that_refuses_every_level_records_that_rather_than_nothing(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """"It sells none of them" is an answer; leaving the capability absent would
    read as "nobody has asked yet" and invite the same spend again."""
    _seed(tmp_path, monkeypatch, thinking=True, protocol="anthropic_compatible")
    _record_asked(monkeypatch, accepted=set())

    client.post("/api/llm/routes/vendor:thinker/probe?force=true", json={})

    capability = load_credentials().provider_routes["vendor:thinker"].capabilities[
        "reasoning_effort"
    ]
    assert capability.value == {"supported": False, "values": []}


def test_a_probe_that_hit_a_rate_limit_records_nothing_rather_than_a_wrong_list(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A dead socket or a throttled account says nothing about which levels the
    route sells; writing "refused" would delete levels it does sell."""
    _seed(tmp_path, monkeypatch, thinking=True, protocol="anthropic_compatible")
    _record_asked(monkeypatch, accepted={"low"}, refusal_status="rate_limited")

    client.post("/api/llm/routes/vendor:thinker/probe?force=true", json={})

    assert "reasoning_effort" not in load_credentials().provider_routes[
        "vendor:thinker"
    ].capabilities
