"""Connectivity checks for Studio LLM provider API keys."""

from __future__ import annotations

import time
from typing import Literal

import httpx

from app.services.copilot_test import (
    PingResult,
    _first_model_id,
    _NetworkError,
    _raise_for_status,
)

ProviderType = Literal[
    "anthropic_compatible",
    "openai_compatible",
    "gemini_official",
    "wavespeed_any_llm",
]

DEFAULT_BASE_URLS: dict[ProviderType, str] = {
    "anthropic_compatible": "https://api.anthropic.com",
    "openai_compatible": "https://api.openai.com",
    "gemini_official": "https://generativelanguage.googleapis.com",
    "wavespeed_any_llm": "https://api.wavespeed.ai",
}


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


async def _request_provider_models(
    client: httpx.AsyncClient,
    provider_type: ProviderType,
    api_key: str,
    base_url: str,
) -> httpx.Response:
    if provider_type == "anthropic_compatible":
        return await client.get(
            f"{base_url}/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
    if provider_type in ("openai_compatible", "wavespeed_any_llm"):
        return await client.get(
            f"{base_url}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    return await client.get(f"{base_url}/v1beta/models", params={"key": api_key})


__all__ = [
    "DEFAULT_BASE_URLS",
    "ProviderType",
    "ping_provider",
]
