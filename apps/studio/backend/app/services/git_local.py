"""Local Git initialization helpers for Studio skill projects."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from app.core import config

logger = logging.getLogger(__name__)

STUDIO_GITIGNORE = "\n".join(
    [
        "/.workspace/*",
        "!/.workspace/golden/",
        "!/.workspace/predict/",
        "/.workspace/local_settings.json",
        "",
    ]
)
FALLBACK_USER_ID = "studio-user"


def initialize_skill_repository(skill_dir: Path, *, user_id: str | None = None) -> None:
    """Initialize local L1 Git state without touching global Git config."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    write_studio_gitignore(skill_dir)
    _run_git(skill_dir, "init")
    resolved_user_id = user_id or _read_user_id_from_app_settings() or FALLBACK_USER_ID
    if resolved_user_id == FALLBACK_USER_ID:
        logger.warning("user_id missing, using fallback")
    _run_git(skill_dir, "config", "--local", "user.name", resolved_user_id)
    _run_git(skill_dir, "config", "--local", "user.email", f"{resolved_user_id}@studio.local")


def write_studio_gitignore(skill_dir: Path) -> Path:
    """Write the Studio P0 .gitignore template for a skill repository."""
    gitignore_path = skill_dir / ".gitignore"
    gitignore_path.write_text(STUDIO_GITIGNORE, encoding="utf-8")
    return gitignore_path


def _read_user_id_from_app_settings() -> str | None:
    settings_path = config.APP_SETTINGS_PATH
    if not settings_path.exists():
        return None
    try:
        payload: Any = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("user_id", "User ID", "userId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _run_git(skill_dir: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=skill_dir,
        check=True,
        capture_output=True,
        text=True,
    )
