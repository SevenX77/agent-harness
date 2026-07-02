"""Gateway-owned provider endpoint and route probe primitives."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import urlparse, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from graph_agent_gateway.registry.schema import ProviderEndpoint, ProviderKind, ProviderRoute

ProviderProbeBackend = Literal["ark", "claude", "deepseek", "gemini", "openai"]
ProviderProbeStatus = Literal[
    "ok",
    "invalid_key",
    "invalid_model",
    "rate_limited",
    "quota_exceeded",
    "network_error",
    "timeout",
    "error",
]
OfficialCallMethod = Literal[
    "anthropic_messages",
    "ark_anthropic_messages",
    "ark_chat",
    "ark_responses",
    "deepseek_anthropic_messages",
    "deepseek_chat_completions",
    "gemini_generate_content",
    "openai_completions",
    "openai_chat_completions",
    "openai_responses",
]


class EndpointProbeResult(BaseModel):
    """Connectivity result for one provider endpoint."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    provider_kind: ProviderKind
    backend: ProviderProbeBackend
    base_url: str
    status: ProviderProbeStatus
    latency_ms: int | None = None
    model_ids: tuple[str, ...] = ()
    model_capabilities: dict[str, dict[str, Any]] = Field(default_factory=dict)
    message: str | None = None
    error_code: str | None = None

    @property
    def model_seen(self) -> str | None:
        return self.model_ids[0] if self.model_ids else None


class RouteProbeResult(BaseModel):
    """Generation probe result for one provider route."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    route_id: str
    provider_kind: ProviderKind
    backend: ProviderProbeBackend
    base_url: str
    model_id: str
    status: ProviderProbeStatus
    latency_ms: int | None = None
    message: str | None = None


async def test_provider_endpoint(
    endpoint: ProviderEndpoint,
    *,
    api_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 8.0,
) -> EndpointProbeResult:
    """Test one endpoint by asking its provider protocol for a model list."""

    backend = endpoint_probe_backend(endpoint)
    base_url = endpoint_probe_base_url(endpoint)
    secret = _endpoint_secret(endpoint, api_key)
    if not base_url:
        return EndpointProbeResult(
            endpoint_id=endpoint.endpoint_id,
            provider_kind=endpoint.provider_kind,
            backend=backend,
            base_url=base_url,
            status="error",
            message="Base URL is empty.",
            error_code="missing_config",
        )
    if not secret:
        return EndpointProbeResult(
            endpoint_id=endpoint.endpoint_id,
            provider_kind=endpoint.provider_kind,
            backend=backend,
            base_url=base_url,
            status="invalid_key",
            message="API key is empty.",
        )

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            response = await _request_models(client, backend, secret, base_url)
    except httpx.TimeoutException:
        return _endpoint_result(endpoint, backend, base_url, "timeout", started, message="Endpoint test timed out.")
    except httpx.HTTPError as exc:
        return _endpoint_result(endpoint, backend, base_url, "network_error", started, message=str(exc))

    status = _probe_status(response, model_not_found_status="error")
    return EndpointProbeResult(
        endpoint_id=endpoint.endpoint_id,
        provider_kind=endpoint.provider_kind,
        backend=backend,
        base_url=base_url,
        status=status,
        latency_ms=_elapsed_ms(started),
        model_ids=_model_ids(response) if status == "ok" else (),
        model_capabilities=_model_capabilities(response) if status == "ok" else {},
        message=None if status == "ok" else _provider_response_message(response),
        error_code=None if status == "ok" else _extract_vendor_error_code(response, default=status),
    )


async def test_provider_route(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    *,
    api_key: str | None = None,
    runtime_settings: Mapping[str, Any] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 15.0,
) -> RouteProbeResult:
    """Probe one concrete provider route with a minimal generation request."""

    backend = endpoint_probe_backend(endpoint)
    base_url = endpoint_probe_base_url(endpoint)
    secret = _endpoint_secret(endpoint, api_key)
    if not base_url:
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=backend,
            base_url=base_url,
            model_id=route.provider_model_id,
            status="error",
            message="Base URL is empty.",
        )
    if not secret:
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=backend,
            base_url=base_url,
            model_id=route.provider_model_id,
            status="invalid_key",
            message="API key is empty.",
        )

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            response = await _request_model_generation(
                client,
                backend,
                secret,
                base_url,
                route.provider_model_id,
                runtime_settings=runtime_settings,
            )
    except httpx.TimeoutException:
        return _route_result(endpoint, route, backend, base_url, "timeout", started)
    except httpx.HTTPError as exc:
        return _route_result(endpoint, route, backend, base_url, "network_error", started, message=str(exc))

    status = _probe_status(response, model_not_found_status="invalid_model")
    return RouteProbeResult(
        endpoint_id=endpoint.endpoint_id,
        route_id=route.route_id,
        provider_kind=endpoint.provider_kind,
        backend=backend,
        base_url=base_url,
        model_id=route.provider_model_id,
        status=status,
        latency_ms=_elapsed_ms(started),
        message=None if status == "ok" else _provider_response_message(response),
    )


async def probe_official_call_method(
    method_id: OfficialCallMethod,
    api_key: str,
    base_url: str,
    model_id: str,
    *,
    runtime_settings: Mapping[str, Any] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float | None = None,
) -> RouteProbeResult:
    """Probe one official provider API method for one concrete model."""

    normalized_base_url = base_url.rstrip("/")
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=timeout or _official_call_method_timeout(method_id, model_id, runtime_settings),
            transport=transport,
        ) as client:
            response = await _request_official_call_method_generation(
                client,
                method_id,
                api_key,
                normalized_base_url,
                model_id,
                runtime_settings=runtime_settings,
            )
    except httpx.TimeoutException:
        status: ProviderProbeStatus = "timeout"
        message = None
        latency_ms = None
    except httpx.HTTPError as exc:
        status = "network_error"
        message = str(exc)
        latency_ms = _elapsed_ms(started)
    else:
        status = _probe_status(response, model_not_found_status="invalid_model")
        message = None if status == "ok" else _provider_response_message(response)
        latency_ms = _elapsed_ms(started)

    return RouteProbeResult(
        endpoint_id="",
        route_id="",
        provider_kind="official",
        backend=_official_method_backend(method_id),
        base_url=normalized_base_url,
        model_id=model_id,
        status=status,
        latency_ms=latency_ms,
        message=message,
    )


def endpoint_probe_backend(endpoint: ProviderEndpoint) -> ProviderProbeBackend:
    """Infer the provider probe backend from endpoint protocol and identity."""

    base_host = _url_hostname(endpoint.base_url)
    endpoint_id = endpoint.endpoint_id.lower()
    if endpoint.protocol == "ark_runtime" or _host_matches(base_host, "volces.com") or "ark" in endpoint_id:
        return "ark"
    if endpoint.protocol == "anthropic_compatible":
        return "claude"
    if endpoint.protocol == "google_genai":
        return "gemini"
    if "deepseek" in base_host or "deepseek" in endpoint_id:
        return "deepseek"
    return "openai"


def endpoint_probe_base_url(endpoint: ProviderEndpoint) -> str:
    return endpoint.base_url.rstrip("/")


async def _request_models(
    client: httpx.AsyncClient,
    backend: ProviderProbeBackend,
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


async def _request_model_generation(
    client: httpx.AsyncClient,
    backend: ProviderProbeBackend,
    api_key: str,
    base_url: str,
    model_id: str,
    *,
    runtime_settings: Mapping[str, Any] | None = None,
) -> httpx.Response:
    max_tokens = _runtime_max_output_tokens(runtime_settings, default=1)
    reasoning = _runtime_reasoning_settings(runtime_settings)
    effort = _runtime_reasoning_effort(reasoning)
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
    if backend == "gemini":
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
    if backend == "ark":
        payload = {
            "model": model_id,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "."}]}],
            "max_output_tokens": max_tokens,
        }
        if effort:
            payload["reasoning"] = {"effort": effort}
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/api/v3/responses"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "."}],
        "max_completion_tokens" if backend == "openai" else "max_tokens": max_tokens,
    }
    if effort:
        payload["reasoning_effort"] = effort
    return await client.post(
        _join_base_url_and_endpoint(base_url, "/v1/chat/completions"),
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )


async def _request_official_call_method_generation(
    client: httpx.AsyncClient,
    method_id: OfficialCallMethod,
    api_key: str,
    base_url: str,
    model_id: str,
    *,
    runtime_settings: Mapping[str, Any] | None = None,
) -> httpx.Response:
    max_tokens = _runtime_max_output_tokens(runtime_settings, default=16)
    reasoning = _runtime_reasoning_settings(runtime_settings)
    effort = _runtime_reasoning_effort(reasoning)
    if method_id == "openai_responses":
        payload: dict[str, object] = {
            "model": model_id,
            "input": "Reply with one short word.",
            "max_output_tokens": max_tokens,
        }
        if effort or _runtime_reasoning_enabled(reasoning):
            payload["reasoning"] = {"effort": effort or "low"}
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/v1/responses"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if method_id == "openai_chat_completions":
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with one short word."}],
            "max_completion_tokens": max_tokens,
        }
        if effort or _runtime_reasoning_enabled(reasoning):
            payload["reasoning_effort"] = effort or "low"
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/v1/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if method_id == "openai_completions":
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/v1/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_id,
                "prompt": "Reply with one short word.",
                "max_tokens": max_tokens,
            },
        )
    if method_id == "anthropic_messages":
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/v1/messages"),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json=_anthropic_messages_payload(model_id, max_tokens, reasoning),
        )
    if method_id == "gemini_generate_content":
        generation_config: dict[str, object] = {"maxOutputTokens": max_tokens}
        thinking_config = _google_thinking_config(reasoning)
        if thinking_config is not None:
            generation_config["thinkingConfig"] = thinking_config
        return await client.post(
            _join_base_url_and_endpoint(base_url, f"/v1beta/models/{model_id}:generateContent"),
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": "Reply with one short word."}]}],
                "generationConfig": generation_config,
            },
        )
    if method_id == "deepseek_anthropic_messages":
        return await client.post(
            _deepseek_anthropic_messages_url(base_url),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json=_anthropic_messages_payload(model_id, max_tokens, reasoning, content_as_blocks=True),
        )
    if method_id == "ark_anthropic_messages":
        return await client.post(
            _ark_anthropic_messages_url(base_url),
            headers={"Authorization": f"Bearer {api_key}", "anthropic-version": "2023-06-01"},
            json=_anthropic_messages_payload(model_id, max_tokens, reasoning, content_as_blocks=True),
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
            _join_base_url_and_endpoint(base_url, "/api/v3/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if method_id == "ark_responses":
        payload = {
            "model": model_id,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "Reply with one short word."}]}],
            "max_output_tokens": max_tokens,
        }
        thinking = _ark_thinking_payload(reasoning)
        if thinking is not None:
            payload["thinking"] = thinking
        return await client.post(
            _join_base_url_and_endpoint(base_url, "/api/v3/responses"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with one short word."}],
        "max_tokens": max_tokens,
    }
    if effort or _runtime_reasoning_enabled(reasoning):
        payload["reasoning_effort"] = effort or "low"
    return await client.post(
        _join_base_url_and_endpoint(base_url, "/v1/chat/completions"),
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )


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


# Providers report an exhausted balance in provider-specific ways that do not
# follow the 402/403 status convention — Anthropic answers HTTP 400
# invalid_request_error with "credit balance is too low". A billing failure hits
# every model on the endpoint, so it must classify as structural quota_exceeded,
# never as a model-level invalid_model.
_BILLING_ERROR_MARKERS = (
    "credit balance",
    "insufficient balance",
    "insufficient credit",
    "insufficient_quota",
    "quota exceeded",
    "billing",
)


def _is_billing_error(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    source = error if isinstance(error, dict) else payload
    text = " ".join(
        str(value).lower()
        for value in (source.get("type"), source.get("code"), source.get("message"))
        if value is not None
    )
    return any(marker in text for marker in _BILLING_ERROR_MARKERS)


def _probe_status(
    response: httpx.Response,
    *,
    model_not_found_status: Literal["invalid_model", "error"],
) -> ProviderProbeStatus:
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
        if _is_billing_error(response):
            return "quota_exceeded"
        return model_not_found_status
    return "error"


def _model_ids(response: httpx.Response) -> tuple[str, ...]:
    try:
        payload = response.json()
    except ValueError:
        return ()
    values: list[str] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
                    values.append(item["id"])
        models = payload.get("models")
        if isinstance(models, list):
            for item in models:
                if isinstance(item, dict):
                    model_name = item.get("name")
                    if isinstance(model_name, str) and model_name:
                        values.append(model_name.removeprefix("models/"))
    return tuple(dict.fromkeys(values))


def _model_capabilities(response: httpx.Response) -> dict[str, dict[str, Any]]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    capabilities: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return capabilities
    entries = payload.get("data")
    if not isinstance(entries, list):
        entries = payload.get("models")
    if not isinstance(entries, list):
        return capabilities
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id:
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            model_id = name.removeprefix("models/")
        capabilities[model_id] = {key: value for key, value in entry.items() if key not in {"id", "name"}}
    return capabilities


def _provider_response_message(response: httpx.Response) -> str:
    error_code = _extract_vendor_error_code(response, default="")
    vendor_message = _extract_vendor_error_message(response)
    if error_code:
        message = f"Provider returned HTTP {response.status_code} ({error_code})."
    else:
        message = f"Provider returned HTTP {response.status_code}."
    if vendor_message:
        message = f"{message} {vendor_message}"
    return message


def _extract_vendor_error_code(response: httpx.Response, *, default: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return default
    if not isinstance(payload, dict):
        return default
    error = payload.get("error")
    if isinstance(error, dict):
        for key in ("code", "type", "status"):
            value = error.get(key)
            if isinstance(value, str) and value:
                return value
    return default


def _extract_vendor_error_message(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    message = payload.get("message")
    return message if isinstance(message, str) and message else None


def _join_base_url_and_endpoint(base_url: str, endpoint_path: str) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_endpoint = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
    base_path = urlsplit(normalized_base).path.rstrip("/")
    endpoint_without_version = normalized_endpoint
    for prefix in ("/v1", "/v1beta", "/api/v3"):
        if base_path.endswith(prefix) and endpoint_without_version.startswith(f"{prefix}/"):
            endpoint_without_version = endpoint_without_version[len(prefix) :]
            break
    parts = urlsplit(normalized_base)
    path = f"{parts.path.rstrip('/')}{endpoint_without_version}"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _endpoint_secret(endpoint: ProviderEndpoint, api_key: str | None) -> str:
    if api_key is not None:
        return api_key
    if endpoint.api_key is None:
        return ""
    return endpoint.api_key.get_secret_value()


def _endpoint_result(
    endpoint: ProviderEndpoint,
    backend: ProviderProbeBackend,
    base_url: str,
    status: ProviderProbeStatus,
    started: float,
    *,
    message: str | None = None,
) -> EndpointProbeResult:
    return EndpointProbeResult(
        endpoint_id=endpoint.endpoint_id,
        provider_kind=endpoint.provider_kind,
        backend=backend,
        base_url=base_url,
        status=status,
        latency_ms=_elapsed_ms(started),
        message=message,
    )


def _route_result(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    backend: ProviderProbeBackend,
    base_url: str,
    status: ProviderProbeStatus,
    started: float,
    *,
    message: str | None = None,
) -> RouteProbeResult:
    return RouteProbeResult(
        endpoint_id=endpoint.endpoint_id,
        route_id=route.route_id,
        provider_kind=endpoint.provider_kind,
        backend=backend,
        base_url=base_url,
        model_id=route.provider_model_id,
        status=status,
        latency_ms=_elapsed_ms(started),
        message=message,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _official_call_method_timeout(
    method_id: OfficialCallMethod,
    model_id: str,
    runtime_settings: Mapping[str, Any] | None = None,
) -> float:
    if method_id != "openai_responses":
        return 15.0
    model = model_id.lower()
    reasoning = _runtime_reasoning_settings(runtime_settings)
    effort = _runtime_reasoning_effort(reasoning)
    if model.startswith("gpt-5-pro"):
        return 180.0
    if model.startswith("gpt-5") and "-pro" in model:
        return 60.0 if effort in {"high", "xhigh"} else 30.0
    return 15.0


def _runtime_max_output_tokens(
    runtime_settings: Mapping[str, Any] | None,
    *,
    default: int,
) -> int:
    value = runtime_settings.get("max_output_tokens") if runtime_settings else None
    if isinstance(value, int | float) and value > 0:
        return max(1, int(value))
    return default


def _runtime_reasoning_settings(runtime_settings: Mapping[str, Any] | None) -> Mapping[str, Any]:
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


def _anthropic_thinking_payload(max_tokens: int, reasoning: Mapping[str, Any]) -> dict[str, object] | None:
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


def _ark_thinking_payload(reasoning: Mapping[str, Any]) -> dict[str, object] | None:
    if "enabled" not in reasoning:
        return None
    return {"type": "enabled" if _runtime_reasoning_enabled(reasoning) else "disabled"}


def _deepseek_anthropic_messages_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return f"{normalized}/anthropic/v1/messages"


def _ark_anthropic_messages_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api/v3"):
        normalized = normalized[: -len("/api/v3")]
    if normalized.endswith("/api/compatible"):
        return f"{normalized}/v1/messages"
    return f"{normalized}/api/compatible/v1/messages"


def _official_method_backend(method_id: OfficialCallMethod) -> ProviderProbeBackend:
    if method_id.startswith("ark_"):
        return "ark"
    if method_id.startswith("deepseek_"):
        return "deepseek"
    if method_id.startswith("gemini_"):
        return "gemini"
    if method_id.startswith("anthropic_"):
        return "claude"
    return "openai"


def _url_hostname(raw_url: str) -> str:
    if not raw_url:
        return ""
    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    return (parsed.hostname or "").lower().rstrip(".")


def _host_matches(hostname: str, domain: str) -> bool:
    normalized_domain = domain.lower().rstrip(".")
    return hostname == normalized_domain or hostname.endswith(f".{normalized_domain}")


__all__ = [
    "EndpointProbeResult",
    "OfficialCallMethod",
    "ProviderProbeBackend",
    "ProviderProbeStatus",
    "RouteProbeResult",
    "endpoint_probe_backend",
    "endpoint_probe_base_url",
    "probe_official_call_method",
    "test_provider_endpoint",
    "test_provider_route",
]
