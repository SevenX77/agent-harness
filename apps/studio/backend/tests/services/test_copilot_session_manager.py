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
    assert options.allowed_tools == ["Read", "Write", "Edit", "Bash"]
    assert options.permission_mode == "acceptEdits"


def test_build_options_sets_provider_base_url(tmp_path: Path) -> None:
    options = copilot.build_options("https://provider.example/anthropic", "provider-key", tmp_path)

    assert Path(options.cwd) == tmp_path
    assert options.env["ANTHROPIC_API_KEY"] == "provider-key"
    assert options.env["ANTHROPIC_BASE_URL"] == "https://provider.example/anthropic"
    assert options.allowed_tools == ["Read", "Write", "Edit", "Bash"]
    assert options.permission_mode == "acceptEdits"


def test_build_options_enables_full_thinking(tmp_path: Path) -> None:
    # F1: thinking must be enabled and shown in full (never summarized/omitted),
    # otherwise the SDK emits no ThinkingBlock and the streamed Thought is empty.
    options = copilot.build_options(None, "claude-key", tmp_path)

    assert options.thinking == {"type": "adaptive"}


def test_build_options_mounts_skill_spec(tmp_path: Path) -> None:
    # F3: the authoritative graph_skill spec is mounted so the copilot can Read it.
    # The spec dir exists in this repo, so add_dirs must include it.
    options = copilot.build_options(None, "claude-key", tmp_path)

    assert any("02-skill-syntax" in entry for entry in options.add_dirs), options.add_dirs


def test_build_system_prompt_has_skill_authoring_brain() -> None:
    # F3: the prompt must teach the v0.3.0 graph_skill format (not the old 3-line
    # generic prompt) and point to the mounted spec.
    prompt = copilot.build_system_prompt("nonexistent-skill")

    assert "graph_skill" in prompt
    assert "v0.3.0" in prompt
    assert "phases" in prompt
    assert "skill-spec" in prompt  # mounted-spec pointer
