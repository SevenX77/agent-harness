"""Path helpers for Studio backend resource resolution."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def resource_dir_from_env(environ: Mapping[str, str], fallback: Path) -> Path:
    raw = environ.get("STUDIO_RESOURCE_DIR")
    return Path(raw).resolve() if raw else fallback.resolve()


def default_skills_dir(resource_dir: Path) -> Path:
    return resource_dir / "skills"


def default_config_dir(resource_dir: Path) -> Path:
    return resource_dir / "config"


def default_workspaces_dir(resource_dir: Path) -> Path:
    return resource_dir / "workspaces"
