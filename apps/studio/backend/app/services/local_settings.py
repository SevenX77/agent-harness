"""Project-local Studio settings stored under a skill .workspace directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.skills import local_settings_path_for, workspace_dir_for


def read_local_settings(skill_dir: Path) -> dict[str, Any]:
    """Read .workspace/local_settings.json, returning an empty object when absent."""
    settings_path = local_settings_path_for(skill_dir)
    if not settings_path.exists():
        return {}
    loaded = json.loads(settings_path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def write_local_settings(skill_dir: Path, settings: dict[str, Any]) -> Path:
    """Persist local UI settings inside .workspace."""
    workspace_dir_for(skill_dir).mkdir(parents=True, exist_ok=True)
    settings_path = local_settings_path_for(skill_dir)
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return settings_path
