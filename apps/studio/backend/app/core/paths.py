"""Path helpers for Studio backend resource resolution."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

APP_DIR_NAME = "AgentStudio"


def resource_dir_from_env(environ: Mapping[str, str], fallback: Path) -> Path:
    raw = environ.get("STUDIO_RESOURCE_DIR")
    return Path(raw).resolve() if raw else fallback


def app_settings_dir(
    environ: Mapping[str, str],
    *,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    config_dir = environ.get("STUDIO_CONFIG_DIR")
    if config_dir:
        return Path(config_dir).resolve()

    raw = environ.get("STUDIO_RESOURCE_DIR")
    if raw:
        return default_config_dir(Path(raw).resolve())

    system = platform or sys.platform
    raw_home = home or Path.home()
    user_home = raw_home if platform is not None else raw_home.resolve()
    if system == "darwin":
        return user_home / "Library" / "Application Support" / APP_DIR_NAME
    if system == "win32":
        appdata = environ.get("APPDATA")
        base = Path(appdata) if appdata else user_home / "AppData" / "Roaming"
        return base / APP_DIR_NAME
    return user_home / ".local" / "share" / APP_DIR_NAME


def skill_index_path(settings_dir: Path) -> Path:
    return settings_dir / "skill_index.json"


def app_settings_path(settings_dir: Path) -> Path:
    return settings_dir / "app_settings.json"


def default_skills_root(settings_dir: Path) -> Path:
    return settings_dir / "Skills"


def default_config_dir(resource_dir: Path) -> Path:
    return resource_dir / "config"


def default_workspaces_dir(resource_dir: Path) -> Path:
    return resource_dir / "workspaces"
