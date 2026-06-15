from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.models.copilot import (
    CopilotEventContextResolved,
    CopilotEventDone,
    CopilotEventError,
    CopilotEventText,
    CopilotEventThinking,
    CopilotEventToolUseResult,
    CopilotEventToolUseStart,
)
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
    RolesData,
)
from app.services import copilot
from claude_agent_sdk import CLIConnectionError
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from pydantic import SecretStr


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


def test_translate_thinking_block_event() -> None:
    # F1: extended-thinking must be streamed (collapsible, never dropped).
    events = copilot._translate_sdk_message(
        AssistantMessage(
            content=[ThinkingBlock(thinking="let me reason...", signature="sig")],
            model="claude",
        ),
        {},
    )

    assert events == [CopilotEventThinking(content="let me reason...")]


def test_translate_thinking_then_text_preserves_order() -> None:
    # Thinking precedes the visible answer in the same assistant turn; both
    # events must be emitted in order so the UI can render the collapsible
    # Thought above the answer text.
    events = copilot._translate_sdk_message(
        AssistantMessage(
            content=[
                ThinkingBlock(thinking="reasoning", signature="sig"),
                TextBlock(text="answer"),
            ],
            model="claude",
        ),
        {},
    )

    assert events == [
        CopilotEventThinking(content="reasoning"),
        CopilotEventText(content="answer"),
    ]


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


def test_translate_tool_result_in_user_message() -> None:
    # The real SDK returns tool results in UserMessage, not AssistantMessage —
    # these must still surface (F1 "不省略"), keyed back to the tool name.
    events = copilot._translate_sdk_message(
        UserMessage(content=[ToolResultBlock(tool_use_id="tool-1", content="file contents")]),
        {"tool-1": "Read"},
    )

    assert events == [
        CopilotEventToolUseResult(tool_name="Read", success=True, result_summary="file contents")
    ]


def test_translate_failed_tool_result_in_user_message() -> None:
    events = copilot._translate_sdk_message(
        UserMessage(
            content=[ToolResultBlock(tool_use_id="tool-1", content="denied", is_error=True)]
        ),
        {"tool-1": "Bash"},
    )

    assert events == [CopilotEventError(message="工具 Bash 失败: denied")]


def test_translate_user_message_with_plain_text_is_ignored() -> None:
    # A plain user-text message (not a tool result) is not echoed back.
    assert copilot._translate_sdk_message(UserMessage(content="hello"), {}) == []


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
        copilot,
        "_resolve_copilot_runtime",
        lambda _model_override, role="copilot_chat": _runtime(_resolved_route(), ""),
    )
    events = asyncio.run(_collect(copilot.stream_query("skill-a", "hi")))

    assert isinstance(events[0], CopilotEventContextResolved)  # F4: first event echoes context
    assert events[1:] == [CopilotEventError(message="Endpoint anthropic-official 未配置 API key")]


def test_stream_query_errors_when_model_override_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def resolve_copilot_runtime(_model_override: str | None, role: str = "copilot_chat") -> object:
        raise KeyError("BAD_MODEL")

    monkeypatch.setattr(copilot, "_resolve_copilot_runtime", resolve_copilot_runtime)

    events = asyncio.run(
        _collect(copilot.stream_query("skill-a", "hi", model_override="BAD_MODEL"))
    )

    assert events == [CopilotEventError(message="未知模型: 'BAD_MODEL'")]


def test_resolve_copilot_runtime_uses_gateway_model_resolver(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from graph_agent_gateway.resolver import ModelResolver

    route_id = "anthropic-official:claude-sonnet"
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                display_name="Anthropic",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.example",
                api_key="secret",
            )
        },
        provider_routes={
            route_id: ProviderRoute(
                route_id=route_id,
                endpoint_id="anthropic-official",
                route_slug="claude-sonnet",
                provider_model_id="claude-sonnet",
                canonical_id="claude-sonnet",
            )
        },
    )
    roles = RolesData(
        roles={
            "copilot_chat": RoleEntry(
                role_kind="copilot",
                fallback_chain=[RoleRouteEntry(route_id=route_id)],
            )
        }
    )
    roles_path = tmp_path / "llm_roles.yaml"
    roles_path.touch()
    calls: list[tuple[str, str | None]] = []
    original_resolve_routes = ModelResolver.resolve_routes

    def recording_resolve_routes(
        self: ModelResolver,
        role_name: str,
        *,
        route_override: str | None = None,
    ):
        calls.append((role_name, route_override))
        return original_resolve_routes(self, role_name, route_override=route_override)

    from app.services import gateway_resolver
    monkeypatch.setattr(gateway_resolver, "load_credentials", lambda: credentials)
    monkeypatch.setattr(gateway_resolver, "default_roles_path", lambda: roles_path)
    monkeypatch.setattr(gateway_resolver, "load_roles_file", lambda _path: roles)
    monkeypatch.setattr(ModelResolver, "resolve_routes", recording_resolve_routes)

    routes, credential_provider = copilot._resolve_copilot_runtime(route_id)

    assert calls == [("copilot_chat", route_id)]
    assert routes[0].route_id == route_id
    assert credential_provider.get("endpoint:anthropic-official").get_secret_value() == "secret"


def test_stream_query_timeout_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        copilot,
        "_session_factory",
        lambda _options: FakeClient(error=TimeoutError()),
    )
    monkeypatch.setattr(
        copilot,
        "_resolve_copilot_runtime",
        lambda _model_override, role="copilot_chat": _runtime(_resolved_route()),
    )

    events = asyncio.run(_collect(copilot.stream_query("skill-a", "hi", workspace_dir=tmp_path)))

    assert isinstance(events[0], CopilotEventContextResolved)
    assert events[1:] == [CopilotEventError(message="请求超时, 检查网络 / 代理")]


def test_stream_query_sdk_network_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        copilot,
        "_session_factory",
        lambda _options: FakeClient(error=CLIConnectionError("connection failed")),
    )
    monkeypatch.setattr(
        copilot,
        "_resolve_copilot_runtime",
        lambda _model_override, role="copilot_chat": _runtime(_resolved_route()),
    )

    events = asyncio.run(_collect(copilot.stream_query("skill-a", "hi", workspace_dir=tmp_path)))

    assert isinstance(events[0], CopilotEventContextResolved)
    assert events[1:] == [
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
        copilot,
        "_resolve_copilot_runtime",
        lambda _model_override, role="copilot_chat": _runtime(_resolved_route()),
    )

    events = asyncio.run(
        _collect(copilot.stream_query("skill-a", "user text", workspace_dir=tmp_path))
    )

    assert isinstance(events[0], CopilotEventContextResolved)  # F4: context echo first
    assert events[0].summary.startswith("本轮注入")
    assert events[1:] == [CopilotEventText(content="hello"), CopilotEventDone()]
    assert client.connected is True
    assert "聚焦 Studio 上下文" in client.queries[0]
    assert "user text" in client.queries[0]


async def _collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


class StaticCredentialProvider:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def get(self, ref: str) -> SecretStr:
        return SecretStr(self.secret)


def _runtime(
    route: SimpleNamespace,
    secret: str = "key",
) -> tuple[list[SimpleNamespace], StaticCredentialProvider]:
    return [route], StaticCredentialProvider(secret)


def _resolved_route() -> SimpleNamespace:
    return SimpleNamespace(
        endpoint_id="anthropic-official",
        route_id="anthropic-official:claude-sonnet",
        provider_model_id="claude-sonnet",
        base_url="https://provider.test",
        credential_ref="endpoint:anthropic-official",
        call_method_id=None,
    )
