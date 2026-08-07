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
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from app.core.backends import clear_backend_caches
from app.core.config import DEFAULT_STUDIO_PORT
from app.core.exceptions import register_exception_handlers
from app.core.middleware import configure_cors
from app.routers import (
    audit,
    compare,
    compare_candidates,
    copilot,
    debug,
    golden,
    io_scan,
    lint,
    llm,
    loopback,
    node_llm_params,
    runs,
    runtime_config,
    settings,
    skills,
    system,
    templates,
    test_inputs,
    websockets,
)
from app.services.cli_mcp_surface import build_cli_mcp_server
from app.services.community_catalog_runtime import sync_verified_community_catalog_into_credentials
from app.services.copilot import cleanup_all_sessions
from app.services.file_watcher import file_watcher
from app.services.run_manager import run_manager
from app.services.runtime_truth_init import ensure_runtime_truth_sources
from app.services.skills import ensure_workspace_layout

logger = logging.getLogger(__name__)
_VALID_TOKENS: list[str] = []


@asynccontextmanager
async def lifespan(studio_app: FastAPI) -> AsyncIterator[None]:
    """Start and stop Studio background services."""
    start_orphan_parent_monitor()
    clear_backend_caches()
    ensure_workspace_layout()
    ensure_runtime_truth_sources()
    await _sync_verified_community_catalog_on_startup()
    file_watcher.start(asyncio.get_running_loop())
    # CLI 表面 MCP 出口(N5):manager 一个实例只能 run 一次,所以每次 lifespan
    # 都新建(Server + manager),经 app.state 交给 /mcp 挂载点转发。
    cli_mcp_manager = StreamableHTTPSessionManager(app=build_cli_mcp_server())
    try:
        async with cli_mcp_manager.run():
            studio_app.state.cli_mcp_manager = cli_mcp_manager
            try:
                yield
            finally:
                studio_app.state.cli_mcp_manager = None
    finally:
        file_watcher.stop()
        await cleanup_all_sessions()
        await run_manager.shutdown()


async def _sync_verified_community_catalog_on_startup() -> None:
    try:
        await sync_verified_community_catalog_into_credentials(trigger="startup")
    except Exception:
        logger.warning("Verified community catalog sync failed during startup", exc_info=True)


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


class _CliMcpAsgiApp:
    """`/mcp` 的 ASGI 端点:转发到 lifespan 期间活着的 session manager。

    是类而非函数——Starlette 的 Route 把函数端点当 `func(request)` 包装,把
    类实例当裸 ASGI 直通,而 streamable HTTP 需要裸 ASGI(SSE 流式响应)。
    """

    def __init__(self, studio_app: FastAPI) -> None:
        self._studio_app = studio_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        manager = getattr(self._studio_app.state, "cli_mcp_manager", None)
        if manager is None:
            # lifespan 外(如未启动的裸 TestClient)明确 503,而不是把请求砸进
            # 未 run 的 manager。
            response = JSONResponse(
                {
                    "error_code": "MCP_SURFACE_NOT_STARTED",
                    "message": "CLI MCP surface is only available while the app lifespan is running",
                },
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
            await response(scope, receive, send)
            return
        await manager.handle_request(scope, receive, send)


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
    studio_app.include_router(test_inputs.router)
    studio_app.include_router(golden.router)
    studio_app.include_router(io_scan.router)
    studio_app.include_router(io_scan.skill_io_router)
    studio_app.include_router(compare.router)
    studio_app.include_router(compare_candidates.router)
    studio_app.include_router(node_llm_params.router)
    studio_app.include_router(runtime_config.router)
    studio_app.include_router(copilot.router)
    studio_app.include_router(llm.router)
    studio_app.include_router(loopback.router)
    studio_app.include_router(audit.router)
    studio_app.include_router(debug.router)
    studio_app.include_router(websockets.router)
    studio_app.include_router(system.router)

    # Route(+ 类实例 ASGI endpoint),不是 Mount:Mount("/mcp") 会把裸 `/mcp`
    # 307 到 `/mcp/`,而跨重定向丢 Authorization 头的 MCP 客户端会因此整片
    # 拿不到工具面。官方 SDK(mcp.server.fastmcp)同样用 Route + ASGI 类实例。
    studio_app.router.routes.append(
        Route(
            "/mcp",
            endpoint=_CliMcpAsgiApp(studio_app),
            methods=["GET", "POST", "DELETE"],
        )
    )
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
