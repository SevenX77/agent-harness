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


def test_set_and_get_view_context() -> None:
    async def scenario() -> None:
        accepted = await copilot.set_view_context(
            "skill-a",
            "Edit",
            {"skill_md_text": "hello"},
            100,
        )

        assert accepted is True

    asyncio.run(scenario())

    cached = copilot.get_view_context("skill-a")
    assert cached is not None
    assert cached.view == "Edit"
    assert cached.context == {"skill_md_text": "hello"}
    assert cached.timestamp_ms == 100


def test_set_view_context_rejects_out_of_order_timestamp() -> None:
    async def scenario() -> None:
        assert await copilot.set_view_context("skill-a", "Edit", {"value": "new"}, 100) is True
        assert await copilot.set_view_context("skill-a", "Run", {"value": "old"}, 50) is False

    asyncio.run(scenario())

    cached = copilot.get_view_context("skill-a")
    assert cached is not None
    assert cached.view == "Edit"
    assert cached.context == {"value": "new"}
    assert cached.timestamp_ms == 100


def test_set_view_context_rejects_equal_timestamp() -> None:
    async def scenario() -> None:
        assert await copilot.set_view_context("skill-a", "Edit", {"value": "first"}, 100) is True
        assert await copilot.set_view_context("skill-a", "Run", {"value": "second"}, 100) is False

    asyncio.run(scenario())

    cached = copilot.get_view_context("skill-a")
    assert cached is not None
    assert cached.view == "Edit"
    assert cached.context == {"value": "first"}


def test_truncate_for_reference_without_frontmatter() -> None:
    content = "a" * 6144

    truncated = copilot.truncate_for_reference(content, "/tmp/SKILL.md")

    assert truncated.startswith("a" * 300)
    assert "a" * 301 not in truncated
    assert "[Content truncated due to length. Use 'Read' tool" in truncated
    assert "/tmp/SKILL.md" in truncated


def test_truncate_for_reference_preserves_yaml_frontmatter() -> None:
    frontmatter = "---\nname: x\nversion: 1\n---\n"
    body = "b" * 6144

    truncated = copilot.truncate_for_reference(frontmatter + body, "/tmp/SKILL.md")

    assert truncated.startswith(frontmatter + ("b" * 300))
    assert "b" * 301 not in truncated
    assert truncated.endswith("]")
    assert "/tmp/SKILL.md" in truncated


def test_truncate_for_reference_trims_oversized_frontmatter_to_budget() -> None:
    content = "---\n" + ("f" * 6144) + "\n---\nbody"

    truncated = copilot.truncate_for_reference(content, "/tmp/SKILL.md")

    assert len(truncated.encode("utf-8")) <= copilot.MAX_REFERENCE_BYTES
    assert truncated.startswith("---\n")
    assert "[Content truncated due to length. Use 'Read' tool" in truncated
    assert "body" not in truncated


def test_truncate_for_reference_uses_first_frontmatter_pair() -> None:
    content = "---\n---\n---\n" + ("c" * 6144)

    truncated = copilot.truncate_for_reference(content, "/tmp/multi.md")

    assert truncated.startswith("---\n---\n---\n" + ("c" * 296))
    assert "c" * 297 not in truncated
    assert "/tmp/multi.md" in truncated
