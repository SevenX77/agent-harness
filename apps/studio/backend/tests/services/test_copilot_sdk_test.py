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
import re
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
_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def assert_english_diagnostic(message: str | None) -> str:
    assert message, "expected a user-visible diagnostic"
    assert not _CJK_RE.search(message), message
    return message


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


def test_sdk_route_test_passes_provider_model_to_options(monkeypatch: pytest.MonkeyPatch) -> None:
    # R7-9 (copilot test 卡住): the route test must send the route's OWN model to
    # the endpoint. build_options previously never set model=, so testing a generic
    # route (call_method_id=None) sent the CLI default (opus) to e.g. deepseek and
    # the test hung. Capture the options handed to the SDK and assert the model.
    captured: dict[str, object] = {}

    def factory(options: object) -> FakeClient:
        captured["model"] = options.model
        return FakeClient(messages=_echoed_token_messages())

    monkeypatch.setattr(copilot, "_sdk_test_token", lambda: _TOKEN)
    monkeypatch.setattr(copilot, "_session_factory", factory)

    result = _run(_route(), _CredProvider())

    assert result.status == "ok"
    assert captured["model"] == "claude-sonnet"


def test_copilot_sdk_route_without_profile_uses_gateway_endpoint_method_catalog() -> None:
    route = SimpleNamespace(
        route_id="qiniu-openai:deepseek.deepseek-v4-pro",
        endpoint_id="qiniu-openai",
        provider_model_id="deepseek/deepseek-v4-pro",
        protocol="openai_compatible",
        base_url="https://api.qnaigc.com/v1",
        credential_ref="endpoint:qiniu-openai",
        call_method_id=None,
    )

    prepared = copilot.resolved_route_with_copilot_sdk_candidate_method(route)
    api_key, base_url, env_overrides = copilot._resolve_route_runtime(
        prepared,
        _CredProvider(),
    )

    assert prepared.call_method_id == "anthropic_messages"
    assert api_key == "key"
    assert base_url == "https://api.qnaigc.com"
    assert env_overrides == {}


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
    message = assert_english_diagnostic(result.message)
    assert "token" in message or "tool loop" in message, message


def test_fails_on_sdk_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(error=CLIConnectionError("connection failed"))
    monkeypatch.setattr(copilot, "_session_factory", lambda _options: client)

    result = _run(_route(), _CredProvider())

    assert result.status == "failed"
    assert "Backend connection failed" in assert_english_diagnostic(result.message)


def test_fails_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(error=TimeoutError())
    monkeypatch.setattr(copilot, "_session_factory", lambda _options: client)

    result = _run(_route(), _CredProvider())

    assert result.status == "failed"
    assert "Request timed out" in assert_english_diagnostic(result.message)


def test_rate_limit_error_surfaces_as_cooling_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-F21: a provider 429 / rate-limit must NOT light the route red.

    The anthropic CLI wraps the upstream HTTP status in a ProcessError-like
    exception; we detect "rate limit" / "429" / "rate_limit" in the error text
    and return ``cooling_down`` so the FE can render a gray light + countdown.
    """
    # A bare RuntimeError carrying a recognizable rate-limit substring + a
    # parseable retry-after — both _is_rate_limit_error and
    # _retry_after_from_exception must trigger.
    rate_limit_error = RuntimeError("HTTP 429 rate limit exceeded; retry after 42 seconds")
    client = FakeClient(error=rate_limit_error)
    monkeypatch.setattr(copilot, "_session_factory", lambda _options: client)

    result = _run(_route(), _CredProvider())

    assert result.status == "cooling_down"
    assert result.retry_after_seconds == 42
    assert result.message  # message preserved for debug


def test_rate_limit_error_without_retry_after_has_none_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-F21: cooling_down still surfaces even when the upstream omits the
    Retry-After hint — the FE renders the disabled state without a countdown.
    """
    client = FakeClient(error=RuntimeError("rate_limit_exceeded; please slow down"))
    monkeypatch.setattr(copilot, "_session_factory", lambda _options: client)

    result = _run(_route(), _CredProvider())

    assert result.status == "cooling_down"
    assert result.retry_after_seconds is None


def test_is_rate_limit_error_matches_common_substrings() -> None:
    """R-F21 helper guard: the substring set we match on is narrow enough not
    to catch unrelated 4xx surfaces while still covering common 429 phrasings.
    """
    assert copilot._is_rate_limit_error(RuntimeError("HTTP 429 too many requests"))
    assert copilot._is_rate_limit_error(RuntimeError("Anthropic RateLimitError"))
    assert copilot._is_rate_limit_error(RuntimeError("rate limit exceeded"))
    assert copilot._is_rate_limit_error(RuntimeError("rate_limit_exceeded"))
    # Non-rate-limit errors must not be misclassified.
    assert not copilot._is_rate_limit_error(RuntimeError("invalid_api_key"))
    assert not copilot._is_rate_limit_error(RuntimeError("HTTP 500 server error"))
    assert not copilot._is_rate_limit_error(RuntimeError("connection reset"))


def test_retry_after_parses_common_shapes() -> None:
    """R-F21 helper: handle "retry after Ns" and "in N seconds" shapes."""
    assert copilot._retry_after_from_exception(RuntimeError("retry after 60s")) == 60
    assert copilot._retry_after_from_exception(RuntimeError("Retry-After: 30")) == 30
    assert (
        copilot._retry_after_from_exception(RuntimeError("rate limited; in 15 seconds"))
        == 15
    )
    # Missing hint → None (the FE renders the disabled state without a number).
    assert copilot._retry_after_from_exception(RuntimeError("rate limit exceeded")) is None


def test_fails_without_spawning_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    spawned = {"called": False}

    def factory(_options: object) -> object:
        spawned["called"] = True
        return FakeClient()

    monkeypatch.setattr(copilot, "_session_factory", factory)

    result = _run(_route(), _CredProvider(secret=None))

    assert result.status == "failed"
    message = assert_english_diagnostic(result.message)
    assert "API key" in message, message
    assert spawned["called"] is False, "must not spawn a CLI when credentials are missing"
