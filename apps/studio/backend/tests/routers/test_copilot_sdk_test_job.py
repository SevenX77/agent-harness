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
from app.services.llm_health_store import ActiveCircuitsIndex

_NO_CIRCUITS = ActiveCircuitsIndex.build([])


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
    # R-F21: routes_evidence now carries retry_after_seconds alongside status
    # so a remount can rehydrate a cooldown countdown via the R20 seed path.
    # The field is None for ok/failed verdicts (they have no cooldown window).
    assert out["sdk_evidence"] == {
        "tested": True,
        "passed": 1,
        "total": 2,
        "routes": {
            "r1": {"status": "failed", "message": "boom", "retry_after_seconds": None},
            "r2": {"status": "ok", "message": None, "retry_after_seconds": None},
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
    # R-F9: the user-visible message is the human Chinese rendering, not
    # the raw `ResourceTerminalError: ...` repr.
    assert "ResourceTerminalError" not in (job.message or "")
    assert "暂无可用模型路由" in (job.message or "")
    assert "copilot_chat" in (job.message or "")


def test_human_message_for_error_code_covers_known_codes() -> None:
    """R-F9 acceptance #1 — every error_code surfaced by the gateway path has a
    human Chinese rendering keyed off the same table the frontend mirrors."""
    assert "暂无可用模型路由" in llm._human_message_for_error_code(
        "resource.no_available_route", "X"
    )
    assert "不存在或已被删除" in llm._human_message_for_error_code(
        "resource.role_unknown", "X"
    )
    assert "不是 copilot 角色" in llm._human_message_for_error_code(
        "resource.role_invalid_kind", "X"
    )
    assert "缺少必需的 API key" in llm._human_message_for_error_code(
        "resource.credential_missing", "X"
    )
    # Unknown code → still human, never leaks "ResourceTerminalError" or repr.
    msg_unknown = llm._human_message_for_error_code("some.new.code", "X")
    assert "测试失败" in msg_unknown and "some.new.code" in msg_unknown
    # None code → fallback to generic message, role still mentioned.
    msg_none = llm._human_message_for_error_code(None, "X")
    assert "X" in msg_none and "无法解析" in msg_none


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


def test_provider_model_option_emits_call_method_id_from_verified_profile() -> None:
    """R-F8 acceptance #2 — `_model_group_response` (via `_provider_model_option`)
    must include `call_method_id` so the frontend CopilotTab can filter copilot
    eligibility by anthropic-messages capability instead of by provider_type.
    The id is derived from the route's preferred ready `VerifiedProfile`.
    """
    from app.core.adapters.gateway import VerifiedProfile
    from app.models.llm_config import ProviderEndpoint, ProviderRoute

    endpoint = ProviderEndpoint(
        endpoint_id="ark-official",
        display_name="Ark Official",
        protocol="openai_compatible",  # non-anthropic provider type — old heuristic would miss it
        base_url="https://ark.example/v1",
        api_key="x",
        status="verified",
    )
    route = ProviderRoute(
        route_id="ark-official:claude-opus-4-8",
        endpoint_id="ark-official",
        route_slug="claude-opus-4-8",
        provider_model_id="claude-opus-4-8",
        canonical_id="claude-opus-4.8",
        verified_profiles=[
            VerifiedProfile(
                profile_id="ark-official:claude-opus-4-8:anthropic_messages:default",
                method_id="ark_anthropic_messages",
                capability="anthropic_messages",
                request_mapper_id="ark_anthropic_messages",
                status="ready",
                default=True,
                input_modalities=["text"],
            )
        ],
    )
    creds = LLMCredentialsFile(
        provider_endpoints={endpoint.endpoint_id: endpoint},
        provider_routes={route.route_id: route},
    )

    option = llm._provider_model_option(route, creds, circuits_index=_NO_CIRCUITS)
    assert option is not None
    assert option["call_method_id"] == "ark_anthropic_messages"
    # The legacy provider_type heuristic would have excluded this — proving
    # that downstream filtering must rely on call_method_id, not protocol.
    assert endpoint.protocol == "openai_compatible"


def test_provider_model_option_call_method_id_none_for_route_without_verified_profile() -> None:
    """Routes without any ready verified profile emit `call_method_id: None`;
    CopilotTab treats this as 'not eligible for copilot', degrading visibly."""
    from app.models.llm_config import ProviderEndpoint, ProviderRoute

    endpoint = ProviderEndpoint(
        endpoint_id="legacy",
        display_name="Legacy",
        protocol="openai_compatible",
        base_url="https://x",
        api_key="x",
        status="verified",
    )
    route = ProviderRoute(
        route_id="legacy:gpt-5",
        endpoint_id="legacy",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        # No verified_profiles → call_method_id resolves to None.
    )
    creds = LLMCredentialsFile(
        provider_endpoints={endpoint.endpoint_id: endpoint},
        provider_routes={route.route_id: route},
    )

    option = llm._provider_model_option(route, creds, circuits_index=_NO_CIRCUITS)
    assert option is not None
    assert option["call_method_id"] is None
