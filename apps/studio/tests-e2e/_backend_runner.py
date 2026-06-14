"""Bootstrap script that overrides backend config from env then runs uvicorn.

Used by the e2e conftest to launch a fully-isolated Studio backend pointed at
temp `skills/` and `workspaces/` directories. Avoids touching backend code.

IMPORTANT: run_manager spawns run workers via multiprocessing "spawn", which
re-imports this module (the launcher's __main__) in every child. Only the cheap
path/config overrides may live at module scope; creating the FastAPI app and
launching uvicorn must stay under __main__ so spawned workers don't re-create
the app or relaunch the server (that previously aborted runs mid-flight, so
final_state.json never landed).
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

# Cheap config overrides — must also apply inside spawned run workers (they read
# these config globals), so they stay at module scope.
if os.environ.get("STUDIO_TEST_SKILLS_DIR"):
    config.SKILLS_DIR = Path(os.environ["STUDIO_TEST_SKILLS_DIR"])
if os.environ.get("STUDIO_TEST_WORKSPACES_DIR"):
    config.WORKSPACES_DIR = Path(os.environ["STUDIO_TEST_WORKSPACES_DIR"])
if os.environ.get("STUDIO_TEST_PORT"):
    config.STUDIO_PORT = int(os.environ["STUDIO_TEST_PORT"])


def main() -> None:
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

    import uvicorn
    from app.main import app
    from app.services.terminal_manager import terminal_manager

    # E2E tests must not depend on the real Claude CLI being installed or
    # interactive — bash is the deterministic alternative explicitly allowed by
    # the backend's _ALLOWED_COMMANDS allowlist.
    if os.environ.get("STUDIO_TEST_TERMINAL_BASH", "1") == "1":
        terminal_manager.command = ["bash", "--noprofile", "--norc"]
        logger.info("e2e override: terminal_manager.command set to bash")

    uvicorn.run(app, host="127.0.0.1", port=config.STUDIO_PORT, log_level="warning")


if __name__ == "__main__":
    main()
