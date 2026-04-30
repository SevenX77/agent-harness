"""Runtime configuration for the Skill Studio backend."""

from __future__ import annotations

from pathlib import Path

STUDIO_BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = STUDIO_BACKEND_DIR.parent

SKILLS_DIR = REPO_ROOT / "skills"
WORKSPACES_DIR = REPO_ROOT / "workspaces"
DEFAULT_USER_ID = "default"
STUDIO_PORT = 8787
TERMINAL_SESSION_TTL_SECONDS = 3600
TERMINAL_REAPER_INTERVAL_SECONDS = 60
MAX_CONCURRENT_TERMINALS = 3
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def default_workspace_skills_dir() -> Path:
    """Return the current default user's writable skill directory."""
    return WORKSPACES_DIR / DEFAULT_USER_ID / "skills"
