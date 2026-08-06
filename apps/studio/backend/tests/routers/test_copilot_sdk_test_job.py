"""COPILOT_ASSIST-4: the role-test job runs the real SDK test for copilot roles.

These exercise the orchestration (per-route lights + result.sdk_evidence +
any-ok verdict) with the SDK driver mocked; the driver itself is covered in
test_copilot_sdk_test.py and the real spawn by a creds-gated live test.
"""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace

import pytest
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute
from app.routers import llm
from app.services.copilot import RouteSdkTestResult
from app.services.llm_health_store import ActiveCircuitsIndex
from graph_agent_gateway.registry.schema import VerifiedProfile

_NO_CIRCUITS = ActiveCircuitsIndex.build([])
_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def assert_english_diagnostic(message: str | None) -> str:
    assert message, "expected a user-visible diagnostic"
    assert not _CJK_RE.search(message), message
    return message


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
    # R-F9: the user-visible message is the human English rendering, not
    # the raw `ResourceTerminalError: ...` repr.
    message = assert_english_diagnostic(job.message)
    assert "ResourceTerminalError" not in message
    assert "has no available model route" in message
    assert "copilot_chat" in message


def test_human_message_for_error_code_covers_known_codes() -> None:
    """R-F9 acceptance #1 — every error_code surfaced by the gateway path has a
    human English rendering keyed off the same table the frontend mirrors."""
    messages = [
        llm._human_message_for_error_code("resource.no_available_route", "X"),
        llm._human_message_for_error_code("resource.role_unknown", "X"),
        llm._human_message_for_error_code("resource.role_invalid_kind", "X"),
        llm._human_message_for_error_code("resource.credential_missing", "X"),
        llm._human_message_for_error_code("some.new.code", "X"),
        llm._human_message_for_error_code(None, "X"),
    ]
    for message in messages:
        assert_english_diagnostic(message)

    assert "has no available model route" in messages[0]
    assert "does not exist or was deleted" in messages[1]
    assert "is not a copilot role" in messages[2]
    assert "is missing a required API key" in messages[3]
    # Unknown code → still human, never leaks "ResourceTerminalError" or repr.
    msg_unknown = messages[4]
    assert "test failed" in msg_unknown and "some.new.code" in msg_unknown
    # None code → fallback to generic message, role still mentioned.
    msg_none = messages[5]
    assert "X" in msg_none and "could not resolve" in msg_none


def test_get_role_test_results_returns_persisted_copilot_diagnostics_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted_message = "SDK returned an error: HTTP 401 unauthorized"
    monkeypatch.setattr(
        llm,
        "load_role_test_results",
        lambda: {
            "copilot_deepseek_v4_flash": {
                "role_name": "copilot_deepseek_v4_flash",
                "status": "failed",
                "message": persisted_message,
                "updated_at": "2026-07-05T00:00:00+00:00",
                "result": {
                    "role_name": "copilot_deepseek_v4_flash",
                    "status": "failed",
                    "warnings": [],
                    "model_groups": [
                        {
                            "canonical_id": "deepseek-v4-flash",
                            "provider_results": [
                                {
                                    "route_id": "qiniu:deepseek-v4-flash",
                                    "status": "failed",
                                    "message": persisted_message,
                                }
                            ],
                        }
                    ],
                    "sdk_evidence": {
                        "tested": True,
                        "passed": 0,
                        "total": 1,
                        "routes": {
                            "qiniu:deepseek-v4-flash": {
                                "status": "failed",
                                "message": persisted_message,
                                "retry_after_seconds": None,
                            }
                        },
                    },
                },
            }
        },
    )

    response = asyncio.run(llm.get_role_test_results())

    persisted = response.results["copilot_deepseek_v4_flash"]
    assert persisted.message == persisted_message
    sdk_route = persisted.result["sdk_evidence"]["routes"]["qiniu:deepseek-v4-flash"]
    assert sdk_route["message"] == persisted_message
    provider_result = persisted.result["model_groups"][0]["provider_results"][0]
    assert provider_result["message"] == persisted_message


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


def test_run_copilot_sdk_test_job_profiles_official_route_for_copilot_method_before_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = SimpleNamespace(
        route_id="deepseek-official:deepseek-v4-flash",
        endpoint_id="deepseek-official",
        canonical_id="deepseek-v4-flash",
        provider_model_id="deepseek-v4-flash",
        call_method_id="deepseek_chat_completions",
    )
    prepared_route = SimpleNamespace(
        route_id="deepseek-official:deepseek-v4-flash",
        endpoint_id="deepseek-official",
        canonical_id="deepseek-v4-flash",
        provider_model_id="deepseek-v4-flash",
        call_method_id="deepseek_anthropic_messages",
    )
    job_id = "job-copilot-deepseek"
    llm._role_test_jobs[job_id] = llm.RoleTestJobResponse(
        job_id=job_id,
        role_name="copilot_deepseek_v4_flash",
        status="queued",
        message="queued",
        provider_statuses=[llm._copilot_route_progress(route, "queued")],
    )
    raw_route = ProviderRoute(
        route_id="deepseek-official:deepseek-v4-flash",
        endpoint_id="deepseek-official",
        route_slug="deepseek-v4-flash",
        provider_model_id="deepseek-v4-flash",
        canonical_id="deepseek-v4-flash",
        status="verified",
        verified_profiles=[
            VerifiedProfile(
                profile_id="text:deepseek_chat_completions",
                capability="text_chat",
                method_id="deepseek_chat_completions",
                request_mapper_id="deepseek_chat_completions_text",
                status="ready",
                default=True,
                fallback_rank=1,
            )
        ],
    )
    endpoint = ProviderEndpoint(
        endpoint_id="deepseek-official",
        display_name="DeepSeek Official",
        protocol="openai_compatible",
        base_url="https://api.deepseek.com",
        api_key="secret",
        status="verified",
        provider_kind="official",
    )
    credentials = LLMCredentialsFile(
        provider_endpoints={endpoint.endpoint_id: endpoint},
        provider_routes={raw_route.route_id: raw_route},
    )
    profile_calls: list[tuple[str, str]] = []
    sdk_calls: list[tuple[str | None, object]] = []

    async def fake_profile_probe(
        route_arg: ProviderRoute,
        endpoint_arg: ProviderEndpoint,
        **kwargs: object,
    ) -> tuple[ProviderRoute, llm.OfficialModelProfileProbeResult]:
        assert kwargs["required_method_ids"] == llm._COPILOT_SDK_SUPPORTED_METHOD_IDS
        profile_calls.append((endpoint_arg.endpoint_id, route_arg.route_id))
        profile = VerifiedProfile(
            profile_id="text:deepseek_anthropic_messages",
            capability="text_chat",
            method_id="deepseek_anthropic_messages",
            request_mapper_id="deepseek_anthropic_messages_text",
            status="ready",
            default=True,
            fallback_rank=1,
        )
        return (
            route_arg.model_copy(
                update={
                    "status": "verified",
                    "verified_profiles": [profile],
                }
            ),
            llm.OfficialModelProfileProbeResult(
                model_id="deepseek-v4-flash",
                profiles=[profile],
            ),
        )

    def fake_runtime(role_name: str, *, route_override: str | None = None, **_kwargs):
        assert role_name == "copilot_deepseek_v4_flash"
        assert route_override == "deepseek-official:deepseek-v4-flash"
        return SimpleNamespace(routes=[prepared_route], credential_provider="fresh-provider")

    async def fake_sdk_test(route_arg: SimpleNamespace, provider: object, *, timeout_s: float = 60.0):
        del timeout_s
        sdk_calls.append((getattr(route_arg, "call_method_id", None), provider))
        return RouteSdkTestResult(route_arg.route_id, "ok", None)

    monkeypatch.setattr(llm, "load_credentials", lambda: credentials)
    monkeypatch.setattr(llm, "_ensure_official_role_test_verified_profile", fake_profile_probe)
    monkeypatch.setattr(llm, "build_gateway_route_runtime", fake_runtime)
    monkeypatch.setattr(llm.copilot, "run_route_sdk_test", fake_sdk_test)
    monkeypatch.setattr(llm, "_persist_copilot_sdk_evidence", lambda _results: None)

    try:
        asyncio.run(llm._run_copilot_sdk_test_job(job_id, "copilot_deepseek_v4_flash", [route], object()))
        assert profile_calls == [
            ("deepseek-official", "deepseek-official:deepseek-v4-flash")
        ]
        assert sdk_calls == [("deepseek_anthropic_messages", "fresh-provider")]
        final = llm._role_test_jobs[job_id]
        assert final.status == "completed"
        assert final.result is not None
        assert final.result["status"] == "ok"
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
