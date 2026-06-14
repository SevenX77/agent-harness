"""Unit tests for the real-ClaudeSDKClient copilot route test (COPILOT_ASSIST-4).

The copilot test must exercise the REAL `ClaudeSDKClient` path and issue a REAL
tool call (design §3.4: "发真工具调用、验 spawn/env/tool loop") — a passing test
must mean copilot actually works. These tests drive the verdict logic by
injecting a `FakeClient` at the `_session_factory` seam; the forced-tool-call
prompt + random-token file is what makes the tool call non-optional in
production (so it is deterministic, not flaky).

The real spawn/env contract is only discharged by a creds-gated live test
(separate); these mocked tests verify the wiring/verdict/error-mapping only.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from app.services import copilot
from claude_agent_sdk import CLIConnectionError
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from pydantic import SecretStr


class FakeClient:
    def __init__(
        self, messages: list[object] | None = None, error: Exception | None = None
    ) -> None:
        self.messages = messages or []
        self.error = error
        self.connected = False
        self.closed = False
        self.queries: list[str] = []

    async def connect(self) -> None:
        self.connected = True

    async def query(self, prompt: str, session_id: str = "default") -> None:
        del session_id
        self.queries.append(prompt)

    async def receive_response(self) -> AsyncIterator[object]:
        if self.error is not None:
            raise self.error
        for message in self.messages:
            yield message

    async def disconnect(self) -> None:
        self.closed = True


class _CredProvider:
    def __init__(self, secret: str | None = "key") -> None:
        self.secret = secret

    def get(self, ref: str) -> SecretStr:
        if self.secret is None:
            raise KeyError(ref)
        return SecretStr(self.secret)


def _route() -> SimpleNamespace:
    return SimpleNamespace(
        route_id="anthropic-official:claude-sonnet",
        endpoint_id="anthropic-official",
        provider_model_id="claude-sonnet",
        base_url="https://api.anthropic.example",
        credential_ref="endpoint:anthropic-official",
        call_method_id=None,
    )


def _result_message() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="session",
    )


_TOKEN = "tok123deadbeef"


def _echoed_token_messages() -> list[object]:
    # Mirrors the real SDK stream: the model issues a tool call (Bash/Read), the
    # SDK runs it and returns the result in a UserMessage (which the translator
    # drops), then the model echoes the file contents (the token) in a TextBlock.
    return [
        AssistantMessage(
            content=[ToolUseBlock(id="t1", name="Read", input={"file_path": "copilot_probe.txt"})],
            model="claude",
        ),
        # In the real SDK this is a UserMessage(ToolResultBlock); the translator
        # ignores it. The proof of a working tool loop is the echoed token below.
        AssistantMessage(content=[ToolResultBlock(tool_use_id="t1", content=_TOKEN)], model="claude"),
        AssistantMessage(content=[TextBlock(text=_TOKEN)], model="claude"),
        _result_message(),
    ]


def _run(route: object, provider: object):
    return asyncio.run(copilot.run_route_sdk_test(route, provider, timeout_s=5.0))


def test_passes_when_model_echoes_the_probe_token(monkeypatch: pytest.MonkeyPatch) -> None:
    # The model can only echo the random token by actually reading the file, so
    # token-echoed ⟺ the tool loop ran.
    monkeypatch.setattr(copilot, "_sdk_test_token", lambda: _TOKEN)
    client = FakeClient(messages=_echoed_token_messages())
    monkeypatch.setattr(copilot, "_session_factory", lambda _options: client)

    result = _run(_route(), _CredProvider())

    assert result.status == "ok"
    assert result.route_id == "anthropic-official:claude-sonnet"
    assert client.queries, "a real query must be sent to the SDK"
    assert client.closed is True, "the client must be closed locally (not via global cleanup)"


def test_fails_when_token_is_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    # No token in the answer = the model never really read the file = the tool
    # loop wasn't exercised → must FAIL (copilot's whole job is using tools).
    monkeypatch.setattr(copilot, "_sdk_test_token", lambda: _TOKEN)
    client = FakeClient(
        messages=[AssistantMessage(content=[TextBlock(text="I can't read files.")], model="claude"), _result_message()]
    )
    monkeypatch.setattr(copilot, "_session_factory", lambda _options: client)

    result = _run(_route(), _CredProvider())

    assert result.status == "failed"
    assert "token" in (result.message or "") or "读取" in (result.message or ""), result.message


def test_fails_on_sdk_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(error=CLIConnectionError("connection failed"))
    monkeypatch.setattr(copilot, "_session_factory", lambda _options: client)

    result = _run(_route(), _CredProvider())

    assert result.status == "failed"
    assert "后端连接失败" in (result.message or ""), result.message


def test_fails_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(error=TimeoutError())
    monkeypatch.setattr(copilot, "_session_factory", lambda _options: client)

    result = _run(_route(), _CredProvider())

    assert result.status == "failed"
    assert "请求超时" in (result.message or ""), result.message


def test_fails_without_spawning_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    spawned = {"called": False}

    def factory(_options: object) -> object:
        spawned["called"] = True
        return FakeClient()

    monkeypatch.setattr(copilot, "_session_factory", factory)

    result = _run(_route(), _CredProvider(secret=None))

    assert result.status == "failed"
    assert "API key" in (result.message or ""), result.message
    assert spawned["called"] is False, "must not spawn a CLI when credentials are missing"
