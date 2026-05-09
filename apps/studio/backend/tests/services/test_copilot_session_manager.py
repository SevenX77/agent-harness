from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.services import copilot
from claude_agent_sdk import ClaudeAgentOptions


class FakeClient:
    def __init__(self, options: ClaudeAgentOptions) -> None:
        self.options = options
        self.disconnect_calls = 0

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


@pytest.fixture(autouse=True)
def clean_sessions() -> Iterator[None]:
    asyncio.run(copilot.cleanup_all_sessions())
    yield
    asyncio.run(copilot.cleanup_all_sessions())


def test_get_or_create_session_reuses_same_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeClient] = []

    def factory(options: ClaudeAgentOptions) -> FakeClient:
        client = FakeClient(options)
        created.append(client)
        return client

    monkeypatch.setattr(copilot, "_session_factory", factory)

    async def scenario() -> None:
        first = await copilot.get_or_create_session("skill-a", "claude", "same-key", tmp_path)
        second = await copilot.get_or_create_session("skill-a", "claude", "same-key", tmp_path)

        assert first is second

    asyncio.run(scenario())
    assert len(created) == 1


def test_reset_session_can_delete_skill_backend_pairs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeClient] = []

    def factory(options: ClaudeAgentOptions) -> FakeClient:
        client = FakeClient(options)
        created.append(client)
        return client

    monkeypatch.setattr(copilot, "_session_factory", factory)

    async def scenario() -> None:
        await copilot.get_or_create_session("skill-a", "claude", "old-key", tmp_path)
        await copilot.get_or_create_session("skill-a", "claude", "new-key", tmp_path)
        await copilot.get_or_create_session("skill-a", "deepseek", "deepseek-key", tmp_path)
        await copilot.get_or_create_session("skill-b", "claude", "other-key", tmp_path)

        removed = await copilot.reset_session("skill-a", "claude")

        assert removed == 2
        assert sum(client.disconnect_calls for client in created) == 2

    asyncio.run(scenario())


def test_reset_session_can_delete_all_backend_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(copilot, "_session_factory", FakeClient)

    async def scenario() -> None:
        await copilot.get_or_create_session("skill-a", "claude", "a-key", tmp_path)
        await copilot.get_or_create_session("skill-b", "claude", "b-key", tmp_path)
        await copilot.get_or_create_session("skill-a", "deepseek", "d-key", tmp_path)

        removed = await copilot.reset_session(None, "claude")

        assert removed == 2

    asyncio.run(scenario())


def test_reset_session_can_delete_all_skill_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(copilot, "_session_factory", FakeClient)

    async def scenario() -> None:
        await copilot.get_or_create_session("skill-a", "claude", "a-key", tmp_path)
        await copilot.get_or_create_session("skill-a", "deepseek", "d-key", tmp_path)
        await copilot.get_or_create_session("skill-b", "claude", "b-key", tmp_path)

        removed = await copilot.reset_session("skill-a", None)

        assert removed == 2

    asyncio.run(scenario())


def test_cleanup_all_sessions_disconnects_every_cached_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeClient] = []

    def factory(options: ClaudeAgentOptions) -> FakeClient:
        client = FakeClient(options)
        created.append(client)
        return client

    monkeypatch.setattr(copilot, "_session_factory", factory)

    async def scenario() -> None:
        await copilot.get_or_create_session("skill-a", "claude", "a-key", tmp_path)
        await copilot.get_or_create_session("skill-b", "deepseek", "d-key", tmp_path)
        await copilot.cleanup_all_sessions()

        assert [client.disconnect_calls for client in created] == [1, 1]

    asyncio.run(scenario())


def test_get_or_create_session_is_safe_for_same_key_concurrency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeClient] = []

    def factory(options: ClaudeAgentOptions) -> FakeClient:
        client = FakeClient(options)
        created.append(client)
        return client

    monkeypatch.setattr(copilot, "_session_factory", factory)

    async def scenario() -> None:
        first, second = await asyncio.gather(
            copilot.get_or_create_session("skill-a", "claude", "same-key", tmp_path),
            copilot.get_or_create_session("skill-a", "claude", "same-key", tmp_path),
        )

        assert first is second

    asyncio.run(scenario())
    assert len(created) == 1


def test_build_options_uses_claude_default_endpoint(tmp_path: Path) -> None:
    options = copilot.build_options("claude", "claude-key", tmp_path)

    assert Path(options.cwd) == tmp_path
    assert options.env == {"ANTHROPIC_API_KEY": "claude-key"}
    assert options.allowed_tools == ["Read", "Write", "Edit", "Bash"]
    assert options.permission_mode == "acceptEdits"


def test_build_options_sets_deepseek_anthropic_endpoint(tmp_path: Path) -> None:
    options = copilot.build_options("deepseek", "deepseek-key", tmp_path)

    assert Path(options.cwd) == tmp_path
    assert options.env["ANTHROPIC_API_KEY"] == "deepseek-key"
    assert options.env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert options.allowed_tools == ["Read", "Write", "Edit", "Bash"]
    assert options.permission_mode == "acceptEdits"
