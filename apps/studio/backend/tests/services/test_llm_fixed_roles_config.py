from app.services.llm_fixed_roles import (
    fixed_role_names,
    recommended_models_for_role,
    studio_fixed_role_config,
)


def test_studio_fixed_roles_are_loaded_from_runtime_config() -> None:
    config = studio_fixed_role_config()

    assert "copilot_deepseek_v4_pro" in config.roles
    assert config.roles["copilot_deepseek_v4_pro"].role_kind == "copilot"
    assert recommended_models_for_role("copilot_deepseek_v4_pro") == ("deepseek-v4-pro",)
    assert "copilot_deepseek_v4_pro" in fixed_role_names()
