"""Tests for prompt_quality validator."""
from __future__ import annotations

from types import SimpleNamespace

from graph_agent.core.validators.prompt_quality import (
    _check_finish_task_visibility,
    _check_prompt_duplication,
    _check_setup_anti_pattern,
)


def _phase(name: str = "review") -> SimpleNamespace:
    return SimpleNamespace(name=name)


def test_prompt_duplication_emits_for_v0_style_rewrite() -> None:
    duplicated = (
        "请严格按以下四步执行：第一步通读章节并识别所有背景规则；"
        "第二步判断每个片段属于A类设定、B类剧情还是C类系统交互；"
        "第三步合并连续同类片段并保持时间线顺序；"
        "第四步输出完整分段结果并说明关键边界依据。"
        "必须逐条复核每一段的起止行、类型、内容摘要和置信度，"
        "并保证最终输出覆盖原文全部行号且没有重叠。"
    )

    issues = _check_prompt_duplication(
        f"你是小说分段专家。\n{duplicated}\n不要遗漏边界。",
        f"输入如下。\n{duplicated}\n请开始执行。",
        _phase("segment"),
        0,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "W-PROMPT-DUPLICATION"
    assert issues[0].severity == "WARNING"
    assert issues[0].location == "SKILL.md:phases.segment.user_prompt_template"


def test_prompt_duplication_skips_v2_style_reference_only_prompt() -> None:
    issues = _check_prompt_duplication(
        "你是小说分段专家。按系统提示中的A/B/C规则完成分段。",
        "章节内容如下：{chapter_content}\n如需规则细节，请查阅 references/guide.md。",
        _phase("segment"),
        0,
    )

    assert issues == []


def test_prompt_duplication_emits_for_repeated_rule_blocks() -> None:
    sys_prompt = (
        "你是分段专家。A类、B类、C类必须按设定和事件区分。"
        "同一时空连续动作合并，并输出分段列表。"
    )
    user_prompt = (
        "请检查章节。\n"
        "## 参考资料：A/B/C 细则\n"
        "- A类：解释设定。\n"
        "- B类：描述事件。\n"
        "- C类：系统空间。\n"
        "- 同一时空连续动作合并。\n"
        "- 最终输出完整分段列表。\n"
        + "补充说明。" * 90
    )

    issues = _check_prompt_duplication(sys_prompt, user_prompt, _phase("segment"), 0)

    assert len(issues) == 1
    assert issues[0].rule_id == "W-PROMPT-DUPLICATION"


def test_finish_task_visibility_emits_when_buried_at_step_six() -> None:
    prompt = "\n".join([
        "你是复核节点。请先完成全部质量检查。" + "背景要求。" * 40,
        "1. 通读原章节。",
        "2. 对照 Pass 1 分段。",
        "3. 检查 C 类边界。",
        "4. 检查 A/B 类混合。",
        "5. 修正所有关键错误。",
        "6. 调用 finish_task 提交最终结果。",
    ])

    issues = _check_finish_task_visibility(prompt, _phase("review"), 0)

    assert len(issues) == 1
    assert issues[0].rule_id == "W-FINISH-TASK-VISIBILITY"
    assert issues[0].severity == "WARNING"
    assert issues[0].location == "SKILL.md:phases.review.prompt"


def test_finish_task_visibility_skips_short_step_list() -> None:
    prompt = "\n".join([
        "你是复核节点。" + "背景要求。" * 40,
        "1. 通读输入。",
        "2. 检查关键边界。",
        "3. 调用 finish_task 提交最终结果。",
    ])

    issues = _check_finish_task_visibility(prompt, _phase("review"), 0)

    assert issues == []


def test_setup_anti_pattern_emits_for_first_logic_setup_phase() -> None:
    manifest = SimpleNamespace(phases=[
        SimpleNamespace(name="setup", mode="logic"),
        SimpleNamespace(name="segment", mode="llm"),
    ])

    issues = _check_setup_anti_pattern(manifest)

    assert len(issues) == 1
    assert issues[0].rule_id == "W-SETUP-PHASE-ANTI-PATTERN"
    assert issues[0].severity == "WARNING"
    assert issues[0].location == "SKILL.md:phases[0]"


def test_setup_anti_pattern_skips_setup_llm_phase() -> None:
    manifest = SimpleNamespace(phases=[SimpleNamespace(name="setup", mode="llm")])

    issues = _check_setup_anti_pattern(manifest)

    assert issues == []


def test_setup_anti_pattern_skips_non_setup_logic_phase() -> None:
    manifest = SimpleNamespace(phases=[SimpleNamespace(name="segment", mode="logic")])

    issues = _check_setup_anti_pattern(manifest)

    assert issues == []
