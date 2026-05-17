"""Internal sidecar lifecycle endpoints."""

from __future__ import annotations

import asyncio
import os
import signal

from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/shutdown")
async def shutdown(request: Request) -> dict[str, str]:
    loop = asyncio.get_running_loop()
    loop.call_soon(_request_server_exit, request)
    return {"status": "shutting_down"}


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
