"""FastAPI application entrypoint for Skill Studio backend."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.backends import clear_backend_caches
from app.core.config import STUDIO_PORT
from app.core.exceptions import register_exception_handlers
from app.core.middleware import configure_cors
from app.routers import (
    audit,
    compare,
    copilot,
    debug,
    golden,
    lint,
    runs,
    skills,
    terminal,
    test_inputs,
    websockets,
)
from app.services.event_bus import file_watcher
from app.services.run_manager import run_manager
from app.services.skills import ensure_workspace_layout
from app.services.terminal_manager import terminal_manager


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start and stop Studio background services."""
    clear_backend_caches()
    ensure_workspace_layout()
    terminal_manager.start_reaper()
    file_watcher.start(asyncio.get_running_loop())
    try:
        yield
    finally:
        file_watcher.stop()
        await terminal_manager.shutdown()
        await run_manager.shutdown()


def create_app() -> FastAPI:
    """Create the Studio FastAPI application."""
    studio_app = FastAPI(
        title="Skill Studio Backend",
        version="0.1.0",
        description="FastAPI backend for graph-agent-harness Skill Studio.",
        lifespan=lifespan,
    )
    configure_cors(studio_app)
    register_exception_handlers(studio_app)

    studio_app.include_router(skills.router)
    studio_app.include_router(lint.router)
    studio_app.include_router(runs.router)
    studio_app.include_router(runs.batch_router)
    studio_app.include_router(terminal.router)
    studio_app.include_router(test_inputs.router)
    studio_app.include_router(golden.router)
    studio_app.include_router(compare.router)
    studio_app.include_router(copilot.router)
    studio_app.include_router(audit.router)
    studio_app.include_router(debug.router)
    studio_app.include_router(websockets.router)
    return studio_app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=STUDIO_PORT)
