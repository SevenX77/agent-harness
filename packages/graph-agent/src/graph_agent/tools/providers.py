"""Shared output/async helpers for graph_agent built-in tools."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast

logger = logging.getLogger(__name__)
T = TypeVar("T")


def ok(data: dict[str, Any]) -> str:
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


def run_async(factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
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
    return cast(T, result["value"])
