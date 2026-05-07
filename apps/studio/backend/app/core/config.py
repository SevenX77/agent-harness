"""Runtime configuration for the Skill Studio backend."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

STUDIO_BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = STUDIO_BACKEND_DIR.parents[2]

DEFAULT_USER_ID = "default"
DEFAULT_STUDIO_PORT = 8787
TERMINAL_SESSION_TTL_SECONDS = 3600
TERMINAL_REAPER_INTERVAL_SECONDS = 60
MAX_CONCURRENT_TERMINALS = 3
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def resource_dir_from_env(environ: Mapping[str, str]) -> Path:
    raw = environ.get("STUDIO_RESOURCE_DIR")
    return Path(raw).resolve() if raw else REPO_ROOT


def default_skills_dir(resource_dir: Path) -> Path:
    return resource_dir / "skills"


def default_workspaces_dir(resource_dir: Path) -> Path:
    return resource_dir / "workspaces"


RESOURCE_DIR = resource_dir_from_env(os.environ)
SKILLS_DIR = default_skills_dir(RESOURCE_DIR)
WORKSPACES_DIR = default_workspaces_dir(RESOURCE_DIR)


def default_workspace_skills_dir() -> Path:
    """Return the current default user's writable skill directory."""
    return WORKSPACES_DIR / DEFAULT_USER_ID / "skills"
