"""Connectivity checks for Copilot provider API keys."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias
from urllib.parse import urlsplit, urlunsplit

import httpx

CopilotProvider: TypeAlias = Literal["ark", "claude", "deepseek", "gemini", "openai"]
OfficialCallMethod: TypeAlias = Literal[
    "anthropic_messages",
    "ark_chat",
    "ark_responses",
    "deepseek_anthropic_messages",
    "deepseek_chat_completions",
    "gemini_generate_content",
    "openai_chat_completions",
    "openai_responses",
]

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
    runtime_settings: Mapping[str, Any] | None = None,
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
                runtime_settings=runtime_settings,
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


async def _probe_official_call_method(
    method_id: OfficialCallMethod,
    api_key: str,
    base_url: str,
    model_id: str,
    runtime_settings: Mapping[str, Any] | None = None,
) -> ModelProbeResult:
    """Probe one official provider API family for one concrete model."""
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await _request_official_call_method_generation(
                client,
                method_id,
                api_key,
                base_url,
                model_id,
                runtime_settings=runtime_settings,
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
    runtime_settings: Mapping[str, Any] | None = None,
) -> httpx.Response:
    max_tokens = _runtime_max_output_tokens(runtime_settings, default=1)
    reasoning = _runtime_reasoning_settings(runtime_settings)
    reasoning_effort = _runtime_reasoning_effort(reasoning)
    if backend == "claude":
        payload: dict[str, object] = {
            "model": model_id,
            "messages": [{"role": "user", "content": "."}],
            "max_tokens": max_tokens,
        }
        thinking = _anthropic_thinking_payload(max_tokens, reasoning)
        if thinking is not None:
            payload["thinking"] = thinking
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/v1/messages"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json=payload,
        )
    if backend == "openai":
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "."}],
            "max_completion_tokens": max_tokens,
        }
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/v1/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if backend == "deepseek":
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "."}],
            "max_tokens": max_tokens,
        }
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/v1/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if backend == "ark":
        payload = {
            "model": model_id,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "."}],
                }
            ],
            "max_output_tokens": max_tokens,
        }
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/api/v3/responses"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    generation_config: dict[str, object] = {"maxOutputTokens": max_tokens}
    thinking_config = _google_thinking_config(reasoning)
    if thinking_config is not None:
        generation_config["thinkingConfig"] = thinking_config
    return await client.post(
        _join_base_url_and_endpoint(base_url, f"/v1beta/models/{model_id}:generateContent"),
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": "."}]}],
            "generationConfig": generation_config,
        },
    )


async def _request_official_call_method_generation(
    client: httpx.AsyncClient,
    method_id: OfficialCallMethod,
    api_key: str,
    base_url: str,
    model_id: str,
    runtime_settings: Mapping[str, Any] | None = None,
) -> httpx.Response:
    normalized_base_url = base_url.rstrip("/")
    max_tokens = _runtime_max_output_tokens(runtime_settings, default=16)
    reasoning = _runtime_reasoning_settings(runtime_settings)
    reasoning_effort = _runtime_reasoning_effort(reasoning)
    if method_id == "openai_responses":
        payload: dict[str, object] = {
            "model": model_id,
            "input": "Reply with one short word.",
            "max_output_tokens": max_tokens,
        }
        if reasoning_effort or _runtime_reasoning_enabled(reasoning):
            payload["reasoning"] = {"effort": reasoning_effort or "low"}
        return await client.post(
            _join_base_url_and_endpoint(normalized_base_url, "/v1/responses"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if method_id == "openai_chat_completions":
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with one short word."}],
            "max_completion_tokens": max_tokens,
        }
        if reasoning_effort or _runtime_reasoning_enabled(reasoning):
            payload["reasoning_effort"] = reasoning_effort or "low"
        return await client.post(
            _join_base_url_and_endpoint(normalized_base_url, "/v1/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if method_id == "anthropic_messages":
        return await client.post(
            _join_base_url_and_endpoint(normalized_base_url, "/v1/messages"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json=_anthropic_messages_payload(model_id, max_tokens, reasoning),
        )
    if method_id == "gemini_generate_content":
        generation_config: dict[str, object] = {"maxOutputTokens": max_tokens}
        thinking_config = _google_thinking_config(reasoning)
        if thinking_config is not None:
            generation_config["thinkingConfig"] = thinking_config
        return await client.post(
            _join_base_url_and_endpoint(
                normalized_base_url,
                f"/v1beta/models/{model_id}:generateContent",
            ),
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": "Reply with one short word."}]}],
                "generationConfig": generation_config,
            },
        )
    if method_id == "deepseek_chat_completions":
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with one short word."}],
            "max_tokens": max_tokens,
        }
        if reasoning_effort or _runtime_reasoning_enabled(reasoning):
            payload["reasoning_effort"] = reasoning_effort or "low"
        return await client.post(
            _join_base_url_and_endpoint(normalized_base_url, "/v1/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if method_id == "deepseek_anthropic_messages":
        return await client.post(
            _deepseek_anthropic_messages_url(normalized_base_url),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json=_anthropic_messages_payload(
                model_id,
                max_tokens,
                reasoning,
                content_as_blocks=True,
            ),
        )
    if method_id == "ark_chat":
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with one short word."}],
            "max_tokens": max_tokens,
        }
        thinking = _ark_thinking_payload(reasoning)
        if thinking is not None:
            payload["thinking"] = thinking
        return await client.post(
            _join_base_url_and_endpoint(normalized_base_url, "/api/v3/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if method_id == "ark_responses":
        payload = {
            "model": model_id,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Reply with one short word."}],
                }
            ],
            "max_output_tokens": max_tokens,
        }
        thinking = _ark_thinking_payload(reasoning)
        if thinking is not None:
            payload["thinking"] = thinking
        return await client.post(
            _join_base_url_and_endpoint(normalized_base_url, "/api/v3/responses"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    raise ValueError(f"Unknown official call method: {method_id}")


def _anthropic_messages_payload(
    model_id: str,
    max_tokens: int,
    reasoning: Mapping[str, Any],
    *,
    content_as_blocks: bool = False,
) -> dict[str, object]:
    content: object = (
        [{"type": "text", "text": "Reply with one short word."}]
        if content_as_blocks
        else "Reply with one short word."
    )
    payload: dict[str, object] = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    thinking = _anthropic_thinking_payload(max_tokens, reasoning)
    if thinking is not None:
        payload["thinking"] = thinking
    effort = _runtime_reasoning_effort(reasoning)
    if thinking is not None and effort:
        payload["output_config"] = {"effort": effort}
    return payload


def _deepseek_anthropic_messages_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return f"{normalized}/anthropic/v1/messages"


def _ark_thinking_payload(reasoning: Mapping[str, Any]) -> dict[str, object] | None:
    if "enabled" not in reasoning:
        return None
    return {"type": "enabled" if _runtime_reasoning_enabled(reasoning) else "disabled"}


def _runtime_max_output_tokens(
    runtime_settings: Mapping[str, Any] | None,
    *,
    default: int,
) -> int:
    value = runtime_settings.get("max_output_tokens") if runtime_settings else None
    if isinstance(value, int | float) and value > 0:
        return max(1, int(value))
    return default


def _runtime_reasoning_settings(
    runtime_settings: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    value = runtime_settings.get("reasoning") if runtime_settings else None
    return value if isinstance(value, Mapping) else {}


def _runtime_reasoning_effort(reasoning: Mapping[str, Any]) -> str | None:
    value = reasoning.get("effort")
    return value if isinstance(value, str) and value else None


def _runtime_reasoning_budget(reasoning: Mapping[str, Any]) -> int | None:
    value = reasoning.get("budget_tokens")
    return int(value) if isinstance(value, int | float) and value > 0 else None


def _runtime_reasoning_enabled(reasoning: Mapping[str, Any]) -> bool:
    return reasoning.get("enabled") is True


def _anthropic_thinking_payload(
    max_tokens: int,
    reasoning: Mapping[str, Any],
) -> dict[str, object] | None:
    if not _runtime_reasoning_enabled(reasoning):
        return None
    if reasoning.get("type") == "adaptive":
        return {"type": "adaptive"}
    budget = _runtime_reasoning_budget(reasoning)
    if budget is None:
        if max_tokens <= 1024:
            return {"type": "adaptive"}
        budget = max(1024, min(4096, max_tokens - 1))
    return {"type": "enabled", "budget_tokens": budget}


def _google_thinking_config(reasoning: Mapping[str, Any]) -> dict[str, object] | None:
    effort = _runtime_reasoning_effort(reasoning)
    if effort:
        return {"thinkingLevel": effort}
    budget = _runtime_reasoning_budget(reasoning)
    if budget is not None:
        return {"thinkingBudget": budget}
    if not _runtime_reasoning_enabled(reasoning):
        return None
    return {}


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
    "_request_official_call_method_generation",
    "_NetworkError",
    "_QuotaExceeded",
    "_RateLimited",
    "_Unauthorized",
    "_join_base_url_and_endpoint",
    "_model_ids",
    "_ping_provider",
    "_probe_official_call_method",
    "_probe_model",
]
