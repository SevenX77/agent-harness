"""COPILOT_ASSIST-4: the role-test job runs the real SDK test for copilot roles.

These exercise the orchestration (per-route lights + result.sdk_evidence +
any-ok verdict) with the SDK driver mocked; the driver itself is covered in
test_copilot_sdk_test.py and the real spawn by a creds-gated live test.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from app.routers import llm
from app.services.copilot import RouteSdkTestResult


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
