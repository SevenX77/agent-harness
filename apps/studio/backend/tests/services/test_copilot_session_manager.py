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


async def get_session(
    skill_id: str,
    model_code: str,
    api_key: str,
    workspace_dir: Path,
    provider_code: str = "OC_CL_ANT",
    base_url: str | None = None,
) -> FakeClient:
    return await copilot.get_or_create_session(
        skill_id=skill_id,
        model_code=model_code,
        provider_code=provider_code,
        base_url=base_url,
        api_key=api_key,
        workspace_dir=workspace_dir,
    )


@pytest.fixture(autouse=True)
def clean_sessions() -> Iterator[None]:
    asyncio.run(copilot.cleanup_all_sessions())
    yield
    asyncio.run(copilot.cleanup_all_sessions())


def test_get_or_create_session_reuses_same_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[FakeClient] = []

    def factory(options: ClaudeAgentOptions) -> FakeClient:
        client = FakeClient(options)
        created.append(client)
        return client

    monkeypatch.setattr(copilot, "_session_factory", factory)

    async def scenario() -> None:
        first = await get_session("skill-a", "CL46T", "same-key", tmp_path)
        second = await get_session("skill-a", "CL46T", "same-key", tmp_path)

        assert first is second

    asyncio.run(scenario())
    assert len(created) == 1


def test_get_or_create_session_keeps_imported_workspace_cwds_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[FakeClient] = []
    workspace_a = tmp_path / "imported-a"
    workspace_b = tmp_path / "imported-b"
    workspace_a.mkdir()
    workspace_b.mkdir()

    def factory(options: ClaudeAgentOptions) -> FakeClient:
        client = FakeClient(options)
        created.append(client)
        return client

    monkeypatch.setattr(copilot, "_session_factory", factory)

    async def scenario() -> None:
        first = await get_session("skill-a", "CL46T", "same-key", workspace_a)
        second = await get_session("skill-a", "CL46T", "same-key", workspace_b)

        assert first is not second
        assert Path(first.options.cwd) == workspace_a
        assert Path(second.options.cwd) == workspace_b

    asyncio.run(scenario())
    assert len(created) == 2


def test_reset_session_can_delete_skill_backend_pairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[FakeClient] = []

    def factory(options: ClaudeAgentOptions) -> FakeClient:
        client = FakeClient(options)
        created.append(client)
        return client

    monkeypatch.setattr(copilot, "_session_factory", factory)

    async def scenario() -> None:
        await get_session("skill-a", "CL46T", "old-key", tmp_path)
        await get_session("skill-a", "CL46T", "new-key", tmp_path)
        await get_session("skill-a", "DS32R", "deepseek-key", tmp_path, "OC_DS")
        await get_session("skill-b", "CL46T", "other-key", tmp_path)

        removed = await copilot.reset_session("skill-a", "CL46T")

        assert removed == 2
        assert sum(client.disconnect_calls for client in created) == 2

    asyncio.run(scenario())


def test_reset_session_can_delete_all_backend_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(copilot, "_session_factory", FakeClient)

    async def scenario() -> None:
        await get_session("skill-a", "CL46T", "a-key", tmp_path)
        await get_session("skill-b", "CL46T", "b-key", tmp_path)
        await get_session("skill-a", "DS32R", "d-key", tmp_path, "OC_DS")

        removed = await copilot.reset_session(None, "CL46T")

        assert removed == 2

    asyncio.run(scenario())


def test_reset_session_can_delete_all_skill_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(copilot, "_session_factory", FakeClient)

    async def scenario() -> None:
        await get_session("skill-a", "CL46T", "a-key", tmp_path)
        await get_session("skill-a", "DS32R", "d-key", tmp_path, "OC_DS")
        await get_session("skill-b", "CL46T", "b-key", tmp_path)

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
        await get_session("skill-a", "CL46T", "a-key", tmp_path)
        await get_session("skill-b", "DS32R", "d-key", tmp_path, "OC_DS")
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
            get_session("skill-a", "CL46T", "same-key", tmp_path),
            get_session("skill-a", "CL46T", "same-key", tmp_path),
        )

        assert first is second

    asyncio.run(scenario())
    assert len(created) == 1


def test_build_options_uses_default_endpoint_when_base_url_is_empty(tmp_path: Path) -> None:
    options = copilot.build_options(None, "claude-key", tmp_path)

    assert Path(options.cwd) == tmp_path
    assert options.env == {"ANTHROPIC_API_KEY": "claude-key"}
    assert options.allowed_tools == ["Read", "Glob", "Grep", "Write", "Edit", "Bash", "Skill"]
    assert options.permission_mode == "acceptEdits"


def test_build_options_sets_provider_base_url(tmp_path: Path) -> None:
    options = copilot.build_options("https://provider.example/anthropic", "provider-key", tmp_path)

    assert Path(options.cwd) == tmp_path
    assert options.env["ANTHROPIC_API_KEY"] == "provider-key"
    assert options.env["ANTHROPIC_BASE_URL"] == "https://provider.example/anthropic"
    assert options.allowed_tools == ["Read", "Glob", "Grep", "Write", "Edit", "Bash", "Skill"]
    assert options.permission_mode == "acceptEdits"


def test_build_options_sets_model_from_provider_model_id(tmp_path: Path) -> None:
    # R7-H: the route's provider_model_id must reach the CLI as the native
    # options.model, so the request carries the right model for EVERY route (not
    # just the special ark/deepseek env path). Without it the CLI uses its built-in
    # default (opus) and a non-opus endpoint (deepseek) stalls.
    options = copilot.build_options(None, "claude-key", tmp_path, model="deepseek-v3-0324")

    assert options.model == "deepseek-v3-0324"


def test_build_options_model_defaults_to_none(tmp_path: Path) -> None:
    # No explicit model → None → CLI default. Production always passes one
    # (get_or_create_session forwards route.provider_model_id).
    options = copilot.build_options(None, "claude-key", tmp_path)

    assert options.model is None


def test_build_options_enables_summarized_thinking(tmp_path: Path) -> None:
    # F1/F8: the CLI only offers summarized|omitted thinking display — there is
    # no "full", and leaving display unset strips the content (ThinkingBlocks
    # arrive EMPTY; probe-verified 2026-07-02, the R5 "thinking never shows"
    # root cause). "summarized" is the maximum exposure and also enables
    # thinking_delta stream events.
    options = copilot.build_options(None, "claude-key", tmp_path)

    assert options.thinking == {"type": "adaptive", "display": "summarized"}


def test_build_options_mounts_knowledge_base_only(tmp_path: Path) -> None:
    # 挂载收敛(R4.4/4.5):只剩随包知识库一条;契约事实经 KB-00 路由按需 Read。
    options = copilot.build_options(None, "claude-key", tmp_path)

    entries = [str(entry) for entry in options.add_dirs]
    assert len(entries) == 1, entries
    assert entries[0].endswith("knowledge"), entries


def test_build_options_carries_preset_system_prompt(tmp_path: Path) -> None:
    # 会话基座 = 完整 claude_code preset + MoirAI 资产 append(R6.1);
    # 纯字符串会把基座整体替换,是已定谳的缺陷用法。
    options = copilot.build_options(None, "claude-key", tmp_path)

    assert isinstance(options.system_prompt, dict)
    assert options.system_prompt["type"] == "preset"
    assert options.system_prompt["preset"] == "claude_code"
    assert "assembled-by=studio" in options.system_prompt["append"]


def test_build_options_isolates_filesystem_settings(tmp_path: Path) -> None:
    # setting_sources 缺省 = 加载全部文件系统配置(开发机 ~/.claude 渗入 copilot);
    # 必须显式 [] + strict_mcp_config 才是 SDK 隔离模式。
    options = copilot.build_options(None, "claude-key", tmp_path)

    assert options.setting_sources == []
    assert options.strict_mcp_config is True


def test_interrupt_active_query_interrupts_the_streaming_client() -> None:
    # R7-I stop button: interrupting a live turn calls the SDK-native
    # client.interrupt() on the skill's currently-streaming client.
    interrupted: list[bool] = []

    class FakeStreamingClient:
        async def interrupt(self) -> None:
            interrupted.append(True)

    copilot._active_clients["skill-stop"] = FakeStreamingClient()  # type: ignore[assignment]
    try:
        result = asyncio.run(copilot.interrupt_active_query("skill-stop"))
    finally:
        copilot._active_clients.pop("skill-stop", None)

    assert result is True
    assert interrupted == [True]


def test_interrupt_active_query_returns_false_when_no_turn_is_active() -> None:
    # No active stream for the skill → nothing to interrupt (idempotent, no error).
    assert asyncio.run(copilot.interrupt_active_query("skill-with-no-active-turn")) is False
