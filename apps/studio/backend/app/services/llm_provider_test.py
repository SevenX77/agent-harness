"""Connectivity checks for Studio LLM provider API keys."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.models.llm_config import ProviderType
from app.services.copilot_test import (
    PingResult,
    _first_model_id,
    _NetworkError,
    _raise_for_status,
)

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
    "ping_provider",
    "ping_provider_extended",
]
