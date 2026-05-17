"""Internal sidecar lifecycle endpoints."""

from __future__ import annotations

import asyncio
import os
import signal

from fastapi import APIRouter, Request

from app.core.exceptions import error_response, raise_error_response

router = APIRouter(tags=["system"])

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/shutdown")
async def shutdown(request: Request) -> dict[str, str]:
    _assert_shutdown_allowed(request)
    loop = asyncio.get_running_loop()
    loop.call_soon(_request_server_exit, request)
    return {"status": "shutting_down"}


def _assert_shutdown_allowed(request: Request) -> None:
    token = os.environ.get("STUDIO_SHUTDOWN_TOKEN")
    provided = request.headers.get("x-studio-shutdown-token")
    client_host = request.client.host if request.client else ""
    if client_host not in _LOOPBACK_HOSTS or not token or provided != token:
        raise_error_response(
            error_response(
                error_code="SHUTDOWN_FORBIDDEN",
                http_status=403,
                message="Shutdown is only allowed from loopback with a valid token",
                details={"client_host": client_host or None},
                retry_strategy="not_retryable",
            )
        )


def _request_server_exit(request: Request) -> None:
    app = request.app
    server = getattr(app.state, "uvicorn_server", None)
    if server is not None:
        server.should_exit = True
    elif os.environ.get("STUDIO_DISABLE_PROCESS_SHUTDOWN") == "1" or (
        request.client and request.client.host == "testclient"
    ):
        app.state.shutdown_requested = True
    else:
        os.kill(os.getpid(), signal.SIGINT)
