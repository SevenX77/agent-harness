from app.services.llm_fixed_roles import (
    fixed_role_names,
    recommended_models_for_role,
    studio_fixed_role_config,
)


def test_studio_fixed_roles_are_loaded_from_runtime_config() -> None:
    config = studio_fixed_role_config()

    assert "copilot_deepseek_v4_flash" in config.roles
    assert config.roles["copilot_deepseek_v4_flash"].role_kind == "copilot"
    assert recommended_models_for_role("copilot_deepseek_v4_flash") == ("deepseek-v4-flash",)
    assert "copilot_deepseek_v4_flash" in fixed_role_names()


def test_builtin_copilot_claude_role_is_opus_5() -> None:
    # 用户裁决 2026-08-27:内置 copilot Claude 角色 = Opus 5(取代 Opus 4.8,
    # 不留旧角色——no-backward-compat,旧盘面数据按「重新生成」处理)。
    config = studio_fixed_role_config()

    assert "copilot_claude_opus_5" in config.roles
    assert config.roles["copilot_claude_opus_5"].role_kind == "copilot"
    assert recommended_models_for_role("copilot_claude_opus_5") == ("claude-opus-5",)
    assert "copilot_claude_opus_5" in fixed_role_names()
    assert "copilot_claude_opus_4_8" not in config.roles
    assert "copilot_claude_opus_4_8" not in fixed_role_names()
