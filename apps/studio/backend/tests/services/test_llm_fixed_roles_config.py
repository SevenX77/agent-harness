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
