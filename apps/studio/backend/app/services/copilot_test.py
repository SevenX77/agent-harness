"""Connectivity checks for Copilot provider API keys."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, TypeAlias
from urllib.parse import urlsplit, urlunsplit

import httpx

CopilotProvider: TypeAlias = Literal["ark", "claude", "deepseek", "gemini", "openai"]

DEFAULT_BASE_URLS: dict[CopilotProvider, str] = {
    "ark": "https://ark.cn-beijing.volces.com/api/v3",
    "claude": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "deepseek": "https://api.deepseek.com",
    "gemini": "https://generativelanguage.googleapis.com",
}


@dataclass(frozen=True)
class PingResult:
    latency_ms: int
    model_ids: tuple[str, ...] = ()

    @property
    def model_seen(self) -> str | None:
        return self.model_ids[0] if self.model_ids else None


@dataclass(frozen=True)
class ModelProbeResult:
    model_id: str
    status: Literal[
        "ok",
        "invalid_model",
        "invalid_key",
        "rate_limited",
        "quota_exceeded",
        "network_error",
        "timeout",
        "error",
    ]
    latency_ms: int | None = None
    message: str | None = None


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
    return PingResult(latency_ms=latency_ms, model_ids=_model_ids(response))


async def _request_models(
    client: httpx.AsyncClient,
    backend: CopilotProvider,
    api_key: str,
    base_url: str,
) -> httpx.Response:
    if backend == "claude":
        return await client.get(
            _join_base_url_and_endpoint(base_url, "/v1/models"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
    if backend in ("ark", "openai", "deepseek"):
        endpoint_path = "/api/v3/models" if backend == "ark" else "/v1/models"
        return await client.get(
            _join_base_url_and_endpoint(base_url, endpoint_path),
            headers={"Authorization": f"Bearer {api_key}"},
        )
    return await client.get(
        _join_base_url_and_endpoint(base_url, "/v1beta/models"),
        params={"key": api_key},
    )


async def _probe_model(
    backend: CopilotProvider,
    api_key: str,
    base_url: str,
    model_id: str,
) -> ModelProbeResult:
    """Probe one concrete model with a minimal generation request."""
    normalized_base_url = base_url.rstrip("/") or DEFAULT_BASE_URLS[backend]
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await _request_model_generation(
                client,
                backend,
                api_key,
                normalized_base_url,
                model_id,
            )
    except httpx.TimeoutException:
        return ModelProbeResult(model_id=model_id, status="timeout")
    except httpx.HTTPError as exc:
        return ModelProbeResult(model_id=model_id, status="network_error", message=str(exc))

    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
    return ModelProbeResult(
        model_id=model_id,
        status=_model_probe_status(response),
        latency_ms=latency_ms,
        message=None if response.status_code < 400 else _model_probe_message(response),
    )


async def _request_model_generation(
    client: httpx.AsyncClient,
    backend: CopilotProvider,
    api_key: str,
    base_url: str,
    model_id: str,
) -> httpx.Response:
    if backend == "claude":
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/v1/messages"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "."}],
                "max_tokens": 1,
            },
        )
    if backend in ("openai", "deepseek"):
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/v1/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "."}],
                "max_tokens": 1,
            },
        )
    if backend == "ark":
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/api/v3/responses"),
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_id,
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "."}],
                    }
                ],
            },
        )
    return await client.post(
        _join_base_url_and_endpoint(base_url, f"/v1beta/models/{model_id}:generateContent"),
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": "."}]}],
            "generationConfig": {"maxOutputTokens": 1},
        },
    )


def _model_probe_status(
    response: httpx.Response,
) -> Literal[
    "ok",
    "invalid_model",
    "invalid_key",
    "rate_limited",
    "quota_exceeded",
    "network_error",
    "timeout",
    "error",
]:
    code = response.status_code
    if 200 <= code < 300:
        return "ok"
    if code == 401:
        return "invalid_key"
    if code == 429:
        return "rate_limited"
    if code in (402, 403):
        return "quota_exceeded"
    if code in (400, 404):
        return "invalid_model"
    return "error"


def _model_probe_message(response: httpx.Response) -> str:
    error_code = _extract_vendor_error_code(response, default="")
    if error_code:
        return f"Provider returned HTTP {response.status_code} ({error_code})."
    return f"Provider returned HTTP {response.status_code}."


def _raise_for_status(response: httpx.Response) -> None:
    code = response.status_code
    if code == 401:
        raise _Unauthorized(
            "HTTP 401 from provider",
            error_code=_extract_vendor_error_code(response, default="unauthorized"),
        )
    if code == 429:
        raise _RateLimited(
            "HTTP 429 from provider",
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

    * Anthropic: ``{"error": {"type": "invalid_api_key", ...}}``.
    * OpenAI: ``{"error": {"type": "invalid_request_error", "code": "invalid_api_key", ...}}``.
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
    for key in ("code", "type", "status"):
        candidate = error.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return default


def _first_model_id(response: httpx.Response) -> str | None:
    model_ids = _model_ids(response)
    return model_ids[0] if model_ids else None


def _model_ids(response: httpx.Response) -> tuple[str, ...]:
    try:
        payload = response.json()
    except ValueError:
        return ()
    if not isinstance(payload, dict):
        return ()

    items = payload.get("data")
    model_key = "id"
    if items is None:
        items = payload.get("models")
        model_key = "name"
    if not isinstance(items, list) or not items:
        return ()

    seen: set[str] = set()
    model_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get(model_key)
        if not isinstance(model_id, str):
            continue
        if model_key == "name" and model_id.startswith("models/"):
            model_id = model_id.removeprefix("models/")
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        model_ids.append(model_id)
    return tuple(model_ids)


def _join_base_url_and_endpoint(base_url: str, endpoint_path: str) -> str:
    """Join a user base URL and endpoint path without duplicating path prefixes."""
    normalized_base = base_url.rstrip("/")
    split = urlsplit(normalized_base)
    base_segments = [segment for segment in split.path.split("/") if segment]
    endpoint_segments = [segment for segment in endpoint_path.split("/") if segment]

    overlap = 0
    max_overlap = min(len(base_segments), len(endpoint_segments))
    for count in range(max_overlap, 0, -1):
        if base_segments[-count:] == endpoint_segments[:count]:
            overlap = count
            break

    joined_segments = base_segments + endpoint_segments[overlap:]
    path = "/" + "/".join(joined_segments) if joined_segments else ""
    return urlunsplit((split.scheme, split.netloc, path, split.query, split.fragment))


__all__ = [
    "DEFAULT_BASE_URLS",
    "ModelProbeResult",
    "PingResult",
    "_NetworkError",
    "_QuotaExceeded",
    "_RateLimited",
    "_Unauthorized",
    "_join_base_url_and_endpoint",
    "_model_ids",
    "_ping_provider",
    "_probe_model",
]
