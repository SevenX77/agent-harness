"""Bootstrap script that overrides backend config from env then runs uvicorn.

Used by the e2e conftest to launch a fully-isolated Studio backend pointed at
temp `skills/` and `workspaces/` directories. Avoids touching backend code.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for path in (REPO_ROOT / "apps/studio/backend", REPO_ROOT / "packages/graph-agent/src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core import config  # noqa: E402

env_skills = os.environ.get("STUDIO_TEST_SKILLS_DIR")
env_workspaces = os.environ.get("STUDIO_TEST_WORKSPACES_DIR")
env_port = os.environ.get("STUDIO_TEST_PORT")

if env_skills:
    config.SKILLS_DIR = Path(env_skills)
if env_workspaces:
    config.WORKSPACES_DIR = Path(env_workspaces)
if env_port:
    config.STUDIO_PORT = int(env_port)

logging.basicConfig(
    level=logging.INFO,
    format="[backend-runner] %(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("e2e.backend_runner")
logger.info(
    "starting backend skills_dir=%s workspaces_dir=%s port=%s",
    config.SKILLS_DIR,
    config.WORKSPACES_DIR,
    config.STUDIO_PORT,
)

import uvicorn  # noqa: E402
from app.main import app  # noqa: E402
from app.services.terminal_manager import terminal_manager  # noqa: E402

# E2E tests must not depend on the real Claude CLI being installed or
# interactive — bash is the deterministic alternative explicitly allowed by
# the backend's _ALLOWED_COMMANDS allowlist.
if os.environ.get("STUDIO_TEST_TERMINAL_BASH", "1") == "1":
    terminal_manager.command = ["bash", "--noprofile", "--norc"]
    logger.info("e2e override: terminal_manager.command set to bash")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=config.STUDIO_PORT, log_level="warning")
