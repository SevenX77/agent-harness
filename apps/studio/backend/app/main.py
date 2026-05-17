"""FastAPI application entrypoint for Skill Studio backend."""

from __future__ import annotations

import argparse
import asyncio
import hmac
import logging
import os
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.backends import clear_backend_caches
from app.core.config import DEFAULT_STUDIO_PORT
from app.core.exceptions import register_exception_handlers
from app.core.middleware import configure_cors
from app.routers import (
    audit,
    compare,
    copilot,
    debug,
    golden,
    llm,
    lint,
    runs,
    settings,
    skills,
    system,
    templates,
    terminal,
    test_inputs,
    websockets,
)
from app.services.copilot import cleanup_all_sessions
from app.services.event_bus import file_watcher
from app.services.run_manager import run_manager
from app.services.skills import ensure_workspace_layout
from app.services.terminal_manager import terminal_manager

logger = logging.getLogger(__name__)
_VALID_TOKENS: list[str] = []


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start and stop Studio background services."""
    start_orphan_parent_monitor()
    clear_backend_caches()
    ensure_workspace_layout()
    terminal_manager.start_reaper()
    file_watcher.start(asyncio.get_running_loop())
    try:
        yield
    finally:
        file_watcher.stop()
        await cleanup_all_sessions()
        await terminal_manager.shutdown()
        await run_manager.shutdown()


def configure_api_auth(studio_app: FastAPI) -> None:
    api_token = os.environ.get("STUDIO_API_TOKEN", "").strip() or None
    dev_tunnel_token = os.environ.get("STUDIO_DEV_TUNNEL_TOKEN", "").strip() or None
    valid_tokens = [token for token in (api_token, dev_tunnel_token) if token]
    if not valid_tokens:
        raise RuntimeError(
            "Refusing to start: STUDIO_API_TOKEN or STUDIO_DEV_TUNNEL_TOKEN must be set"
        )

    # Production Tauri uses STUDIO_API_TOKEN. Dev tunnel uses STUDIO_DEV_TUNNEL_TOKEN.
    # There is no dev bypass mode.
    global _VALID_TOKENS
    _VALID_TOKENS = valid_tokens

    @studio_app.middleware("http")
    async def auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path in ("/health", "/api/health"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error_code": "UNAUTHORIZED", "message": "Missing Bearer token"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        token = auth_header[7:]
        if not _is_valid_token(token):
            return JSONResponse(
                {"error_code": "INVALID_TOKEN", "message": "Invalid Bearer token"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        return await call_next(request)


def _constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _is_valid_token(token: str | None) -> bool:
    if not token:
        return False
    return any(_constant_time_compare(token, valid_token) for valid_token in _VALID_TOKENS)


def create_app() -> FastAPI:
    """Create the Studio FastAPI application."""
    studio_app = FastAPI(
        title="Skill Studio Backend",
        version="0.1.0",
        description="FastAPI backend for graph-agent-harness Skill Studio.",
        lifespan=lifespan,
    )
    configure_api_auth(studio_app)
    configure_cors(studio_app)
    register_exception_handlers(studio_app)

    studio_app.include_router(skills.router)
    studio_app.include_router(templates.router)
    studio_app.include_router(lint.router)
    studio_app.include_router(runs.router)
    studio_app.include_router(runs.batch_router)
    studio_app.include_router(settings.router)
    studio_app.include_router(terminal.router)
    studio_app.include_router(test_inputs.router)
    studio_app.include_router(golden.router)
    studio_app.include_router(compare.router)
    studio_app.include_router(copilot.router)
    studio_app.include_router(llm.router)
    studio_app.include_router(audit.router)
    studio_app.include_router(debug.router)
    studio_app.include_router(websockets.router)
    studio_app.include_router(system.router)
    return studio_app


app = create_app()


def start_orphan_parent_monitor() -> None:
    if os.environ.get("STUDIO_EXIT_ON_ORPHAN") != "1":
        return

    def monitor() -> None:
        while True:
            if os.getppid() == 1:
                os._exit(1)
            time.sleep(2)

    thread = threading.Thread(target=monitor, name="studio-parent-monitor", daemon=True)
    thread.start()


def parse_main_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Skill Studio FastAPI sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_STUDIO_PORT)
    return parser.parse_args(argv)


def run_sidecar(host: str, port: int) -> None:
    import uvicorn

    server_config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(server_config)
    app.state.uvicorn_server = server
    server.run()


if __name__ == "__main__":
    args = parse_main_args()
    run_sidecar(args.host, args.port)
