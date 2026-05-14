"""Connectivity checks for Copilot provider API keys."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.models.copilot import CopilotBackend

DEFAULT_BASE_URLS: dict[CopilotBackend, str] = {
    "claude": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "deepseek": "https://api.deepseek.com",
    "gemini": "https://generativelanguage.googleapis.com",
}


@dataclass(frozen=True)
class PingResult:
    latency_ms: int
    model_seen: str | None = None


class _Unauthorized(Exception):
    pass


class _RateLimited(Exception):
    pass


class _QuotaExceeded(Exception):
    pass


class _NetworkError(Exception):
    pass


async def _ping_provider(
    backend: CopilotBackend,
    api_key: str,
    base_url: str,
) -> PingResult:
    normalized_base_url = base_url.rstrip("/") or DEFAULT_BASE_URLS[backend]
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await _request_models(client, backend, api_key, normalized_base_url)
    except httpx.TimeoutException:
        raise
    except httpx.HTTPError as exc:
        raise _NetworkError(str(exc)) from exc

    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
    _raise_for_status(response)
    return PingResult(latency_ms=latency_ms, model_seen=_first_model_id(response))


async def _request_models(
    client: httpx.AsyncClient,
    backend: CopilotBackend,
    api_key: str,
    base_url: str,
) -> httpx.Response:
    if backend == "claude":
        return await client.get(
            f"{base_url}/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
    if backend in ("openai", "deepseek"):
        return await client.get(
            f"{base_url}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    return await client.get(f"{base_url}/v1beta/models", params={"key": api_key})


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise _Unauthorized
    if response.status_code == 429:
        raise _RateLimited
    if response.status_code in (402, 403):
        raise _QuotaExceeded
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _NetworkError(f"Provider returned HTTP {response.status_code}") from exc


def _first_model_id(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None

    items = payload.get("data")
    if items is None:
        items = payload.get("models")
    if not isinstance(items, list) or not items:
        return None

    first = items[0]
    if not isinstance(first, dict):
        return None

    model_id = first.get("id") or first.get("name")
    return model_id if isinstance(model_id, str) else None


__all__ = [
    "DEFAULT_BASE_URLS",
    "PingResult",
    "_NetworkError",
    "_QuotaExceeded",
    "_RateLimited",
    "_Unauthorized",
    "_ping_provider",
]
