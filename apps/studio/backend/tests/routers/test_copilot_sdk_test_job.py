"""COPILOT_ASSIST-4: the role-test job runs the real SDK test for copilot roles.

These exercise the orchestration (per-route lights + result.sdk_evidence +
any-ok verdict) with the SDK driver mocked; the driver itself is covered in
test_copilot_sdk_test.py and the real spawn by a creds-gated live test.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from app.models.llm_config import LLMCredentialsFile, ProviderRoute
from app.routers import llm
from app.services.copilot import RouteSdkTestResult


def _seed_credentials(monkeypatch: pytest.MonkeyPatch, route: ProviderRoute) -> list[LLMCredentialsFile]:
    creds = LLMCredentialsFile(provider_routes={route.route_id: route})
    saved: list[LLMCredentialsFile] = []
    monkeypatch.setattr(llm, "load_credentials", lambda: creds)
    monkeypatch.setattr(llm, "save_credentials", lambda c: saved.append(c))
    return saved


def _route_record(route_id: str) -> ProviderRoute:
    endpoint_id, _, slug = route_id.partition(":")
    return ProviderRoute(
        route_id=route_id,
        endpoint_id=endpoint_id,
        route_slug=slug,
        provider_model_id="m1",
        canonical_id="c1",
        metadata={"reason_code": "keep-me"},
    )


def _route(route_id: str, canonical: str = "claude-sonnet") -> SimpleNamespace:
    return SimpleNamespace(route_id=route_id, canonical_id=canonical)


def test_build_copilot_sdk_result_any_ok_is_pass() -> None:
    routes = [_route("r1"), _route("r2")]
    results = [RouteSdkTestResult("r1", "failed", "boom"), RouteSdkTestResult("r2", "ok", None)]

    out = llm._build_copilot_sdk_result("copilot_chat", routes, results)

    assert out["status"] == "ok"  # copilot needs only one working route (fallback)
    assert out["sdk_evidence"] == {
        "tested": True,
        "passed": 1,
        "total": 2,
        "routes": {
            "r1": {"status": "failed", "message": "boom"},
            "r2": {"status": "ok", "message": None},
        },
    }


def test_build_copilot_sdk_result_all_failed_is_failed() -> None:
    routes = [_route("r1")]
    results = [RouteSdkTestResult("r1", "failed", "x")]

    out = llm._build_copilot_sdk_result("copilot_chat", routes, results)

    assert out["status"] == "failed"
    assert out["sdk_evidence"]["passed"] == 0


def test_start_copilot_sdk_test_job_preserves_gateway_terminal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.adapters.gateway import ResourceTerminalError

    async def run_job() -> llm.RoleTestJobResponse:
        return await llm._start_copilot_sdk_test_job("copilot_chat")

    def fail_resolution(_role_name: str) -> object:
        raise ResourceTerminalError(
            "resource.no_available_route",
            {"role": "copilot_chat", "route_ids": []},
        )

    monkeypatch.setattr(llm, "_resolve_copilot_test_routes", fail_resolution)

    job = asyncio.run(run_job())

    assert job.status == "failed"
    assert job.error_code == "resource.no_available_route"
    assert job.error_payload == {"role": "copilot_chat", "route_ids": []}


def test_run_copilot_sdk_test_job_updates_each_route_light_and_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routes = [_route("r1"), _route("r2")]
    job_id = "job-copilot-x"
    llm._role_test_jobs[job_id] = llm.RoleTestJobResponse(
        job_id=job_id,
        role_name="copilot_chat",
        status="queued",
        message="queued",
        provider_statuses=[llm._copilot_route_progress(route, "queued") for route in routes],
    )

    async def fake_sdk_test(route: object, _provider: object, *, timeout_s: float = 60.0):
        del timeout_s
        ok = route.route_id == "r2"
        return RouteSdkTestResult(route.route_id, "ok" if ok else "failed", None if ok else "boom")

    monkeypatch.setattr(llm.copilot, "run_route_sdk_test", fake_sdk_test)

    monkeypatch.setattr(llm, "_persist_copilot_sdk_evidence", lambda _results: None)
    try:
        asyncio.run(llm._run_copilot_sdk_test_job(job_id, "copilot_chat", routes, object()))
        final = llm._role_test_jobs[job_id]
        assert final.status == "completed"
        assert {p.route_id: p.status for p in final.provider_statuses} == {"r1": "failed", "r2": "ok"}
        assert final.result is not None
        assert final.result["status"] == "ok"
        assert final.result["sdk_evidence"]["passed"] == 1
    finally:
        llm._role_test_jobs.pop(job_id, None)


def test_persist_copilot_sdk_evidence_writes_route_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = _seed_credentials(monkeypatch, _route_record("e1:r1"))

    llm._persist_copilot_sdk_evidence([RouteSdkTestResult("e1:r1", "ok", None)])

    assert saved, "passing evidence must be persisted to credentials"
    route = saved[-1].provider_routes["e1:r1"]
    evidence = route.metadata["sdk_tool_call_verified"]
    assert evidence["verified"] is True and evidence["status"] == "ok"
    assert "verified_at" in evidence
    assert route.metadata["reason_code"] == "keep-me", "existing metadata preserved"


def test_persist_copilot_sdk_evidence_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = _seed_credentials(monkeypatch, _route_record("e1:r1"))

    llm._persist_copilot_sdk_evidence([RouteSdkTestResult("e1:r1", "failed", "boom")])

    evidence = saved[-1].provider_routes["e1:r1"].metadata["sdk_tool_call_verified"]
    assert evidence["verified"] is False and evidence["status"] == "failed"


def test_persist_copilot_sdk_evidence_skips_unknown_route(monkeypatch: pytest.MonkeyPatch) -> None:
    creds = LLMCredentialsFile(provider_routes={})
    saved: list[LLMCredentialsFile] = []
    monkeypatch.setattr(llm, "load_credentials", lambda: creds)
    monkeypatch.setattr(llm, "save_credentials", lambda c: saved.append(c))

    llm._persist_copilot_sdk_evidence([RouteSdkTestResult("missing", "ok", None)])

    assert saved == [], "nothing to persist when the route is unknown"
