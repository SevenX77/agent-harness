"""Connectivity checks for Studio LLM provider API keys."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from services.llm_provider_meta import DOCS_DIR, load_provider_meta

from app.models.llm_config import ModelInfo, ProviderType
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
    "google_genai": "https://generativelanguage.googleapis.com/v1beta",
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

    model_ids = [model.id for model in _parse_models_response(payload, provider_code)]
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
    if sdk == "google_genai":
        return await _probe_google_genai_1token(base_url, headers)
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


async def _probe_google_genai_1token(base_url: str, headers: dict[str, str]) -> int:
    """Google GenAI generateContent probe."""

    url = f"{base_url.rstrip('/')}/v1beta/models/gemini-2.0-flash:generateContent"
    payload = {
        "contents": [{"parts": [{"text": "."}]}],
        "generationConfig": {"maxOutputTokens": 1},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=15.0)
    return response.status_code


async def probe_available_models(vendor: str, api_key: str, base_url: str) -> list[ModelInfo]:
    """Load model ids via the provider /models endpoint or provider docs fallback."""

    meta = load_provider_meta(vendor)
    if meta.models_endpoint_path is None:
        return _load_fallback_models_from_doc(vendor)

    headers = _render_auth_headers(meta.auth_header_format, api_key)
    url = _join_base_url_and_endpoint(base_url, meta.models_endpoint_path)
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=15.0)
    response.raise_for_status()
    return _parse_models_response(response.json(), vendor)


def _load_fallback_models_from_doc(vendor: str) -> list[ModelInfo]:
    """Load backtick-wrapped model ids from app/data/llm_providers/<vendor>.md §4."""

    doc_path = DOCS_DIR / f"{vendor}.md"
    if not doc_path.exists():
        return []
    content = doc_path.read_text(encoding="utf-8")
    model_ids = _extract_model_ids_from_section(_extract_section_4(content))
    return _model_infos_from_ids(model_ids, vendor)


def _model_infos_from_ids(model_ids: list[str], vendor: str) -> list[ModelInfo]:
    del vendor
    return [ModelInfo(id=model_id) for model_id in model_ids]


def _extract_section_4(md_content: str) -> str:
    """Extract the §4 markdown section body."""

    pattern = re.compile(
        r"^##\s+§4[^\n]*\n(.*?)(?=^##\s+§|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(md_content)
    return match.group(1) if match else ""


def _extract_model_ids_from_section(section: str) -> list[str]:
    """Extract unique backtick-wrapped model ids from a markdown section."""

    matches = re.findall(r"`([a-zA-Z0-9][a-zA-Z0-9._/-]*)`", section)
    seen: set[str] = set()
    result: list[str] = []
    for model_id in matches:
        if model_id in seen:
            continue
        seen.add(model_id)
        result.append(model_id)
    return result


def _parse_models_response(json_resp: Any, vendor: str) -> list[ModelInfo]:
    """Normalize supported provider /models payload shapes to ``ModelInfo`` records."""

    del vendor

    if not isinstance(json_resp, dict):
        return []
    data = json_resp.get("data")
    if isinstance(data, list):
        return [
            ModelInfo(id=item["id"], capabilities=_extract_capabilities(item, id_keys={"id"}))
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
        ]
    models = json_resp.get("models")
    if isinstance(models, list):
        return [
            ModelInfo(
                id=item["name"].removeprefix("models/"),
                capabilities=_extract_capabilities(item, id_keys={"name"}),
            )
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]
        ]
    return []


def _extract_capabilities(item: dict[str, Any], *, id_keys: set[str]) -> dict[str, Any]:
    """Collect provider model metadata into a vendor-neutral capability dict."""

    capabilities: dict[str, Any] = {}
    nested = item.get("capabilities")
    for key, value in item.items():
        if key in id_keys or key == "capabilities":
            continue
        capabilities[key] = value
    if isinstance(nested, dict):
        capabilities.update(nested)

    context_value = _first_present(
        item,
        "max_context_tokens",
        "max_input_tokens",
        "inputTokenLimit",
        "context_length",
    )
    if context_value is not None:
        capabilities["max_context_tokens"] = context_value

    output_value = _first_present(
        item,
        "max_output_tokens",
        "outputTokenLimit",
        "max_tokens",
    )
    if output_value is not None:
        capabilities["max_output_tokens"] = output_value

    return capabilities


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _join_base_url_and_endpoint(base_url: str, endpoint_path: str) -> str:
    """Join a user base URL and metadata endpoint without duplicating path prefixes."""

    normalized_base = base_url.rstrip("/")
    normalized_endpoint = "/" + endpoint_path.lstrip("/")
    parent, _, leaf = normalized_endpoint.rpartition("/")
    if parent and normalized_base.endswith(parent):
        return f"{normalized_base}/{leaf}"
    return f"{normalized_base}{normalized_endpoint}"


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
    if provider_type == "openai_compatible":
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
    "_extract_model_ids_from_section",
    "_extract_section_4",
    "_load_fallback_models_from_doc",
    "_join_base_url_and_endpoint",
    "_parse_models_response",
    "_render_auth_headers",
    "_send_1_token_request",
    "ping_provider",
    "ping_provider_extended",
    "probe_available_models",
    "probe_compatible_sdks",
]
