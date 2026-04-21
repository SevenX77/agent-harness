"""Shared provider helpers for graph_agent built-in tools.

Auth, image loading, context helpers, and async polling for
WaveSpeed and ARK providers.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx

from ..config.multimodal_config import (
    MultimodalProviderDef,
    ResolvedMultimodalProvider,
    get_multimodal_role_config,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


# ---------------------------------------------------------------------------
# Auth & config
# ---------------------------------------------------------------------------


def get_api_key(prov: MultimodalProviderDef) -> str:
    key = os.getenv(prov.api_key_env, "") if prov.api_key_env else ""
    if not key:
        raise RuntimeError(f"{prov.api_key_env} not set")
    return key


def get_proxy(prov: MultimodalProviderDef) -> str | None:
    if prov.proxy_env:
        return os.getenv(prov.proxy_env) or None
    return None


def call_chain(role: str) -> list[ResolvedMultimodalProvider]:
    return get_multimodal_role_config().resolve_role(role).call_chain


# ---------------------------------------------------------------------------
# Image loading
# ---------------------------------------------------------------------------


def load_image_bytes_sync(source: str) -> tuple[bytes, str]:
    """Load image from data URI, HTTP URL, or local file path."""
    if source.startswith("data:"):
        if "," not in source:
            raise RuntimeError(f"Malformed data URI (missing comma separator): {source[:100]}")
        header, data = source.split(",", 1)
        mime = header.split(";")[0].replace("data:", "")
        return base64.b64decode(data), mime

    if source.startswith(("http://", "https://")):
        proxy = os.getenv("HTTP_PROXY") or os.getenv("GEMINI_PROXY") or None
        with httpx.Client(
            timeout=60, proxy=proxy, follow_redirects=True
        ) as client:
            resp = client.get(source)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/jpeg")
            return resp.content, ct.split(";")[0].strip()

    path = Path(source)
    if not path.is_file():
        raise RuntimeError(f"local image not found: {source}")
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return path.read_bytes(), mime_map.get(path.suffix.lower(), "image/jpeg")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def ok(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def err(exc: Exception) -> str:
    return json.dumps(
        {
            "status": "error",
            "error": str(exc),
            "error_type": type(exc).__name__,
        },
        ensure_ascii=False,
    )


def run_async(factory: Callable[[], Awaitable[T]]) -> T:
    """Run an async factory from sync code, even inside an active event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(factory())
        except BaseException as exc:  # pragma: no cover - threaded handoff
            error["exc"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=300)
    if thread.is_alive():
        raise TimeoutError("run_async: async factory did not complete within 300s")
    if "exc" in error:
        raise error["exc"]
    return result["value"]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Async polling: WaveSpeed
# ---------------------------------------------------------------------------


async def wavespeed_submit(
    prov: MultimodalProviderDef,
    model_path: str,
    payload: dict,
) -> tuple[str, int]:
    api_key, proxy = get_api_key(prov), get_proxy(prov)
    url = f"{prov.base_url}/{model_path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    start = time.time()
    async with httpx.AsyncClient(timeout=60, proxy=proxy) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        task_id: str = resp.json()["data"]["id"]
    return task_id, int((time.time() - start) * 1000)


async def wavespeed_poll(
    prov: MultimodalProviderDef, task_id: str
) -> tuple[str, int]:
    api_key, proxy = get_api_key(prov), get_proxy(prov)
    url = f"{prov.base_url}/predictions/{task_id}/result"
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.time() + prov.timeout
    poll_count = 0
    async with httpx.AsyncClient(timeout=30, proxy=proxy) as client:
        while time.time() < deadline:
            await asyncio.sleep(prov.poll_interval)
            poll_count += 1
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()["data"]
            if data.get("status") == "completed":
                outputs = data.get("outputs", [])
                if not outputs:
                    raise RuntimeError(
                        f"WaveSpeed {task_id} completed but outputs empty"
                    )
                return outputs[0], poll_count
            if data.get("status") == "failed":
                raise RuntimeError(
                    f"WaveSpeed task failed: {data.get('error', '?')}"
                )
    raise RuntimeError(f"WaveSpeed {task_id} timed out (>{prov.timeout}s)")


# ---------------------------------------------------------------------------
# Async polling: ARK video
# ---------------------------------------------------------------------------


async def ark_video_submit_and_poll(
    prov: MultimodalProviderDef,
    payload: dict,
) -> tuple[str, int, str | None]:
    """Submit ARK video task, poll until done.

    Returns (video_url, poll_count, last_frame_url).
    """
    api_key, proxy = get_api_key(prov), get_proxy(prov)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    submit_url = f"{prov.base_url}/contents/generations/tasks"

    async with httpx.AsyncClient(timeout=60, proxy=proxy) as client:
        resp = await client.post(submit_url, headers=headers, json=payload)
        resp.raise_for_status()
        task_id: str = resp.json()["id"]

    poll_url = f"{prov.base_url}/contents/generations/tasks/{task_id}"
    poll_headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.time() + prov.timeout
    poll_count = 0

    async with httpx.AsyncClient(timeout=30, proxy=proxy) as client:
        while time.time() < deadline:
            await asyncio.sleep(prov.poll_interval)
            poll_count += 1
            resp = await client.get(poll_url, headers=poll_headers)
            resp.raise_for_status()
            result = resp.json()
            status = result.get("status", "")
            if status == "succeeded":
                content = result.get("content", {})
                video_url = (
                    content.get("video_url", "")
                    if isinstance(content, dict)
                    else ""
                )
                last_frame = (
                    content.get("last_frame_url")
                    if isinstance(content, dict)
                    else None
                )
                if not video_url:
                    raise RuntimeError(
                        f"ARK {task_id} succeeded but video_url empty"
                    )
                return video_url, poll_count, last_frame
            if status in ("failed", "canceled"):
                raise RuntimeError(
                    f"ARK task {status}: {result.get('error', '?')}"
                )
    raise RuntimeError(f"ARK {task_id} timed out (>{prov.timeout}s)")
