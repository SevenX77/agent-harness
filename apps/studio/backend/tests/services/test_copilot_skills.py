"""场景技能机制:随包 SKILL.md 物化进 workspace/.claude/skills + skills 白名单。"""

from __future__ import annotations

from pathlib import Path

from app.services import copilot
from claude_agent_sdk import PermissionResultAllow


def test_shipped_scenario_skills_are_discovered() -> None:
    names = copilot.copilot_skill_names()
    assert names == [
        "agent-prompt-design",
        "compile-error-repair",
        "domain-analysis",
        "graph-design",
    ]


def test_skill_documents_have_frontmatter_name_matching_dir() -> None:
    for name in copilot.copilot_skill_names():
        text = (copilot._SKILLS_SRC_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---"), name
        assert f"name: {name}" in text, name
        assert "description:" in text, name


def test_materialize_copies_skills_into_workspace(tmp_path: Path) -> None:
    names = copilot._materialize_copilot_skills(tmp_path)

    assert names == copilot.copilot_skill_names()
    for name in names:
        target = tmp_path / ".claude" / "skills" / name / "SKILL.md"
        assert target.is_file(), name
    # 幂等:重复物化直接覆盖,不报错。
    assert copilot._materialize_copilot_skills(tmp_path) == names


def test_build_options_enables_skill_whitelist_for_chat_only(tmp_path: Path) -> None:
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    chat_options = copilot.build_options(None, "key", tmp_path, can_use_tool=cb)
    probe_options = copilot.build_options(None, "key", tmp_path)

    # chat 路:白名单启用随包技能(SDK 自动配 Skill 工具)。
    assert chat_options.skills == copilot.copilot_skill_names()
    # probe 路:确定性输出,技能全压。
    assert probe_options.skills == []
