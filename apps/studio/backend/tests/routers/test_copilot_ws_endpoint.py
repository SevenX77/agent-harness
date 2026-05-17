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
from graph_agent.config.llm_config import ModelDef, ProviderDef, ResolvedProvider, ResolvedRole


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
    fake_config = FakeConfig()
    client = FakeClient([AssistantMessage(content=[TextBlock(text="hello")], model="claude")])
    monkeypatch.setattr(copilot_service, "load_config", lambda: fake_config)
    monkeypatch.setenv("PRIMARY_KEY", "primary-secret")
    monkeypatch.setattr(
        copilot_service, "_session_factory", lambda options: client.capture(options)
    )

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert fake_config.role_calls == ["copilot_chat"]
    assert fake_config.model_calls == []
    assert client.options is not None
    assert client.options.env["ANTHROPIC_API_KEY"] == "primary-secret"
    assert client.options.env["ANTHROPIC_BASE_URL"] == "https://provider.test"
    assert events == [CopilotEventText(content="hello"), CopilotEventDone()]


def test_stream_query_uses_model_override_when_provided(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_config = FakeConfig()
    client = FakeClient([AssistantMessage(content=[TextBlock(text="hello")], model="claude")])
    monkeypatch.setattr(copilot_service, "load_config", lambda: fake_config)
    monkeypatch.setenv("PRIMARY_KEY", "primary-secret")
    monkeypatch.setattr(
        copilot_service, "_session_factory", lambda options: client.capture(options)
    )

    events = asyncio.run(
        _collect(
            copilot_service.stream_query(
                "skill-a",
                "hi",
                model_override="CL46T",
                workspace_dir=tmp_path,
            )
        )
    )

    assert fake_config.role_calls == []
    assert fake_config.model_calls == ["CL46T"]
    assert events[-1] == CopilotEventDone()


def test_stream_query_yields_error_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PRIMARY_KEY", raising=False)
    monkeypatch.delenv("FALLBACK_KEY", raising=False)
    monkeypatch.setattr(copilot_service, "load_config", lambda: FakeConfig())

    events = asyncio.run(
        _collect(copilot_service.stream_query("skill-a", "hi", workspace_dir=tmp_path))
    )

    assert events == [
        CopilotEventError(message="Provider TEST_PROVIDER 未配置 API key (env: PRIMARY_KEY)")
    ]


async def _events(*items: object) -> AsyncIterator[object]:
    for item in items:
        yield item


async def _collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


class FakeConfig:
    def __init__(self) -> None:
        self.role_calls: list[str] = []
        self.model_calls: list[str] = []

    def resolve_role(self, role_name: str) -> ResolvedRole:
        self.role_calls.append(role_name)
        return _resolved_role("copilot_chat", "CL46T")

    def resolve_model(self, model_code: str) -> ResolvedRole:
        self.model_calls.append(model_code)
        return _resolved_role("_model_override::CL46T", model_code)


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


def _resolved_role(role_name: str, active_model_code: str) -> ResolvedRole:
    model = ModelDef(
        code=active_model_code,
        name="Claude Test",
        providers={"TEST_PROVIDER": "claude-test"},
    )
    provider = ProviderDef(
        code="TEST_PROVIDER",
        name="Test Provider",
        type="anthropic_compatible",
        api_key_env="PRIMARY_KEY",
        api_key_env_fallback="FALLBACK_KEY",
        base_url="https://provider.test",
    )
    return ResolvedRole(
        role_name=role_name,
        temperature=0.7,
        system_prompt_prefix="",
        active_model_code=active_model_code,
        model_fallback=False,
        call_chain=[
            ResolvedProvider(
                provider_code="TEST_PROVIDER",
                provider_def=provider,
                model_name="claude-test",
                model_def=model,
            )
        ],
    )
