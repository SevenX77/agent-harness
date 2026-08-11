"""Sending one probe and reporting what came back.

Each entry point asks one question of one provider: what does this endpoint
list, can this route generate, does this official method work for this model.
The request is rendered by `dialect`, the answer read by `judge`; what is left
here is which question to ask and how to describe the attempt.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx

from graph_agent_gateway.dialect import (
    Image,
    Prompt,
    Reasoning,
    VersionedPath,
    dialect_for_method,
    join_base_url_and_path,
)
from graph_agent_gateway.registry import (
    ProviderEndpoint,
    ProviderProbeBackend,
    ProviderRoute,
    apply_call_method_base_url,
    call_method_is_officially_probeable,
    preferred_call_method_for_endpoint,
    provider_backend_for_method,
)

from .judge import (
    ProviderProbeStatus,
    model_capabilities,
    model_ids,
    probe_status,
    provider_response_message,
    vendor_error_code,
)
from .results import EndpointProbeResult, RouteProbeResult

OfficialCallMethod = str


async def probe_provider_endpoint(
    endpoint: ProviderEndpoint,
    *,
    api_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 8.0,
) -> EndpointProbeResult:
    """Test one endpoint by asking its provider protocol for a model list."""

    backend = endpoint_probe_backend(endpoint)
    wire = probe_wire_backend(endpoint.protocol)
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
            response = await _request_models(client, wire, secret, base_url)
    except httpx.TimeoutException:
        return _endpoint_result(endpoint, backend, base_url, "timeout", started, message="Endpoint test timed out.")
    except httpx.HTTPError as exc:
        return _endpoint_result(endpoint, backend, base_url, "network_error", started, message=str(exc))

    status = probe_status(response, model_not_found_status="error", probed_backend=wire)
    return EndpointProbeResult(
        endpoint_id=endpoint.endpoint_id,
        provider_kind=endpoint.provider_kind,
        backend=backend,
        base_url=base_url,
        status=status,
        latency_ms=_elapsed_ms(started),
        model_ids=model_ids(response) if status == "ok" else (),
        model_capabilities=model_capabilities(response) if status == "ok" else {},
        message=None if status == "ok" else provider_response_message(response),
        error_code=(
            None
            if status == "ok"
            # The classification is authoritative for a protocol mismatch — a
            # misroute/route-rejection body often carries the FOREIGN upstream's
            # vendor code, which must not leak past the classification the gate
            # and UI key off.
            else "protocol_unsupported"
            if status == "protocol_unsupported"
            else vendor_error_code(response, default=status)
        ),
    )


async def probe_provider_route(
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
    wire = probe_wire_backend(endpoint.protocol)
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
                wire,
                secret,
                base_url,
                route.provider_model_id,
                runtime_settings=runtime_settings,
            )
    except httpx.TimeoutException:
        return _route_result(endpoint, route, backend, base_url, "timeout", started)
    except httpx.HTTPError as exc:
        return _route_result(endpoint, route, backend, base_url, "network_error", started, message=str(exc))

    status = probe_status(response, model_not_found_status="invalid_model", probed_backend=wire)
    return RouteProbeResult(
        endpoint_id=endpoint.endpoint_id,
        route_id=route.route_id,
        provider_kind=endpoint.provider_kind,
        backend=backend,
        base_url=base_url,
        model_id=route.provider_model_id,
        status=status,
        latency_ms=_elapsed_ms(started),
        message=None if status == "ok" else provider_response_message(response),
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
    multimodal: bool = False,
) -> RouteProbeResult:
    """Probe one official provider API method for one concrete model.

    ``multimodal=True`` 在探测消息里加一张测试图(#11):provider 接受(2xx)=该模型
    接受图像输入(input_modalities 含 image),4xx 拒绝=不支持。老式 completions
    接口无多模态能力,``multimodal=True`` 时直接 ``ValueError``。
    """

    if not call_method_is_officially_probeable(method_id):
        raise ValueError(f"Not an officially probeable call method: {method_id}")

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
                multimodal=multimodal,
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
        status = probe_status(response, model_not_found_status="invalid_model")
        message = None if status == "ok" else provider_response_message(response)
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


# The two protocols DeepSeek publishes a surface for. A url on that host saying
# anything else is not a DeepSeek surface, whatever the host suggests.
_DEEPSEEK_SURFACES = ("openai_compatible", "anthropic_compatible")


def endpoint_probe_backend(endpoint: ProviderEndpoint) -> ProviderProbeBackend:
    """Whose official API an endpoint belongs to.

    A question about the vendor, not about the wire: it decides which official
    methods and capability ladders are offered for this endpoint, while
    `probe_wire_backend` decides how to speak to it. DeepSeek publishes its own
    method list on both an OpenAI-compatible and an Anthropic-compatible
    surface, and its url is the only place that identity appears.

    The endpoint's NAME is not consulted. It is a label the user typed, and it
    used to change which token budget field the probe sent.
    """

    if endpoint.protocol in _DEEPSEEK_SURFACES and _host_matches(
        _url_hostname(endpoint.base_url), "deepseek.com"
    ):
        return "deepseek"
    return probe_wire_backend(endpoint.protocol)


def probe_wire_backend(protocol: str) -> ProviderProbeBackend:
    """How to speak to an endpoint: the protocol it declares.

    The protocol is the user's statement about the wire and the thing
    production dispatches on (`call/dispatch.py`), so a hostname never
    overrules it — an endpoint declaring `anthropic_compatible` is probed with
    Anthropic's wire wherever it is hosted.
    """

    # No base url on purpose: host rules answer the vendor question, not this one.
    return provider_backend_for_method(preferred_call_method_for_endpoint(protocol, base_url=None))


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
            join_base_url_and_path(base_url, "/v1/models"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
    if backend in ("ark", "openai"):
        url = (
            join_base_url_and_path(base_url, "/api/v3/models")
            if backend == "ark"
            else VersionedPath("/models").url(base_url)
        )
        return await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
    return await client.get(
        join_base_url_and_path(base_url, "/v1beta/models"),
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
            join_base_url_and_path(base_url, "/v1/messages"),
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
            join_base_url_and_path(base_url, f"/v1beta/models/{model_id}:generateContent"),
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
            join_base_url_and_path(base_url, "/api/v3/responses"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "."}],
        "max_tokens": max_tokens,
    }
    if effort:
        payload["reasoning_effort"] = effort
    return await client.post(
        VersionedPath("/chat/completions").url(base_url),
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )


# 多模态探测(#11):最小合法 1x1 PNG。只为验证 provider 是否**接受**图像输入
# payload —— 接受(2xx)= 该模型 input_modalities 含 image;不支持 vision 的模型
# 会以 4xx 拒绝图块。不要求模型"看懂"图,只看它收不收(与文本探测"成功=可达"同构)。
_PROBE_TEXT = "Reply with one short word."
_PROBE_IMAGE_MEDIA_TYPE = "image/png"
_PROBE_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


async def _request_official_call_method_generation(
    client: httpx.AsyncClient,
    method_id: OfficialCallMethod,
    api_key: str,
    base_url: str,
    model_id: str,
    *,
    runtime_settings: Mapping[str, Any] | None = None,
    multimodal: bool = False,
) -> httpx.Response:
    """Send one probe generation in the wire language that call method speaks.

    The dialect renders the request and this function only sends it: what a
    provider's payload looks like is decided in one place rather than once per
    probe, which is what lets a probe result say anything about a real call.
    """

    request = dialect_for_method(method_id).generation(
        base_url=apply_call_method_base_url(method_id, base_url),
        secret=api_key,
        model_id=model_id,
        prompt=_probe_prompt(multimodal),
        max_output_tokens=_runtime_max_output_tokens(runtime_settings, default=16),
        reasoning=Reasoning.from_runtime_settings(runtime_settings),
    )
    return await client.post(
        request.url,
        headers=request.headers,
        params=request.params,
        json=request.body,
    )


def _probe_prompt(multimodal: bool) -> Prompt:
    return Prompt(
        text=_PROBE_TEXT,
        image=(
            Image(media_type=_PROBE_IMAGE_MEDIA_TYPE, base64_data=_PROBE_IMAGE_BASE64)
            if multimodal
            else None
        ),
    )


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


# `_request_model_generation` picks a wire from the backend name rather than from
# a call method, so it cannot ask a dialect what to send and still renders these
# two blocks itself. They are the dialects' rules written a second time, and they
# go when that probe starts naming the call method it is testing.
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


def _official_method_backend(method_id: OfficialCallMethod) -> ProviderProbeBackend:
    return provider_backend_for_method(method_id)




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
    "probe_wire_backend",
    "probe_provider_endpoint",
    "probe_provider_route",
]
