"""FastAPI application entrypoint for Skill Studio backend."""

from __future__ import annotations

from fastapi import FastAPI

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


def create_app() -> FastAPI:
    """Create the Studio FastAPI application."""
    studio_app = FastAPI(
        title="Skill Studio Backend",
        version="0.1.0",
        description="Phase 0 API scaffold for graph-agent-harness Skill Studio.",
    )
    configure_cors(studio_app)
    register_exception_handlers(studio_app)

    studio_app.include_router(skills.router)
    studio_app.include_router(lint.router)
    studio_app.include_router(runs.router)
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
