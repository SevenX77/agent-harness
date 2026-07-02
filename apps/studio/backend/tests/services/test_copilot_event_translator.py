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
    StreamEvent,
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


def _stream_event(
    event: dict[str, object], parent_tool_use_id: str | None = None
) -> StreamEvent:
    return StreamEvent(
        uuid="uuid-1",
        session_id="session-1",
        event=event,
        parent_tool_use_id=parent_tool_use_id,
    )


def _text_delta(text: str) -> StreamEvent:
    return _stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}
    )


def _thinking_delta(thinking: str) -> StreamEvent:
    return _stream_event(
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": thinking},
        }
    )


def test_translate_text_event() -> None:
    # F8 no-stream fallback: without partial deltas the whole block is emitted.
    events = copilot.SdkMessageTranslator().translate(
        AssistantMessage(content=[TextBlock(text="hello")], model="claude"),
    )

    assert events == [CopilotEventText(content="hello")]


def test_translate_thinking_block_event() -> None:
    # F1: extended-thinking must be streamed (collapsible, never dropped).
    events = copilot.SdkMessageTranslator().translate(
        AssistantMessage(
            content=[ThinkingBlock(thinking="let me reason...", signature="sig")],
            model="claude",
        ),
    )

    assert events == [CopilotEventThinking(content="let me reason...")]


def test_translate_thinking_then_text_preserves_order() -> None:
    # Thinking precedes the visible answer in the same assistant turn; both
    # events must be emitted in order so the UI can render the collapsible
    # Thought above the answer text.
    events = copilot.SdkMessageTranslator().translate(
        AssistantMessage(
            content=[
                ThinkingBlock(thinking="reasoning", signature="sig"),
                TextBlock(text="answer"),
            ],
            model="claude",
        ),
    )

    assert events == [
        CopilotEventThinking(content="reasoning"),
        CopilotEventText(content="answer"),
    ]


def test_translate_tool_use_start_event() -> None:
    translator = copilot.SdkMessageTranslator()

    events = translator.translate(
        AssistantMessage(
            content=[ToolUseBlock(id="tool-1", name="Read", input={"file_path": "SKILL.md"})],
            model="claude",
        ),
    )

    assert events == [
        CopilotEventToolUseStart(tool_name="Read", tool_input={"file_path": "SKILL.md"})
    ]
    assert translator.tool_names == {"tool-1": "Read"}


def test_translate_renders_search_tools_instead_of_fake_failures() -> None:
    """Glob/Grep 由权限层放行并真实执行;翻译器再报「V1 不支持工具」= 执行成功
    UI 报失败的三处口径不一致(实测过的假失败主因),必须渲染而不是报错。"""
    tool_names: dict[str, str] = {}

    events = copilot._translate_sdk_message(
        AssistantMessage(
            content=[
                ToolUseBlock(id="tool-g", name="Glob", input={"pattern": "**/*.md"}),
                ToolUseBlock(id="tool-r", name="Grep", input={"pattern": "phase"}),
            ],
            model="claude",
        ),
        tool_names,
    )

    assert events == [
        CopilotEventToolUseStart(tool_name="Glob", tool_input={"pattern": "**/*.md"}),
        CopilotEventToolUseStart(tool_name="Grep", tool_input={"pattern": "phase"}),
    ]
    assert tool_names == {"tool-g": "Glob", "tool-r": "Grep"}


def test_translate_renders_studio_mcp_tools() -> None:
    tool_names: dict[str, str] = {}

    events = copilot._translate_sdk_message(
        AssistantMessage(
            content=[
                ToolUseBlock(id="tool-m", name="mcp__studio__compile_skill", input={"skill_id": "s"})
            ],
            model="claude",
        ),
        tool_names,
    )

    assert events == [
        CopilotEventToolUseStart(
            tool_name="mcp__studio__compile_skill", tool_input={"skill_id": "s"}
        )
    ]


def test_translate_tool_result_event() -> None:
    translator = copilot.SdkMessageTranslator()
    translator.tool_names["tool-1"] = "Read"

    events = translator.translate(
        AssistantMessage(
            content=[ToolResultBlock(tool_use_id="tool-1", content="ok")], model="claude"
        ),
    )

    assert events == [
        CopilotEventToolUseResult(tool_name="Read", success=True, result_summary="ok")
    ]


def test_translate_tool_result_in_user_message() -> None:
    # The real SDK returns tool results in UserMessage, not AssistantMessage —
    # these must still surface (F1 "不省略"), keyed back to the tool name.
    translator = copilot.SdkMessageTranslator()
    translator.tool_names["tool-1"] = "Read"

    events = translator.translate(
        UserMessage(content=[ToolResultBlock(tool_use_id="tool-1", content="file contents")]),
    )

    assert events == [
        CopilotEventToolUseResult(tool_name="Read", success=True, result_summary="file contents")
    ]


def test_translate_failed_tool_result_in_user_message() -> None:
    # F8: a failed tool is a RECOVERABLE fact the model often works around —
    # transcribe it as tool_use_result(success=False), never as CopilotEventError
    # (reserved for fatal stream-ending errors; the frontend settles the message
    # state machine on it).
    translator = copilot.SdkMessageTranslator()
    translator.tool_names["tool-1"] = "Bash"

    events = translator.translate(
        UserMessage(
            content=[ToolResultBlock(tool_use_id="tool-1", content="denied", is_error=True)]
        ),
    )

    assert events == [
        CopilotEventToolUseResult(tool_name="Bash", success=False, result_summary="denied")
    ]


def test_translate_user_message_with_plain_text_is_ignored() -> None:
    # A plain user-text message (not a tool result) is not echoed back.
    assert copilot.SdkMessageTranslator().translate(UserMessage(content="hello")) == []


def test_translate_result_message_is_done() -> None:
    events = copilot.SdkMessageTranslator().translate(
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="session",
        ),
    )

    assert events == [CopilotEventDone()]


def test_tool_failure_translates_to_failed_tool_result() -> None:
    translator = copilot.SdkMessageTranslator()
    translator.tool_names["tool-1"] = "Bash"

    events = translator.translate(
        AssistantMessage(
            content=[
                ToolResultBlock(tool_use_id="tool-1", content="permission denied", is_error=True)
            ],
            model="claude",
        ),
    )

    assert events == [
        CopilotEventToolUseResult(
            tool_name="Bash", success=False, result_summary="permission denied"
        )
    ]


def test_unlisted_tool_use_is_transcribed_faithfully() -> None:
    # F8: the SDK actually EXECUTES read-only tools outside the pre-allowed list
    # (Glob/Grep, live evidence 2026-07-02). The translator reports what
    # happened — policy is enforced at the SDK layer (allowed_tools /
    # can_use_tool), not by the transcript. The old "V1 不支持工具 X" error was
    # a lie that also broke the tool-name mapping for the result event AND
    # split the frontend message (error settles the state machine).
    translator = copilot.SdkMessageTranslator()

    start_events = translator.translate(
        AssistantMessage(
            content=[ToolUseBlock(id="tool-9", name="Glob", input={"pattern": "**/*.md"})],
            model="claude",
        ),
    )
    result_events = translator.translate(
        UserMessage(content=[ToolResultBlock(tool_use_id="tool-9", content="a.md")]),
    )

    assert start_events == [
        CopilotEventToolUseStart(tool_name="Glob", tool_input={"pattern": "**/*.md"})
    ]
    assert result_events == [
        CopilotEventToolUseResult(tool_name="Glob", success=True, result_summary="a.md")
    ]


def test_stream_text_delta_is_incremental_text() -> None:
    # F8-1: partial text deltas stream through as incremental text events.
    translator = copilot.SdkMessageTranslator()

    assert translator.translate(_text_delta("Hel")) == [CopilotEventText(content="Hel")]
    assert translator.translate(_text_delta("lo")) == [CopilotEventText(content="lo")]


def test_stream_thinking_delta_is_incremental_thinking() -> None:
    # F8-1: reasoning content streams live, not as a whole block at the end.
    translator = copilot.SdkMessageTranslator()

    assert translator.translate(_thinking_delta("hmm")) == [CopilotEventThinking(content="hmm")]


def test_stream_lifecycle_and_non_text_deltas_are_silent() -> None:
    # F8-1: message lifecycle, signature and tool-input deltas produce no UI events.
    translator = copilot.SdkMessageTranslator()
    silent_events = [
        {"type": "message_start", "message": {}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "sig"},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"file'},
        },
        {"type": "content_block_stop", "index": 0},
        {"type": "message_stop"},
    ]

    for raw in silent_events:
        assert translator.translate(_stream_event(raw)) == []


def test_stream_subagent_deltas_are_skipped() -> None:
    # F8-1: deltas belonging to a subagent (parent_tool_use_id) stay out of the
    # main transcript.
    translator = copilot.SdkMessageTranslator()
    event = _stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "x"}},
        parent_tool_use_id="tool-99",
    )

    assert translator.translate(event) == []


def test_complete_message_suppresses_streamed_text_and_thinking() -> None:
    # F8-2: after partial deltas streamed, the complete AssistantMessage must not
    # re-emit the same text/thinking — but tool_use blocks still come from it.
    translator = copilot.SdkMessageTranslator()
    translator.translate(_thinking_delta("reasoning"))
    translator.translate(_text_delta("Hel"))
    translator.translate(_text_delta("lo"))

    events = translator.translate(
        AssistantMessage(
            content=[
                ThinkingBlock(thinking="reasoning", signature="sig"),
                TextBlock(text="Hello"),
                ToolUseBlock(id="tool-1", name="Read", input={"file_path": "SKILL.md"}),
            ],
            model="claude",
        ),
    )

    assert events == [
        CopilotEventToolUseStart(tool_name="Read", tool_input={"file_path": "SKILL.md"})
    ]


def test_suppression_resets_after_each_complete_message() -> None:
    # F8-2/F8-3: suppression is per assistant message — a later message that had
    # no partial deltas (no-stream provider) still emits its whole blocks.
    translator = copilot.SdkMessageTranslator()
    translator.translate(_text_delta("first"))
    translator.translate(AssistantMessage(content=[TextBlock(text="first")], model="claude"))

    events = translator.translate(
        AssistantMessage(content=[TextBlock(text="second")], model="claude"),
    )

    assert events == [CopilotEventText(content="second")]


def test_build_options_enables_partial_messages(tmp_path: Path) -> None:
    # F8-1: without include_partial_messages the SDK only yields whole messages.
    options = copilot.build_options(None, "key", tmp_path)

    assert options.include_partial_messages is True


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
    from app.core import config

    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")

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
    captured_options: list[object] = []

    def factory(options: object) -> FakeClient:
        captured_options.append(options)
        return client

    monkeypatch.setattr(copilot, "_session_factory", factory)
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
    # 规则文档在会话级 system_prompt,不随每轮 query 重发;无 view context 时
    # query 就是裸用户消息。
    assert "聚焦 Studio 上下文" in str(getattr(captured_options[0], "system_prompt", ""))
    assert client.queries[0] == "user text"


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
