from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Self
from unittest.mock import AsyncMock

import pytest
from app.models.copilot import (
    CopilotEventContextResolved,
    CopilotEventDone,
    CopilotEventError,
    CopilotEventText,
    CopilotEventToolUseStart,
)
from app.routers import copilot as copilot_router
from app.services import copilot as copilot_service
from claude_agent_sdk import ClaudeAgentOptions, ProcessError
from claude_agent_sdk.types import AssistantMessage, TextBlock
from fastapi.testclient import TestClient
from graph_agent_gateway.registry.schema import Protocol, ResolvedRoute
from pydantic import SecretStr


def test_copilot_bash_approval_endpoint_forwards_decision(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def resolve_bash_approval(
        skill_id: str,
        tool_use_id: str,
        *,
        approve: bool,
    ) -> copilot_service.BashApprovalResult:
        calls.append(
            {
                "skill_id": skill_id,
                "tool_use_id": tool_use_id,
                "approve": approve,
            }
        )
        return copilot_service.BashApprovalResult(
            tool_use_id=tool_use_id,
            approved=approve,
            executed=approve,
            success=True,
            stdout="ok\n",
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(copilot_router, "resolve_bash_approval", resolve_bash_approval)

    response = client.post(
        "/api/skills/text-segmentation/copilot/bash-approval",
        json={"tool_use_id": "tu-approve", "approve": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "tool_use_id": "tu-approve",
        "approved": True,
        "executed": True,
        "success": True,
        "stdout": "ok\n",
        "stderr": "",
        "returncode": 0,
        "message": None,
    }
    assert calls == [
        {
            "skill_id": "text-segmentation",
            "tool_use_id": "tu-approve",
            "approve": True,
        }
    ]


def test_copilot_ws_streams_normal_query(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        copilot_router,
        "stream_query",
        lambda **_kwargs: _events(CopilotEventText(content="hello"), CopilotEventDone()),
    )

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})

        assert websocket.receive_json()["type"] == "text_delta"
        assert websocket.receive_json()["type"] == "done"


def test_copilot_ws_forwards_model_override(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def stream_query(**kwargs: object) -> AsyncIterator[object]:
        calls.append(kwargs)
        return _events(CopilotEventDone())

    monkeypatch.setattr(copilot_router, "stream_query", stream_query)

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi", "model_override": "CL46T"})
        assert websocket.receive_json()["type"] == "done"

    assert calls == [
        {
            "skill_id": "text-segmentation",
            "user_message": "hi",
            "model_override": "CL46T",
            "role": None,
            "workspace_root": None,
            "judge_context": None,
        }
    ]


def test_copilot_ws_forwards_workspace_root(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def stream_query(**kwargs: object) -> AsyncIterator[object]:
        calls.append(kwargs)
        return _events(CopilotEventDone())

    monkeypatch.setattr(copilot_router, "stream_query", stream_query)

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({
            "user_message": "hi",
            "workspace_root": "/abs/imported-skill",
        })
        assert websocket.receive_json()["type"] == "done"

    assert calls == [
        {
            "skill_id": "text-segmentation",
            "user_message": "hi",
            "model_override": None,
            "role": None,
            "workspace_root": "/abs/imported-skill",
            "judge_context": None,
        }
    ]


def test_copilot_ws_forwards_structured_judge_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    judge_context = {
        "compare_result_ref": "text-segmentation/golden/golden-1/compare/run-1/compare_result.json",
        "judge_context_ref": "text-segmentation/runs/run-1/copilot_judge/golden-1/judge_context.json",
        "baseline_ref": "text-segmentation/golden/golden-1/baseline.json",
        "diff_summary": {
            "baseline_id": "golden-1",
            "run_results_ref": "text-segmentation/runs/run-1/result.json",
            "total_score": 88,
            "node_group_count": 2,
            "failed_node_count": 1,
        },
    }

    def stream_query(**kwargs: object) -> AsyncIterator[object]:
        calls.append(kwargs)
        return _events(CopilotEventDone())

    monkeypatch.setattr(copilot_router, "stream_query", stream_query)

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({
            "user_message": "judge it",
            "role": "copilot_judge",
            "judge_context": judge_context,
        })
        assert websocket.receive_json()["type"] == "done"

    assert calls == [
        {
            "skill_id": "text-segmentation",
            "user_message": "judge it",
            "model_override": None,
            "role": "copilot_judge",
            "workspace_root": None,
            "judge_context": judge_context,
        }
    ]


def test_copilot_prompt_renders_structured_judge_context() -> None:
    prompt = copilot_service._prompt_with_system_context(
        "text-segmentation",
        "judge it",
        judge_context={
            "compare_result_ref": "text-segmentation/golden/golden-1/compare/run-1/compare_result.json",
            "judge_context_ref": "text-segmentation/runs/run-1/copilot_judge/golden-1/judge_context.json",
            "baseline_ref": "text-segmentation/golden/golden-1/baseline.json",
            "diff_summary": {
                "baseline_id": "golden-1",
                "run_results_ref": "text-segmentation/runs/run-1/result.json",
                "total_score": 88,
                "node_group_count": 2,
                "failed_node_count": 1,
            },
        },
    )

    assert "<judge_context>" in prompt
    assert "<baseline_ref>text-segmentation/golden/golden-1/baseline.json</baseline_ref>" in prompt
    assert '"failed_node_count": 1' in prompt


def test_copilot_ws_does_not_read_legacy_copilot_json(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_path = tmp_path / ".studio"
    legacy_path.mkdir()
    (legacy_path / "copilot.json").write_text(
        '{"active_backend":"gemini","backends":{"gemini":{"api_key":"legacy"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        copilot_router,
        "stream_query",
        lambda **_kwargs: _events(CopilotEventDone()),
    )
    assert not hasattr(copilot_router, "read_credentials")

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})
        assert websocket.receive_json()["type"] == "done"


def test_copilot_ws_disconnect_resets_skill_sessions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_session = AsyncMock(return_value=1)
    monkeypatch.setattr(copilot_router, "reset_session", reset_session)
    monkeypatch.setattr(
        copilot_router,
        "stream_query",
        lambda **_kwargs: _events(CopilotEventText(content="hello"), CopilotEventDone()),
    )

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})
        assert websocket.receive_json()["type"] == "text_delta"
        assert websocket.receive_json()["type"] == "done"

    reset_session.assert_awaited_once_with(skill_id="text-segmentation", model_code=None)


def test_copilot_ws_forwards_stream_query_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        copilot_router,
        "stream_query",
        lambda **_kwargs: _events(CopilotEventError(message="boom")),
    )

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})

        assert websocket.receive_json() == {"type": "error", "message": "boom"}


def test_copilot_ws_serializes_copilot_event_discriminator(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        copilot_router,
        "stream_query",
        lambda **_kwargs: _events(
            CopilotEventToolUseStart(tool_name="Read", tool_input={"file_path": "SKILL.md"}),
            CopilotEventDone(),
        ),
    )

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})

        assert websocket.receive_json() == {
            "type": "tool_use_start",
            "tool_name": "Read",
            "tool_input": {"file_path": "SKILL.md"},
        }


def test_stream_query_uses_copilot_chat_active_model_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient([AssistantMessage(content=[TextBlock(text="hello")], model="claude")])
    calls: list[str | None] = []
    route = _resolved_route(base_url="https://credential.test")
    def mock_resolve(override: str | None, role: str = "copilot_chat") -> tuple[list[ResolvedRoute], StaticCredentialProvider]:
        calls.append(override)
        return _runtime([route], {route.credential_ref: "primary-secret"})

    monkeypatch.setattr(copilot_service, "_resolve_copilot_runtime", mock_resolve)
    monkeypatch.setattr(
        copilot_service, "_session_factory", lambda options: client.capture(options)
    )

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert calls == [None]
    assert client.options is not None
    assert client.options.env["ANTHROPIC_API_KEY"] == "primary-secret"
    assert client.options.env["ANTHROPIC_BASE_URL"] == "https://credential.test"
    assert isinstance(events[0], CopilotEventContextResolved)
    assert events[1:] == [CopilotEventText(content="hello"), CopilotEventDone()]


def test_stream_query_passes_selected_copilot_role_to_resolver(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The composer's copilot role picker sends the chosen role; stream_query must
    # resolve THAT role (each copilot role = its own model group), not always
    # copilot_chat. role=None falls back to copilot_chat.
    client = FakeClient([AssistantMessage(content=[TextBlock(text="hi")], model="claude")])
    seen: dict[str, object] = {}
    route = _resolved_route(base_url="https://credential.test")

    def mock_resolve(
        override: str | None, role: str = "copilot_chat"
    ) -> tuple[list[ResolvedRoute], StaticCredentialProvider]:
        seen["role"] = role
        return _runtime([route], {route.credential_ref: "primary-secret"})

    monkeypatch.setattr(copilot_service, "_resolve_copilot_runtime", mock_resolve)
    monkeypatch.setattr(
        copilot_service, "_session_factory", lambda options: client.capture(options)
    )

    asyncio.run(
        _collect(
            copilot_service.stream_query(
                "skill-a", "hi", role="copilot_opus_4_7", workspace_dir=tmp_path
            )
        )
    )
    assert seen["role"] == "copilot_opus_4_7"

    seen.clear()
    asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )
    assert seen["role"] == "copilot_chat"


def test_stream_query_resolves_secret_from_credential_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient([AssistantMessage(content=[TextBlock(text="hello")], model="claude")])
    route = ResolvedRoute(
        role_name="copilot_chat",
        route_id="test-provider:claude-test",
        endpoint_id="test-provider",
        protocol="anthropic_compatible",
        base_url="https://credential.test",
        credential_ref="cred:test-provider",
        credential_fingerprint="fp",
        provider_model_id="claude-test",
        canonical_id="claude-test",
    )

    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": (
            [route],
            StaticCredentialProvider({"cred:test-provider": "provider-secret"}),
        ),
        raising=False,
    )
    monkeypatch.setattr(
        copilot_service, "_session_factory", lambda options: client.capture(options)
    )

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert client.options is not None
    assert client.options.env["ANTHROPIC_API_KEY"] == "provider-secret"
    assert isinstance(events[0], CopilotEventContextResolved)
    assert events[1:] == [CopilotEventText(content="hello"), CopilotEventDone()]


def test_stream_query_falls_back_to_second_copilot_route_when_first_route_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    copilot_service._sessions.clear()
    routes = [
        _resolved_route(
            route_id="primary:claude",
            endpoint_id="primary",
            base_url="https://primary.test",
        ),
        _resolved_route(
            route_id="secondary:claude",
            endpoint_id="secondary",
            base_url="https://secondary.test",
        ),
    ]
    created_keys: list[str] = []
    fallback_payloads: list[dict[str, object]] = []
    secondary = FakeClient(
        [AssistantMessage(content=[TextBlock(text="fallback hello")], model="claude")]
    )

    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": _runtime(
            routes,
            {
                routes[0].credential_ref: "first-secret",
                routes[1].credential_ref: "second-secret",
            },
        ),
        raising=False,
    )
    monkeypatch.setattr(copilot_service, "_resolve_copilot_route", lambda _override, role="copilot_chat": routes[0])

    class FakeGatewayAdapter:
        def decide_fallback(self, payload: dict[str, object]) -> dict[str, object]:
            fallback_payloads.append(payload)
            return {
                "decision": "switch_route",
                "route_id": "secondary:claude",
                "retry_same": False,
                "give_up": False,
            }

    monkeypatch.setattr(
        copilot_service,
        "_gateway_adapter_factory",
        lambda: FakeGatewayAdapter(),
        raising=False,
    )

    def session_factory(options: ClaudeAgentOptions) -> FakeClient:
        api_key = options.env["ANTHROPIC_API_KEY"]
        created_keys.append(api_key)
        if api_key == "first-secret":
            return FailingClient(TimeoutError("primary timed out")).capture(options)
        return secondary.capture(options)

    monkeypatch.setattr(copilot_service, "_session_factory", session_factory)

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert created_keys == ["first-secret", "second-secret"]
    assert len(fallback_payloads) == 1
    assert fallback_payloads[0]["current_route_id"] == "primary:claude"
    assert fallback_payloads[0]["fallback_chain"] == [
        {"route_id": "primary:claude"},
        {"route_id": "secondary:claude"},
    ]
    assert secondary.options is not None
    assert secondary.options.env["ANTHROPIC_BASE_URL"] == "https://secondary.test"
    assert isinstance(events[0], CopilotEventContextResolved)
    assert events[1:] == [CopilotEventText(content="fallback hello"), CopilotEventDone()]


def test_stream_query_maps_ark_anthropic_profile_to_claude_code_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient([AssistantMessage(content=[TextBlock(text="ark hello")], model="doubao")])
    route = _resolved_route(
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        route_id="ark-official:doubao-seed-2-0-pro-260215",
        endpoint_id="ark-official",
        protocol="ark_runtime",
        provider_model_id="doubao-seed-2-0-pro-260215",
        canonical_id="doubao-seed-2-0-pro",
        call_method_id="ark_anthropic_messages",
    )
    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": _runtime([route], {route.credential_ref: "ark-secret"}),
    )
    monkeypatch.setattr(
        copilot_service, "_session_factory", lambda options: client.capture(options)
    )

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert client.options is not None
    assert client.options.env["ANTHROPIC_BASE_URL"] == (
        "https://ark.cn-beijing.volces.com/api/compatible"
    )
    assert client.options.env["ANTHROPIC_AUTH_TOKEN"] == "ark-secret"
    assert client.options.env["ANTHROPIC_MODEL"] == "doubao-seed-2-0-pro-260215"
    assert isinstance(events[0], CopilotEventContextResolved)
    assert events[1:] == [CopilotEventText(content="ark hello"), CopilotEventDone()]


def test_stream_query_reports_clear_error_after_all_copilot_routes_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    copilot_service._sessions.clear()
    routes = [
        _resolved_route(route_id="primary:claude", endpoint_id="primary"),
        _resolved_route(route_id="secondary:claude", endpoint_id="secondary"),
    ]
    created_keys: list[str] = []

    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": _runtime(
            routes,
            {
                routes[0].credential_ref: "first-secret",
                routes[1].credential_ref: "second-secret",
            },
        ),
        raising=False,
    )
    monkeypatch.setattr(copilot_service, "_resolve_copilot_route", lambda _override, role="copilot_chat": routes[0])

    def session_factory(options: ClaudeAgentOptions) -> FailingClient:
        created_keys.append(options.env["ANTHROPIC_API_KEY"])
        return FailingClient(TimeoutError("provider timed out")).capture(options)

    monkeypatch.setattr(copilot_service, "_session_factory", session_factory)

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert created_keys == ["first-secret", "second-secret"]
    assert isinstance(events[0], CopilotEventContextResolved)
    assert len(events) == 2
    assert isinstance(events[1], CopilotEventError)
    assert "all configured Copilot providers failed" in events[1].message


def test_stream_query_single_route_error_redacts_provider_secret_and_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    route = _resolved_route(route_id="primary:claude", endpoint_id="primary")
    canary = "sk-live-secret Traceback (most recent call last)"

    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": _runtime([route], {route.credential_ref: "first-secret"}),
        raising=False,
    )
    monkeypatch.setattr(
        copilot_service,
        "_session_factory",
        lambda options: FailingClient(ProcessError(canary, exit_code=1, stderr=canary)).capture(options),
    )

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert isinstance(events[-1], CopilotEventError)
    assert "sk-live-secret" not in events[-1].message
    assert "Traceback" not in events[-1].message


def test_stream_query_all_routes_failed_redacts_provider_secret_and_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    routes = [
        _resolved_route(route_id="primary:claude", endpoint_id="primary"),
        _resolved_route(route_id="secondary:claude", endpoint_id="secondary"),
    ]
    canary = "sk-live-secret Traceback (most recent call last)"
    decisions: list[dict[str, object]] = [
        {"decision": "switch_route", "route_id": "secondary:claude", "retry_same": False, "give_up": False},
        {
            "decision": "give_up",
            "error_code": "resource.no_available_route",
            "failed_route_ids": ["primary:claude", "secondary:claude"],
            "route_ids": ["primary:claude", "secondary:claude"],
            "give_up": True,
        },
    ]

    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": _runtime(
            routes,
            {
                routes[0].credential_ref: "first-secret",
                routes[1].credential_ref: "second-secret",
            },
        ),
        raising=False,
    )

    class FakeGatewayAdapter:
        def decide_fallback(self, _payload: dict[str, object]) -> dict[str, object]:
            return decisions.pop(0)

    monkeypatch.setattr(
        copilot_service,
        "_gateway_adapter_factory",
        lambda: FakeGatewayAdapter(),
        raising=False,
    )
    monkeypatch.setattr(
        copilot_service,
        "_session_factory",
        lambda options: FailingClient(RuntimeError(canary)).capture(options),
    )

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert isinstance(events[-1], CopilotEventError)
    assert "sk-live-secret" not in events[-1].message
    assert "Traceback" not in events[-1].message


def test_next_copilot_route_logs_gateway_fallback_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    route = _resolved_route(route_id="primary:claude", endpoint_id="primary")

    class FailingGatewayAdapter:
        def decide_fallback(self, payload: dict[str, object]) -> dict[str, object]:
            del payload
            raise RuntimeError("gateway adapter unavailable")

    monkeypatch.setattr(
        copilot_service,
        "_gateway_adapter_factory",
        lambda: FailingGatewayAdapter(),
        raising=False,
    )
    caplog.set_level(logging.WARNING, logger="app.services.copilot")

    next_route = copilot_service._next_copilot_route(
        routes=[route],
        route_by_id={route.route_id: route},
        current_route=route,
        failed_route_ids=[],
        retry_counts={},
        error=TimeoutError("provider timed out"),
    )

    assert next_route is None
    assert "Gateway fallback decision failed" in caplog.text
    assert "primary:claude" in caplog.text


def test_stream_query_all_routes_failed_surfaces_canonical_fallback_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    routes = [
        _resolved_route(route_id="primary:claude", endpoint_id="primary"),
        _resolved_route(route_id="secondary:claude", endpoint_id="secondary"),
    ]
    decisions: list[dict[str, object]] = [
        {
            "decision": "switch_route",
            "route_id": "secondary:claude",
            "retry_same": False,
            "give_up": False,
        },
        {
            "decision": "give_up",
            "error_code": "resource.no_available_route",
            "failed_route_ids": ["primary:claude", "secondary:claude"],
            "route_ids": ["primary:claude", "secondary:claude"],
            "give_up": True,
        },
    ]

    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": _runtime(
            routes,
            {
                routes[0].credential_ref: "first-secret",
                routes[1].credential_ref: "second-secret",
            },
        ),
    )

    class FakeGatewayAdapter:
        def decide_fallback(self, _payload: dict[str, object]) -> dict[str, object]:
            return decisions.pop(0)

    monkeypatch.setattr(
        copilot_service,
        "_gateway_adapter_factory",
        lambda: FakeGatewayAdapter(),
        raising=False,
    )

    def session_factory(options: ClaudeAgentOptions) -> FakeClient:
        api_key = options.env["ANTHROPIC_API_KEY"]
        if api_key == "first-secret":
            return FailingClient(TimeoutError("primary timed out")).capture(options)
        return FailingClient(TimeoutError("secondary timed out")).capture(options)

    monkeypatch.setattr(copilot_service, "_session_factory", session_factory)

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert isinstance(events[0], CopilotEventContextResolved)
    assert isinstance(events[-1], CopilotEventError)
    assert "resource.no_available_route" in events[-1].message
    assert "failed_route_ids" in events[-1].message
    assert "primary:claude" in events[-1].message
    assert "secondary:claude" in events[-1].message


def test_stream_query_uses_model_override_when_provided(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient([AssistantMessage(content=[TextBlock(text="hello")], model="claude")])
    calls: list[str | None] = []
    route = _resolved_route()
    def mock_resolve(override: str | None, role: str = "copilot_chat") -> tuple[list[ResolvedRoute], StaticCredentialProvider]:
        calls.append(override)
        return _runtime([route], {route.credential_ref: "primary-secret"})

    monkeypatch.setattr(copilot_service, "_resolve_copilot_runtime", mock_resolve)
    monkeypatch.setattr(
        copilot_service, "_session_factory", lambda options: client.capture(options)
    )

    events = asyncio.run(
        _collect(
            copilot_service.stream_query(
                "skill-a",
                "hi",
                model_override="test-provider:claude-test",
                workspace_dir=tmp_path,
            )
        )
    )

    assert calls == ["test-provider:claude-test"]
    assert events[-1] == CopilotEventDone()


def test_stream_query_yields_error_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": _runtime(
            [_resolved_route()],
            {"endpoint:test-provider": ""},
        ),
    )

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert isinstance(events[0], CopilotEventContextResolved)
    assert events[1:] == [CopilotEventError(message="Endpoint test-provider 未配置 API key")]


def test_stream_query_yields_clear_error_for_credential_ref_only_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": _runtime(
            [_resolved_route(credential_ref="cred:test-provider")],
            {},
        ),
    )

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert isinstance(events[0], CopilotEventContextResolved)
    assert events[1:] == [
        CopilotEventError(message="Endpoint test-provider 未配置 API key")
    ]


def test_stream_query_surfaces_resource_terminal_error_as_copilot_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Regression: the gateway raises ResourceTerminalError (base Exception, NOT a
    # ValueError) when no copilot route resolves. Left uncaught it propagated out
    # of the ws stream loop and the socket died silently (user saw nothing). It
    # must now surface as a CopilotEventError so the panel shows the reason.
    from app.core.adapters.gateway import ResourceTerminalError
    from app.services import gateway_resolver

    class _Resolver:
        def resolve_routes(self, *_args: object, **_kwargs: object) -> object:
            raise ResourceTerminalError(
                "resource.no_available_route", {"role": "copilot_chat"}
            )

    monkeypatch.setattr(gateway_resolver, "build_gateway_model_resolver", lambda: _Resolver())

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert len(events) == 1
    assert isinstance(events[0], CopilotEventError)
    assert "无可用 route" in events[0].message


def test_stream_query_preserves_resource_terminal_error_code_and_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core.adapters.gateway import ResourceTerminalError
    from app.services import gateway_resolver

    def fail_runtime(*_args: object, **_kwargs: object) -> object:
        raise ResourceTerminalError(
            "resource.no_available_route",
            {
                "role": "copilot_chat",
                "route_ids": [],
                "failed_route_ids": ["primary"],
            },
        )

    monkeypatch.setattr(gateway_resolver, "build_gateway_route_runtime", fail_runtime)

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert len(events) == 1
    assert isinstance(events[0], CopilotEventError)
    assert events[0].error_code == "resource.no_available_route"
    assert events[0].error_payload == {
        "role": "copilot_chat",
        "route_ids": [],
        "failed_route_ids": ["primary"],
    }


def test_resolve_copilot_workspace_dir_uses_skill_dir_not_process_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The copilot CLI cwd must be the skill workspace dir, never the process CWD
    # (in the packaged app that is the backend dir inside the repo, which makes
    # the SDK initialize load the repo's MCP/settings and hang).
    from app.core import config

    skills_root = tmp_path / "workspaces" / "default" / "skills"
    skill_dir = skills_root / "demo"
    skill_dir.mkdir(parents=True)
    monkeypatch.setattr(config, "default_workspace_skills_dir", lambda: skills_root)

    assert copilot_service._resolve_copilot_workspace_dir("demo") == skill_dir


def test_resolve_copilot_workspace_dir_accepts_registered_imported_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    imported_root = tmp_path / "imported-skill"
    imported_root.mkdir()
    (imported_root / "GRAPH.md").write_text("---\nname: imported-skill\n---\n", encoding="utf-8")
    index_path = tmp_path / "skill-index.json"
    index_path.write_text(
        json.dumps({"text-segmentation": {"absolute_path": str(imported_root), "l2_remote_url": ""}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "SKILL_INDEX_PATH", index_path)

    assert (
        copilot_service._resolve_copilot_workspace_dir(
            "text-segmentation",
            workspace_root=str(imported_root),
        )
        == imported_root.resolve()
    )


def test_resolve_copilot_workspace_dir_rejects_registered_root_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    registered_root = tmp_path / "registered-skill"
    requested_root = tmp_path / "wrong-skill"
    registered_root.mkdir()
    requested_root.mkdir()
    index_path = tmp_path / "skill-index.json"
    index_path.write_text(
        json.dumps({"text-segmentation": {"absolute_path": str(registered_root), "l2_remote_url": ""}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "SKILL_INDEX_PATH", index_path)

    with pytest.raises(ValueError, match="does not match registered workspace"):
        copilot_service._resolve_copilot_workspace_dir(
            "text-segmentation",
            workspace_root=str(requested_root),
        )


def test_resolve_copilot_workspace_dir_rejects_missing_workspace_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        copilot_service._resolve_copilot_workspace_dir(
            "text-segmentation",
            workspace_root=str(tmp_path / "missing"),
        )


def test_resolve_copilot_workspace_dir_rejects_relative_workspace_root() -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        copilot_service._resolve_copilot_workspace_dir(
            "text-segmentation",
            workspace_root="relative-skill",
        )


def test_stream_query_uses_imported_workspace_root_as_sdk_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    imported_root = tmp_path / "imported-skill"
    imported_root.mkdir()
    index_path = tmp_path / "skill-index.json"
    index_path.write_text(
        json.dumps({"skill-a": {"absolute_path": str(imported_root), "l2_remote_url": ""}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "SKILL_INDEX_PATH", index_path)

    client = FakeClient([AssistantMessage(content=[TextBlock(text="hello")], model="claude")])
    route = _resolved_route(base_url="https://credential.test")
    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_runtime",
        lambda _override, role="copilot_chat": _runtime(
            [route],
            {route.credential_ref: "primary-secret"},
        ),
    )
    monkeypatch.setattr(
        copilot_service, "_session_factory", lambda options: client.capture(options)
    )

    events = asyncio.run(
        _collect(
            copilot_service.stream_query(
                "skill-a",
                "hi",
                workspace_root=str(imported_root),
            )
        )
    )

    assert client.options is not None
    assert Path(client.options.cwd) == imported_root.resolve()
    assert isinstance(events[0], CopilotEventContextResolved)
    assert events[1:] == [CopilotEventText(content="hello"), CopilotEventDone()]


def test_resolve_copilot_workspace_dir_falls_back_to_skills_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    skills_root = tmp_path / "skills"
    monkeypatch.setattr(config, "default_workspace_skills_dir", lambda: skills_root)

    resolved = copilot_service._resolve_copilot_workspace_dir("missing-skill")

    assert resolved == skills_root
    assert resolved.is_dir()
    assert resolved != Path.cwd()


async def _events(*items: object) -> AsyncIterator[object]:
    for item in items:
        yield item


async def _collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


class FakeClient:
    def __init__(self, messages: list[object]) -> None:
        self.messages = messages
        self.connected = False
        self.queries: list[str] = []
        self.options: ClaudeAgentOptions | None = None

    def capture(self, options: ClaudeAgentOptions) -> Self:
        self.options = options
        return self

    async def connect(self) -> None:
        self.connected = True

    async def query(self, prompt: str, session_id: str = "default") -> None:
        del session_id
        self.queries.append(prompt)

    async def receive_response(self) -> AsyncIterator[object]:
        for message in self.messages:
            yield message


class StaticCredentialProvider:
    def __init__(self, secrets: dict[str, str]) -> None:
        self.secrets = secrets

    def get(self, ref: str) -> SecretStr:
        return SecretStr(self.secrets[ref])


def _runtime(
    routes: list[ResolvedRoute],
    secrets: dict[str, str],
) -> tuple[list[ResolvedRoute], StaticCredentialProvider]:
    return routes, StaticCredentialProvider(secrets)


class FailingClient(FakeClient):
    def __init__(self, exc: Exception) -> None:
        super().__init__([])
        self.exc = exc

    async def connect(self) -> None:
        raise self.exc


def _resolved_route(
    *,
    api_key: str | None = None,
    credential_ref: str | None = None,
    base_url: str = "https://provider.test",
    route_id: str = "test-provider:claude-test",
    endpoint_id: str = "test-provider",
    protocol: Protocol = "anthropic_compatible",
    provider_model_id: str = "claude-test",
    canonical_id: str = "claude-test",
    call_method_id: str | None = None,
) -> ResolvedRoute:
    del api_key
    return ResolvedRoute(
        role_name="copilot_chat",
        route_id=route_id,
        endpoint_id=endpoint_id,
        protocol=protocol,
        base_url=base_url,
        credential_ref=credential_ref or f"endpoint:{endpoint_id}",
        credential_fingerprint="fp",
        provider_model_id=provider_model_id,
        canonical_id=canonical_id,
        call_method_id=call_method_id,
    )
