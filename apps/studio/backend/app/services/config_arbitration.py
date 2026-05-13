"""Read-only configuration arbitration helpers for skill repositories."""

from __future__ import annotations

import logging
from pathlib import Path

from app.models.settings import AppSettings
from app.models.skills import ConfigMismatchWarning
from app.services.git_local import GitCommandError, GitLocalService

logger = logging.getLogger(__name__)


def detect_config_mismatch(
    skill_id: str,
    skill_dir: Path,
    app_settings: AppSettings,
    *,
    local_git: GitLocalService,
) -> ConfigMismatchWarning | None:
    """Return a warning when origin remote differs from app settings expectations."""
    if not app_settings.gitea_host or not app_settings.user_id:
        return None

    try:
        actual_url = local_git.remote_get_url(skill_dir, "origin").stdout.strip()
    except GitCommandError:
        logger.debug("origin remote missing for skill %s", skill_id)
        return None

    if not actual_url:
        return None

    expected_url = f"{app_settings.gitea_host.rstrip('/')}/{app_settings.user_id}/{skill_id}.git"
    if _normalize_remote_url(actual_url) == _normalize_remote_url(expected_url):
        return None

    return ConfigMismatchWarning(
        actual_remote_url=actual_url,
        expected_remote_url=expected_url,
    )


def _normalize_remote_url(url: str) -> str:
    return url.rstrip("/")
