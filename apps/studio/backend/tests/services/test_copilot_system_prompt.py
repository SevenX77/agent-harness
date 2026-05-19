from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from app.services import copilot


@pytest.fixture(autouse=True)
def clear_view_contexts() -> Iterator[None]:
    copilot._view_contexts.clear()
    yield
    copilot._view_contexts.clear()


def test_base_system_prompt_contains_ac11_phrases() -> None:
    assert "聚焦 Studio 上下文" in copilot.BASE_SYSTEM_PROMPT_TEMPLATE
    assert "允许任何通用问题" in copilot.BASE_SYSTEM_PROMPT_TEMPLATE
    assert "不要拒答" in copilot.BASE_SYSTEM_PROMPT_TEMPLATE


def test_build_system_prompt_without_view_context_returns_base_only() -> None:
    assert copilot.build_system_prompt("skill-a") == copilot.BASE_SYSTEM_PROMPT_TEMPLATE.strip()


def test_build_system_prompt_injects_small_view_context() -> None:
    async def scenario() -> None:
        await copilot.set_view_context(
            "skill-a",
            "Edit",
            {"skill_md_text": "hello", "dirty": True},
            100,
        )

    asyncio.run(scenario())

    prompt = copilot.build_system_prompt("skill-a")

    assert prompt.startswith(copilot.BASE_SYSTEM_PROMPT_TEMPLATE.strip())
    assert "\n\n## 当前 View: Edit\n" in prompt
    assert '"skill_md_text": "hello"' in prompt
    assert '"dirty": true' in prompt


def test_build_system_prompt_truncates_large_file_context() -> None:
    async def scenario() -> None:
        await copilot.set_view_context(
            "skill-a",
            "Edit",
            {
                "file_path": "/tmp/SKILL.md",
                "skill_md_text": "x" * 6144,
                "dirty": False,
            },
            100,
        )

    asyncio.run(scenario())

    prompt = copilot.build_system_prompt("skill-a")

    assert "\n\n## 当前 View: Edit\n" in prompt
    assert "x" * 300 in prompt
    assert "x" * 301 not in prompt
    assert "[Content truncated due to length. Use 'Read' tool" in prompt
    assert "/tmp/SKILL.md" in prompt
    assert '"dirty": false' in prompt
