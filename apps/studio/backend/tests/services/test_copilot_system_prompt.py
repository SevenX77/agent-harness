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


def test_base_system_prompt_is_skill_authoring_brain() -> None:
    # F3: the prompt teaches the v0.3.0 graph_skill format (replacing the old
    # 3-line generic prompt) while keeping "answer any reasonable question".
    template = copilot.BASE_SYSTEM_PROMPT_TEMPLATE
    assert "graph_skill" in template
    assert "v0.3.0" in template
    assert "phases" in template
    assert "聚焦 Studio 上下文" in template
    assert "不拒答" in template


def test_build_system_prompt_without_view_context_has_brain_and_mounted_spec() -> None:
    # F3: with no view context, the prompt is the brain + the mounted-spec pointer
    # (the spec dir exists in this repo), and no view section.
    prompt = copilot.build_system_prompt("skill-a")

    assert prompt.startswith(copilot.BASE_SYSTEM_PROMPT_TEMPLATE.strip())
    assert "已挂载 skill-spec" in prompt
    assert "## 当前 View" not in prompt


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
