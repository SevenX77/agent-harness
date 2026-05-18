"""Connectivity checks for Copilot provider API keys."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, TypeAlias

import httpx

CopilotProvider: TypeAlias = Literal["claude", "deepseek", "gemini", "openai"]

DEFAULT_BASE_URLS: dict[CopilotProvider, str] = {
    "claude": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "deepseek": "https://api.deepseek.com",
    "gemini": "https://generativelanguage.googleapis.com",
}


@dataclass(frozen=True)
class PingResult:
    latency_ms: int
    model_seen: str | None = None


class _ProviderTestError(Exception):
    """Base class for provider Test errors carrying a vendor-specific code."""

    def __init__(self, message: str = "", *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code or ""


class _Unauthorized(_ProviderTestError):
    pass


class _RateLimited(_ProviderTestError):
    pass


class _QuotaExceeded(_ProviderTestError):
    pass


class _NetworkError(_ProviderTestError):
    pass


async def _ping_provider(
    backend: CopilotProvider,
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
    backend: CopilotProvider,
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
    code = response.status_code
    if code == 401:
        raise _Unauthorized(
            f"HTTP 401 from provider",
            error_code=_extract_vendor_error_code(response, default="unauthorized"),
        )
    if code == 429:
        raise _RateLimited(
            f"HTTP 429 from provider",
            error_code=_extract_vendor_error_code(response, default="rate_limited"),
        )
    if code in (402, 403):
        raise _QuotaExceeded(
            f"HTTP {code} from provider",
            error_code=_extract_vendor_error_code(response, default="quota_exceeded"),
        )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _NetworkError(
            f"Provider returned HTTP {code}",
            error_code=_extract_vendor_error_code(response, default="http_error"),
        ) from exc


def _extract_vendor_error_code(response: httpx.Response, *, default: str) -> str:
    """Extract a vendor-specific error code from a failed /models response body.

    Vendors disagree on the shape:

    * Anthropic / OpenAI: ``{"error": {"type": "invalid_api_key", ...}}``
      (OpenAI also exposes ``code``).
    * Gemini: ``{"error": {"status": "PERMISSION_DENIED", ...}}``.

    Falls back to ``default`` when no recognized code is present (e.g. when
    the body is plain text or the field is missing).
    """

    try:
        payload = response.json()
    except ValueError:
        return default
    if not isinstance(payload, dict):
        return default
    error = payload.get("error")
    if not isinstance(error, dict):
        return default
    for key in ("type", "code", "status"):
        candidate = error.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return default


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
