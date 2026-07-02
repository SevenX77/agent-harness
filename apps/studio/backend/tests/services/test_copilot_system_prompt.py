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


def test_rules_document_is_skill_authoring_brain() -> None:
    # 恒定规则层独立成文档(app/prompts/copilot-rules.md),仍是 F3 的 skill-authoring
    # 心智模型 + R4 语言硬规则,不因抽离丢内容。
    rules = copilot.load_copilot_rules()
    assert "graph_skill" in rules
    assert "v0.3.0" in rules
    assert "phases" in rules
    assert "聚焦 Studio 上下文" in rules
    assert "不拒答" in rules
    assert "语言跟随用户" in rules


def test_rules_document_covers_tools_and_context_contract() -> None:
    # 新增章节:工具边界(四工具白名单/workspace 圈定/Bash 审批语义)与上下文契约
    # (<copilot_context> 各层语义),让模型不再靠猜。
    rules = copilot.load_copilot_rules()
    assert "工具与边界" in rules
    assert "Read / Write / Edit / Bash" in rules
    assert "workspace" in rules
    assert "不要重发同一命令" in rules
    assert "<copilot_context>" in rules
    assert "<mentions>" in rules
    assert "只读" in rules


def test_rules_hash_is_stable_short_hex() -> None:
    digest = copilot.copilot_rules_hash()
    assert len(digest) == 8
    int(digest, 16)  # valid hex
    assert digest == copilot.copilot_rules_hash()


def test_session_system_prompt_has_rules_and_spec_but_never_view_context() -> None:
    # 会话级 system prompt = 规则 + 挂载 spec 指针;运行时 view context 绝不进来
    # (它每轮都变,属于 turn prompt)。
    asyncio.run(copilot.set_view_context("skill-a", "Edit", {"dirty": True}, 100))

    prompt = copilot.build_session_system_prompt()

    assert prompt.startswith(copilot.load_copilot_rules())
    assert "已挂载 skill-spec" in prompt
    assert "## 当前上下文" not in prompt
    # 规则文档的「上下文契约」章节会提到 <copilot_context> 标签名,所以这里断言的是
    # 渲染出来的具体上下文内容不在场,而不是标签字样。
    assert '<skill>{"id": "skill-a"' not in prompt


def test_turn_prompt_injects_small_view_context() -> None:
    asyncio.run(
        copilot.set_view_context("skill-a", "Edit", {"skill_md_text": "hello", "dirty": True}, 100)
    )

    prompt = copilot._prompt_with_turn_context("skill-a", "why?")

    # F4: context renders as structured XML before the user message; the rules
    # document itself must NOT be re-sent per turn.
    assert "## 当前上下文" in prompt
    assert '<skill>{"id": "skill-a", "view": "Edit"}</skill>' in prompt
    assert '"skill_md_text": "hello"' in prompt
    assert '"dirty": true' in prompt
    assert prompt.rstrip().endswith("## 用户消息\nwhy?")
    assert "graph_skill 格式心智模型" not in prompt


def test_turn_prompt_truncates_large_file_context() -> None:
    asyncio.run(
        copilot.set_view_context(
            "skill-a",
            "Edit",
            {"file_path": "/tmp/SKILL.md", "skill_md_text": "x" * 6144, "dirty": False},
            100,
        )
    )

    prompt = copilot._prompt_with_turn_context("skill-a", "check")

    assert "<copilot_context>" in prompt
    assert "x" * 300 in prompt
    assert "x" * 301 not in prompt
    assert "[Content truncated due to length. Use 'Read' tool" in prompt
    assert "/tmp/SKILL.md" in prompt
    assert '"dirty": false' in prompt


def test_turn_prompt_without_context_is_plain_user_message() -> None:
    assert copilot._prompt_with_turn_context("no-context-skill", "hello") == "hello"


def test_context_resolved_event_echoes_rules_hash() -> None:
    event = copilot._context_resolved_event("skill-a")
    assert f"rules@{copilot.copilot_rules_hash()}" in event.summary
