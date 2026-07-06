from __future__ import annotations

from app.services import copilot


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
    rules = copilot.load_copilot_rules()
    assert "工具与边界" in rules
    assert "Read / Glob / Grep" in rules
    assert "Write / Edit" in rules
    assert "workspace" in rules
    assert "不要原样重发" in rules
    assert "不会把当前 UI selection" in rules
    assert "@" in rules
    assert "只读" in rules
    assert "mcp__studio__" in rules
    assert "get_llm_roles" in rules
    assert "compile_skill" in rules


def test_rules_hash_is_stable_short_hex() -> None:
    digest = copilot.copilot_rules_hash()
    assert len(digest) == 8
    int(digest, 16)  # valid hex
    assert digest == copilot.copilot_rules_hash()


def test_session_system_prompt_has_rules_and_spec_but_no_request_context() -> None:
    prompt = copilot.build_session_system_prompt()

    assert prompt.startswith(copilot.load_copilot_rules())
    # 渐进暴露:system prompt 只带挂载目录的一行式路由表,重内容靠 Read。
    assert "已挂载参考目录" in prompt
    assert "02-skill-syntax" in prompt
    assert "graph-agent-gateway" in prompt
    assert "Studio 配置文件地图" in prompt
    assert "## 当前上下文" not in prompt
    assert "## Copilot Judge Context" not in prompt


def test_turn_prompt_injects_only_explicit_judge_context() -> None:
    prompt = copilot._prompt_with_turn_context(
        "skill-a",
        "why?",
        judge_context={
            "compare_result_ref": "skills/s/golden/g1/compare/r1/compare_result.json",
            "judge_context_ref": "skills/s/runs/r1/copilot_judge/g1/judge_context.json",
            "baseline_ref": "skills/s/golden/g1/baseline.json",
            "diff_summary": {"total_score": 88},
        },
    )

    assert "## 当前上下文" not in prompt
    assert "## Copilot Judge Context" in prompt
    assert "<judge_context>" in prompt
    assert "compare_result_ref" in prompt
    assert "total_score" in prompt
    assert prompt.rstrip().endswith("## 用户消息\nwhy?")
    assert "graph_skill 格式心智模型" not in prompt


def test_turn_prompt_without_context_is_plain_user_message() -> None:
    assert copilot._prompt_with_turn_context("no-context-skill", "hello") == "hello"


def test_context_resolved_event_echoes_rules_hash() -> None:
    event = copilot._context_resolved_event("skill-a")
    assert f"rules@{copilot.copilot_rules_hash()}" in event.summary
    assert event.detail == "(no request context)"
