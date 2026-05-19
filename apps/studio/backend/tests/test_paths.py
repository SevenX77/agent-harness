from __future__ import annotations

from pathlib import Path

from app.core import paths


def test_resource_dir_prefers_studio_resource_dir_env() -> None:
    resource_dir = paths.resource_dir_from_env(
        {"STUDIO_RESOURCE_DIR": "/tmp/studio-resources"},
        Path("/repo"),
    )

    assert resource_dir == Path("/tmp/studio-resources")
    assert paths.default_skills_dir(resource_dir) == Path("/tmp/studio-resources/skills")
    assert paths.default_config_dir(resource_dir) == Path("/tmp/studio-resources/config")
    assert paths.default_workspaces_dir(resource_dir) == Path("/tmp/studio-resources/workspaces")
    assert paths.app_settings_dir(
        {"STUDIO_RESOURCE_DIR": "/tmp/studio-resources"},
        home=Path("/home/user"),
    ) == Path("/tmp/studio-resources/config")


def test_resource_dir_uses_fallback_without_env() -> None:
    assert paths.resource_dir_from_env({}, Path("/repo")) == Path("/repo")


def test_app_settings_dir_uses_linux_default() -> None:
    settings_dir = paths.app_settings_dir({}, platform="linux", home=Path("/home/user"))

    assert settings_dir == Path("/home/user/.local/share/AgentStudio")
    assert paths.skill_index_path(settings_dir) == settings_dir / "skill_index.json"
    assert paths.default_skills_root(settings_dir) == settings_dir / "Skills"


def test_app_settings_dir_uses_macos_default() -> None:
    settings_dir = paths.app_settings_dir({}, platform="darwin", home=Path("/Users/user"))

    assert settings_dir == Path("/Users/user/Library/Application Support/AgentStudio")


def test_app_settings_dir_uses_windows_default() -> None:
    settings_dir = paths.app_settings_dir(
        {"APPDATA": "C:/Users/user/AppData/Roaming"},
        platform="win32",
        home=Path("C:/Users/user"),
    )

    assert settings_dir == Path("C:/Users/user/AppData/Roaming/AgentStudio")
