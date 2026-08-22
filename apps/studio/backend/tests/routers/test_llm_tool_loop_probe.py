"""Whether a route calls a tool, asked by the Tests whose route set the user chose.

"Does this route work" has a different answer for an agent phase than for a
plain generation: every agent loop binds tools and reads a tool call back
(`call/chat_model.py::_dispatch`). A route can pass the generation probe and
still be useless to an agent, and until now nothing asked.

Two paths ask, and what they have in common is the rule: T3 is the deepest rung
of the probe ladder — two real requests per route, against T1's one GET
(`docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md`, D1's
table) — so it may only ride a path whose set of routes THE USER picked.

  * the forced probe of one named route: one deliberate click, one route;
  * a role test: one deliberate click over the chain that role was configured
    with, which is what the probing decision doc named as T3's home ("角色 Test
    ... 拿一组已 fit 的设置跑 T2 深度 0(将来加 T3)"). The chain runs through
    `asyncio.gather`, so the wall clock is the slowest route rather than the sum.

The bulk "test models" path (`_measure_what_only_asking_settles`) still does NOT
ask, and that is the same rule rather than an exception to it: its route set is
however many models an endpoint happens to list, which nobody chose.
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
from graph_agent_gateway.probing import (
    RouteProbeResult,
    RouteToolLoopResult,
    ToolLoopReach,
)


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
                "vendor:worker": ProviderRoute(
                    route_id="vendor:worker",
                    endpoint_id="vendor",
                    route_slug="worker",
                    provider_model_id="worker",
                    canonical_id="worker",
                )
            },
        ),
        credentials_path(),
    )


def _generation_answers_ok(monkeypatch) -> None:
    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        del runtime_settings
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=llm_router._provider_backend_for_endpoint(endpoint),
            base_url=llm_router._endpoint_probe_base_url(endpoint),
            model_id=route.provider_model_id,
            status="ok",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)


def _tool_loop_reaches(monkeypatch, reach: ToolLoopReach) -> list[str]:
    """Stand in for the tool-loop probe, remembering which routes it was asked about."""
    asked: list[str] = []

    async def fake_tool_loop(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
    ) -> RouteToolLoopResult:
        asked.append(route.route_id)
        return RouteToolLoopResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=llm_router._provider_backend_for_endpoint(endpoint),
            base_url=llm_router._endpoint_probe_base_url(endpoint),
            model_id=route.provider_model_id,
            status="ok",
            reach=reach,
        )

    monkeypatch.setattr(llm_router, "_gateway_probe_route_tool_loop", fake_tool_loop)
    return asked


def test_a_route_watched_calling_a_tool_records_it_as_measured(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    _generation_answers_ok(monkeypatch)
    asked = _tool_loop_reaches(monkeypatch, "closed_the_loop")

    response = client.post("/api/llm/routes/vendor:worker/probe")

    assert response.status_code == 200, response.text
    capability = load_credentials().provider_routes["vendor:worker"].capabilities["tool_protocol"]
    assert capability.value is True
    assert capability.source == "probed_verified"
    assert asked == ["vendor:worker"]


def test_a_route_that_only_called_the_tool_still_verifies_the_protocol(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Calling is what the capability is about; closing the loop is a stronger
    observation with nowhere to go but the message."""
    _seed(tmp_path, monkeypatch)
    _generation_answers_ok(monkeypatch)
    _tool_loop_reaches(monkeypatch, "called_the_tool")

    client.post("/api/llm/routes/vendor:worker/probe")

    capability = load_credentials().provider_routes["vendor:worker"].capabilities["tool_protocol"]
    assert capability.value is True
    assert capability.message is not None


def test_a_route_that_answered_in_prose_leaves_the_capability_unmeasured(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """No tool call has two indistinguishable causes — a protocol with no tools,
    and a model that chose prose — so writing `False` would delete a capability
    the route may well have. Absent already means "nobody has asked yet"."""
    _seed(tmp_path, monkeypatch)
    _generation_answers_ok(monkeypatch)
    _tool_loop_reaches(monkeypatch, "answered_without_calling")

    client.post("/api/llm/routes/vendor:worker/probe")

    assert "tool_protocol" not in load_credentials().provider_routes["vendor:worker"].capabilities


def test_a_route_that_failed_its_generation_probe_is_never_asked_about_tools(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Two more requests to a route that just refused the cheapest one buys
    nothing — the same rule that keeps the effort ladder off a route with no
    thinking to spend it on."""
    _seed(tmp_path, monkeypatch)
    asked = _tool_loop_reaches(monkeypatch, "closed_the_loop")

    async def refuse(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        del runtime_settings
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=llm_router._provider_backend_for_endpoint(endpoint),
            base_url=llm_router._endpoint_probe_base_url(endpoint),
            model_id=route.provider_model_id,
            status="invalid_key",
            message="bad key",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", refuse)

    client.post("/api/llm/routes/vendor:worker/probe")

    assert asked == []


def test_a_measurement_that_blows_up_does_not_take_the_answer_with_it(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The reader asked "does this route work". T3 is an extra asked afterwards.

    Measured 2026-08-21: on a `google_genai` route in an environment without the
    optional `langchain-google-genai` client, building the probe model raises
    `ImportError` — and because the raise happened after the generation probe had
    already answered `ok`, the whole request 500'd and the answer the reader
    actually asked for was thrown away with it.

    Same rule, same file, same shape as `_preferred_route_call_method_id`
    (`llm.py`): an extra projection that fails degrades to "not measured" and
    says so in the log; it never voids the response it was riding on.
    """
    _seed(tmp_path, monkeypatch)
    _generation_answers_ok(monkeypatch)

    async def explode(endpoint: ProviderEndpoint, route: ProviderRoute) -> RouteToolLoopResult:
        del endpoint, route
        raise ImportError("google_genai routes require the graph-agent-gateway[google] extra")

    monkeypatch.setattr(llm_router, "_gateway_probe_route_tool_loop", explode)

    response = client.post("/api/llm/routes/vendor:worker/probe")

    assert response.status_code == 200, response.text
    assert load_credentials().provider_routes["vendor:worker"].status == "verified"
    assert "tool_protocol" not in load_credentials().provider_routes["vendor:worker"].capabilities


def _seed_role_over(tmp_path: Path, monkeypatch, *, route_ids: list[str]) -> None:
    """Credentials plus a role whose chain is exactly `route_ids`, already verified.

    The routes start `verified` because T3 only ever runs after the generation
    probe has answered — measuring tools on a route that cannot answer at all
    would be asking the second question before the first.
    """
    from app.models.llm_config import RoleEntry, RoleRouteEntry, RolesData
    from app.services.llm_roles import save_roles_file

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
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
                route_id: ProviderRoute(
                    route_id=route_id,
                    endpoint_id="vendor",
                    route_slug=route_id.split(":", 1)[1],
                    provider_model_id=route_id.split(":", 1)[1],
                    canonical_id=route_id.split(":", 1)[1],
                    status="verified",
                )
                for route_id in route_ids
            },
        ),
        credentials_path(),
    )
    save_roles_file(
        settings_dir / "llm" / "llm_roles.yaml",
        RolesData(
            roles={
                "graph_agent": RoleEntry(
                    fallback_chain=[RoleRouteEntry(route_id=route_id) for route_id in route_ids]
                )
            },
        ),
        known_route_ids=set(route_ids),
    )


def _await_role_test_job(client: TestClient, job_id: str) -> dict:
    import time

    for _ in range(400):
        body = client.get(f"/api/llm/role-test-jobs/{job_id}").json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.01)
    raise AssertionError("role test job never finished")


def test_a_role_test_asks_every_route_in_the_chain_about_tools(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The role test is where the probing decision doc puts T3.

    `2026-08-10-gateway-module-tree-and-probing-decision.md:124`: "角色 Test 不是
    新原子,它是『拿一组已 fit 的设置跑 T2 深度 0(**将来加 T3**)』". The chain is
    a set of routes the user configured, so it satisfies the cost rule in this
    module's docstring, and the answer is exactly what a reader about to hand
    this role an agent phase needs.
    """
    _seed_role_over(tmp_path, monkeypatch, route_ids=["vendor:worker", "vendor:helper"])
    _generation_answers_ok(monkeypatch)
    asked = _tool_loop_reaches(monkeypatch, "closed_the_loop")

    start = client.post("/api/llm/roles/graph_agent/test-jobs")
    assert start.status_code == 200, start.text
    finished = _await_role_test_job(client, start.json()["job_id"])

    assert finished["status"] == "completed"
    assert sorted(asked) == ["vendor:helper", "vendor:worker"]
    routes = load_credentials().provider_routes
    for route_id in ("vendor:worker", "vendor:helper"):
        capability = routes[route_id].capabilities["tool_protocol"]
        assert capability.value is True
        assert capability.source == "probed_verified"
        assert capability.message_code == "tool_loop_closed_the_loop"


def test_a_role_test_whose_tool_measurement_blows_up_still_reports_the_route(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Same rule as the single-route probe, now on the path that runs many at once.

    The reader asked whether their role works. One route's extra measurement
    failing must not turn that into a failed job — nor lose the OTHER routes'
    measurements, which is the part running them through `asyncio.gather` makes
    easy to get wrong.
    """
    _seed_role_over(tmp_path, monkeypatch, route_ids=["vendor:worker", "vendor:helper"])
    _generation_answers_ok(monkeypatch)

    async def explode_for_worker(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
    ) -> RouteToolLoopResult:
        if route.route_id == "vendor:worker":
            raise ImportError("this route's optional client is not installed")
        return RouteToolLoopResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=llm_router._provider_backend_for_endpoint(endpoint),
            base_url=llm_router._endpoint_probe_base_url(endpoint),
            model_id=route.provider_model_id,
            status="ok",
            reach="closed_the_loop",
        )

    monkeypatch.setattr(llm_router, "_gateway_probe_route_tool_loop", explode_for_worker)

    start = client.post("/api/llm/roles/graph_agent/test-jobs")
    finished = _await_role_test_job(client, start.json()["job_id"])

    assert finished["status"] == "completed"
    routes = load_credentials().provider_routes
    assert "tool_protocol" not in routes["vendor:worker"].capabilities
    assert routes["vendor:helper"].capabilities["tool_protocol"].value is True
