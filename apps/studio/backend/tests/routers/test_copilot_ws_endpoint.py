from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from app.models.copilot import (
    CopilotEventDone,
    CopilotEventError,
    CopilotEventText,
    CopilotEventToolUseStart,
)
from app.routers import copilot as copilot_router
from app.services import copilot as copilot_service
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock
from fastapi.testclient import TestClient
from graph_agent_gateway.registry.schema import ResolvedRoute


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
        }
    ]


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
    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_routes",
        lambda override: calls.append(override)
        or [_resolved_route(api_key="primary-secret", base_url="https://credential.test")],
    )
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
    assert events == [CopilotEventText(content="hello"), CopilotEventDone()]


def test_stream_query_falls_back_to_second_copilot_route_when_first_route_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    copilot_service._sessions.clear()
    routes = [
        _resolved_route(
            route_id="primary:claude",
            endpoint_id="primary",
            api_key="first-secret",
            base_url="https://primary.test",
        ),
        _resolved_route(
            route_id="secondary:claude",
            endpoint_id="secondary",
            api_key="second-secret",
            base_url="https://secondary.test",
        ),
    ]
    created_keys: list[str] = []
    secondary = FakeClient([AssistantMessage(content=[TextBlock(text="fallback hello")], model="claude")])

    monkeypatch.setattr(copilot_service, "_resolve_copilot_routes", lambda _override: routes, raising=False)
    monkeypatch.setattr(copilot_service, "_resolve_copilot_route", lambda _override: routes[0])

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
    assert secondary.options is not None
    assert secondary.options.env["ANTHROPIC_BASE_URL"] == "https://secondary.test"
    assert events == [CopilotEventText(content="fallback hello"), CopilotEventDone()]


def test_stream_query_maps_ark_anthropic_profile_to_claude_code_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient([AssistantMessage(content=[TextBlock(text="ark hello")], model="doubao")])
    route = _resolved_route(
        api_key="ark-secret",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        route_id="ark-official:doubao-seed-2-0-pro-260215",
        endpoint_id="ark-official",
        protocol="ark_runtime",
        provider_model_id="doubao-seed-2-0-pro-260215",
        canonical_id="doubao-seed-2-0-pro",
        call_method_id="ark_anthropic_messages",
    )
    monkeypatch.setattr(copilot_service, "_resolve_copilot_routes", lambda _override: [route])
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
    assert events == [CopilotEventText(content="ark hello"), CopilotEventDone()]


def test_stream_query_reports_clear_error_after_all_copilot_routes_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    copilot_service._sessions.clear()
    routes = [
        _resolved_route(route_id="primary:claude", endpoint_id="primary", api_key="first-secret"),
        _resolved_route(route_id="secondary:claude", endpoint_id="secondary", api_key="second-secret"),
    ]
    created_keys: list[str] = []

    monkeypatch.setattr(copilot_service, "_resolve_copilot_routes", lambda _override: routes, raising=False)
    monkeypatch.setattr(copilot_service, "_resolve_copilot_route", lambda _override: routes[0])

    def session_factory(options: ClaudeAgentOptions) -> FailingClient:
        created_keys.append(options.env["ANTHROPIC_API_KEY"])
        return FailingClient(TimeoutError("provider timed out")).capture(options)

    monkeypatch.setattr(copilot_service, "_session_factory", session_factory)

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert created_keys == ["first-secret", "second-secret"]
    assert len(events) == 1
    assert isinstance(events[0], CopilotEventError)
    assert "all configured Copilot providers failed" in events[0].message


def test_stream_query_uses_model_override_when_provided(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient([AssistantMessage(content=[TextBlock(text="hello")], model="claude")])
    calls: list[str | None] = []
    monkeypatch.setattr(
        copilot_service,
        "_resolve_copilot_routes",
        lambda override: calls.append(override) or [_resolved_route(api_key="primary-secret")],
    )
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
        "_resolve_copilot_routes",
        lambda _override: [_resolved_route(api_key="")],
    )

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert events == [CopilotEventError(message="Endpoint test-provider 未配置 API key")]


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

    def capture(self, options: ClaudeAgentOptions) -> FakeClient:
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


class FailingClient(FakeClient):
    def __init__(self, exc: Exception) -> None:
        super().__init__([])
        self.exc = exc

    async def connect(self) -> None:
        raise self.exc


def _resolved_route(
    *,
    api_key: str,
    base_url: str = "https://provider.test",
    route_id: str = "test-provider:claude-test",
    endpoint_id: str = "test-provider",
    protocol: str = "anthropic_compatible",
    provider_model_id: str = "claude-test",
    canonical_id: str = "claude-test",
    call_method_id: str | None = None,
) -> ResolvedRoute:
    return ResolvedRoute(
        role_name="copilot_chat",
        route_id=route_id,
        endpoint_id=endpoint_id,
        protocol=protocol,
        base_url=base_url,
        api_key=api_key,
        credential_fingerprint="fp",
        provider_model_id=provider_model_id,
        canonical_id=canonical_id,
        call_method_id=call_method_id,
    )
