from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.models.copilot import (
    CopilotEventDone,
    CopilotEventError,
    CopilotEventText,
    CopilotEventToolUseResult,
    CopilotEventToolUseStart,
)
from app.services import copilot
from claude_agent_sdk import CLIConnectionError
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


class FakeClient:
    def __init__(
        self, messages: list[object] | None = None, error: Exception | None = None
    ) -> None:
        self.messages = messages or []
        self.error = error
        self.queries: list[str] = []
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def query(self, prompt: str, session_id: str = "default") -> None:
        del session_id
        self.queries.append(prompt)
        if self.error is not None:
            raise self.error

    async def receive_response(self) -> AsyncIterator[object]:
        for message in self.messages:
            yield message


@pytest.fixture(autouse=True)
def clean_copilot_state() -> Iterator[None]:
    asyncio.run(copilot.cleanup_all_sessions())
    copilot._view_contexts.clear()
    yield
    asyncio.run(copilot.cleanup_all_sessions())
    copilot._view_contexts.clear()


def test_translate_text_event() -> None:
    events = copilot._translate_sdk_message(
        AssistantMessage(content=[TextBlock(text="hello")], model="claude"),
        {},
    )

    assert events == [CopilotEventText(content="hello")]


def test_translate_tool_use_start_event() -> None:
    tool_names: dict[str, str] = {}

    events = copilot._translate_sdk_message(
        AssistantMessage(
            content=[ToolUseBlock(id="tool-1", name="Read", input={"file_path": "SKILL.md"})],
            model="claude",
        ),
        tool_names,
    )

    assert events == [
        CopilotEventToolUseStart(tool_name="Read", tool_input={"file_path": "SKILL.md"})
    ]
    assert tool_names == {"tool-1": "Read"}


def test_translate_tool_result_event() -> None:
    events = copilot._translate_sdk_message(
        AssistantMessage(
            content=[ToolResultBlock(tool_use_id="tool-1", content="ok")], model="claude"
        ),
        {"tool-1": "Read"},
    )

    assert events == [
        CopilotEventToolUseResult(tool_name="Read", success=True, result_summary="ok")
    ]


def test_translate_result_message_is_done() -> None:
    events = copilot._translate_sdk_message(
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="session",
        ),
        {},
    )

    assert events == [CopilotEventDone()]


def test_tool_failure_translates_to_error_event() -> None:
    events = copilot._translate_sdk_message(
        AssistantMessage(
            content=[
                ToolResultBlock(tool_use_id="tool-1", content="permission denied", is_error=True)
            ],
            model="claude",
        ),
        {"tool-1": "Bash"},
    )

    assert events == [CopilotEventError(message="工具 Bash 失败: permission denied")]


def test_stream_query_errors_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        copilot, "_resolve_copilot_provider", lambda _model_override: _resolved_provider()
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    events = asyncio.run(_collect(copilot.stream_query("skill-a", "hi")))

    assert events == [
        CopilotEventError(message="Provider OC_CL_ANT 未配置 API key (env: ANTHROPIC_API_KEY)")
    ]


def test_stream_query_errors_when_model_override_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def resolve_copilot_provider(_model_override: str | None) -> object:
        raise KeyError("BAD_MODEL")

    monkeypatch.setattr(copilot, "_resolve_copilot_provider", resolve_copilot_provider)

    events = asyncio.run(
        _collect(copilot.stream_query("skill-a", "hi", model_override="BAD_MODEL"))
    )

    assert events == [CopilotEventError(message="未知模型: 'BAD_MODEL'")]


def test_stream_query_timeout_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        copilot,
        "_session_factory",
        lambda _options: FakeClient(error=TimeoutError()),
    )
    monkeypatch.setattr(
        copilot, "_resolve_copilot_provider", lambda _model_override: _resolved_provider()
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")

    events = asyncio.run(_collect(copilot.stream_query("skill-a", "hi", workspace_dir=tmp_path)))

    assert events == [CopilotEventError(message="请求超时, 检查网络 / 代理")]


def test_stream_query_sdk_network_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        copilot,
        "_session_factory",
        lambda _options: FakeClient(error=CLIConnectionError("connection failed")),
    )
    monkeypatch.setattr(
        copilot, "_resolve_copilot_provider", lambda _model_override: _resolved_provider()
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")

    events = asyncio.run(_collect(copilot.stream_query("skill-a", "hi", workspace_dir=tmp_path)))

    assert events == [
        CopilotEventError(
            message="后端连接失败 (DeepSeek 端点不可达 / 大陆需代理): connection failed"
        )
    ]


def test_stream_query_uses_system_prompt_and_yields_done(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient(
        messages=[AssistantMessage(content=[TextBlock(text="hello")], model="claude")]
    )
    monkeypatch.setattr(copilot, "_session_factory", lambda _options: client)
    monkeypatch.setattr(
        copilot, "_resolve_copilot_provider", lambda _model_override: _resolved_provider()
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")

    events = asyncio.run(
        _collect(copilot.stream_query("skill-a", "user text", workspace_dir=tmp_path))
    )

    assert events == [CopilotEventText(content="hello"), CopilotEventDone()]
    assert client.connected is True
    assert "聚焦 Studio 上下文" in client.queries[0]
    assert "user text" in client.queries[0]


async def _collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


def _resolved_provider() -> object:
    provider_def = SimpleNamespace(
        api_key_env="ANTHROPIC_API_KEY",
        api_key_env_fallback=None,
        base_url="https://provider.test",
    )
    model_def = SimpleNamespace(code="CL46T")
    return SimpleNamespace(
        provider_code="OC_CL_ANT",
        provider_def=provider_def,
        model_def=model_def,
    )
