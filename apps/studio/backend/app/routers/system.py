"""Internal sidecar lifecycle endpoints."""

from __future__ import annotations

import asyncio
import os
import signal

from fastapi import APIRouter, HTTPException, Request

from app.core.backends import get_backend_config
from app.services.runtime_truth_sources import (
    build_truth_source_sections,
    read_truth_source_content,
)

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/system/truth-sources")
async def truth_sources() -> dict[str, object]:
    return build_truth_source_sections()


@router.get("/api/system/truth-sources/{source_id}/content")
async def truth_source_content(source_id: str) -> dict[str, object]:
    content = read_truth_source_content(source_id)
    if content is None:
        raise HTTPException(status_code=404, detail="truth source content unavailable")
    return content


@router.get("/api/system/community-catalog-config")
async def community_catalog_config() -> dict[str, str]:
    """Read-only view of the baked-in community catalog config (R-G3 / R10).

    Both the manifest URL and the ed25519 signing public key ship as public
    defaults (no secrets) and are env-overridable; the UI shows them read-only.
    """
    cfg = get_backend_config()
    return {
        "manifest_url": cfg.community_catalog_manifest_url,
        "signing_pubkey": cfg.community_catalog_signing_pubkey,
    }


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
