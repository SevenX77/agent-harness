"""Connectivity checks for Studio LLM provider API keys."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
from services.llm_provider_meta import load_provider_meta

from app.models.llm_config import ProviderType
from app.services.copilot_test import (
    PingResult,
    _first_model_id,
    _NetworkError,
    _raise_for_status,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URLS: dict[ProviderType, str] = {
    "anthropic_compatible": "https://api.anthropic.com/v1",
    "openai_compatible": "https://api.openai.com/v1",
    "gemini_official": "https://generativelanguage.googleapis.com/v1beta",
    "wavespeed_any_llm": "https://llm.wavespeed.ai/v1",
}


@dataclass(frozen=True)
class PingResultExtended:
    """Extended ping result carrying full model list and raw payload."""

    latency_ms: int
    model_seen: str | None
    model_ids: list[str]
    raw_payload: Any


async def ping_provider(
    provider_code: str,
    provider_type: ProviderType,
    api_key: str,
    base_url: str | None = None,
) -> PingResult:
    """Ping one provider using the client style selected by ``provider_type``."""

    del provider_code
    normalized_base_url = (base_url or DEFAULT_BASE_URLS[provider_type]).rstrip("/")
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await _request_provider_models(
                client,
                provider_type,
                api_key,
                normalized_base_url,
            )
    except httpx.TimeoutException:
        raise TimeoutError from None
    except httpx.HTTPError as exc:
        raise _NetworkError(str(exc)) from exc

    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
    _raise_for_status(response)
    return PingResult(latency_ms=latency_ms, model_seen=_first_model_id(response))


async def ping_provider_extended(
    provider_code: str,
    provider_type: ProviderType,
    api_key: str,
    base_url: str | None = None,
) -> PingResultExtended:
    """Ping provider and return full model list (vendor-shape aware)."""

    del provider_code
    normalized_base_url = (base_url or DEFAULT_BASE_URLS[provider_type]).rstrip("/")
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await _request_provider_models(
                client,
                provider_type,
                api_key,
                normalized_base_url,
            )
    except httpx.TimeoutException:
        raise TimeoutError from None
    except httpx.HTTPError as exc:
        raise _NetworkError(str(exc)) from exc

    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
    _raise_for_status(response)

    try:
        payload = response.json()
    except ValueError:
        payload = None

    model_ids = _extract_model_ids(payload)
    return PingResultExtended(
        latency_ms=latency_ms,
        model_seen=model_ids[0] if model_ids else None,
        model_ids=model_ids,
        raw_payload=payload,
    )


def _extract_model_ids(payload: Any) -> list[str]:
    """Extract a flat list of model id strings from a provider /models payload."""

    if not isinstance(payload, dict):
        return []
    items = payload.get("data")
    if items is None:
        items = payload.get("models")
    if not isinstance(items, list):
        return []
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = item.get("id") or item.get("name")
        if isinstance(candidate, str) and candidate:
            ids.append(candidate)
    return ids


async def probe_compatible_sdks(vendor: str, api_key: str, base_url: str) -> list[str]:
    """Probe vendor metadata SDKs and return the SDKs that pass auth."""

    meta = load_provider_meta(vendor)
    available: list[str] = []
    for sdk in meta.compatible_sdks:
        try:
            status = await _send_1_token_request(
                sdk,
                api_key,
                base_url,
                meta.auth_header_format,
            )
        except Exception as exc:
            logger.warning("SDK probe vendor=%s sdk=%s failed: %s", vendor, sdk, exc)
            continue
        if status in (200, 400, 422):
            available.append(sdk)
        elif status in (401, 403):
            continue
        else:
            logger.warning(
                "SDK probe vendor=%s sdk=%s unexpected status=%s",
                vendor,
                sdk,
                status,
            )
    return available


async def _send_1_token_request(
    sdk: str,
    api_key: str,
    base_url: str,
    auth_header_template: str,
) -> int:
    """Dispatch one minimal request through the implementation for ``sdk``."""

    headers = _render_auth_headers(auth_header_template, api_key)
    if sdk == "openai_compatible":
        return await _probe_openai_1token(base_url, headers)
    if sdk == "anthropic_compatible":
        return await _probe_anthropic_1token(base_url, headers)
    if sdk == "gemini_official":
        return await _probe_gemini_1token(base_url, headers)
    if sdk == "wavespeed_any_llm":
        return await _probe_wavespeed_1token(base_url, headers)
    raise ValueError(f"Unknown SDK enum: {sdk}")


def _render_auth_headers(template: str, api_key: str) -> dict[str, str]:
    """Render a docs §1.5 auth header template into an HTTP header dict."""

    rendered = template.replace("${key}", api_key)
    headers: dict[str, str] = {}
    for line in rendered.strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


async def _probe_openai_1token(base_url: str, headers: dict[str, str]) -> int:
    """OpenAI-compatible chat completions probe."""

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "."}],
        "max_tokens": 1,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=15.0)
    return response.status_code


async def _probe_anthropic_1token(base_url: str, headers: dict[str, str]) -> int:
    """Anthropic-compatible messages probe."""

    url = f"{base_url.rstrip('/')}/v1/messages"
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "."}],
        "max_tokens": 1,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=15.0)
    return response.status_code


async def _probe_gemini_1token(base_url: str, headers: dict[str, str]) -> int:
    """Gemini official generateContent probe."""

    url = f"{base_url.rstrip('/')}/v1beta/models/gemini-2.0-flash:generateContent"
    payload = {
        "contents": [{"parts": [{"text": "."}]}],
        "generationConfig": {"maxOutputTokens": 1},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=15.0)
    return response.status_code


async def _probe_wavespeed_1token(base_url: str, headers: dict[str, str]) -> int:
    """WaveSpeed any-LLM gateway uses the OpenAI-compatible request shape."""

    return await _probe_openai_1token(base_url, headers)


async def _request_provider_models(
    client: httpx.AsyncClient,
    provider_type: ProviderType,
    api_key: str,
    base_url: str,
) -> httpx.Response:
    if provider_type == "anthropic_compatible":
        return await client.get(
            f"{base_url}/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
    if provider_type in ("openai_compatible", "wavespeed_any_llm"):
        return await client.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    return await client.get(f"{base_url}/models", params={"key": api_key})


__all__ = [
    "DEFAULT_BASE_URLS",
    "PingResultExtended",
    "ProviderType",
    "_extract_model_ids",
    "_render_auth_headers",
    "_send_1_token_request",
    "ping_provider",
    "ping_provider_extended",
    "probe_compatible_sdks",
]
