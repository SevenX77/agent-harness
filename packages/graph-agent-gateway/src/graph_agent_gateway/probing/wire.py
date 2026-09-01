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

import httpx
from langchain_core.messages import HumanMessage
from pydantic import SecretStr

from graph_agent_gateway.call import RouteChatModelFactory
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
    ResolvedRoute,
    RuntimeSettings,
    apply_call_method_base_url,
    call_method_is_officially_probeable,
    provider_backend_for_endpoint,
    provider_backend_for_method,
    provider_backend_for_protocol,
    wire_backend_for_method,
)

from .judge import (
    ProviderAnswer,
    ProviderProbeStatus,
    answer_from_failed_call,
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

    backend = provider_backend_for_endpoint(endpoint)
    wire = provider_backend_for_protocol(endpoint.protocol)
    base_url = endpoint_probe_base_url(endpoint)
    secret = route_probe_secret(endpoint, api_key)
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
            answer = _answer_from(await _request_models(client, wire, secret, base_url))
    except httpx.TimeoutException:
        return _endpoint_result(endpoint, backend, base_url, "timeout", started, message="Endpoint test timed out.")
    except httpx.HTTPError as exc:
        return _endpoint_result(endpoint, backend, base_url, "network_error", started, message=str(exc))

    status = probe_status(answer, model_not_found_status="error", probed_backend=wire)
    return EndpointProbeResult(
        endpoint_id=endpoint.endpoint_id,
        provider_kind=endpoint.provider_kind,
        backend=backend,
        base_url=base_url,
        status=status,
        latency_ms=probe_elapsed_ms(started),
        model_ids=model_ids(answer) if status == "ok" else (),
        model_capabilities=model_capabilities(answer) if status == "ok" else {},
        message=None if status == "ok" else provider_response_message(answer),
        error_code=(
            None
            if status == "ok"
            # The classification is authoritative for a protocol mismatch — a
            # misroute/route-rejection body often carries the FOREIGN upstream's
            # vendor code, which must not leak past the classification the gate
            # and UI key off.
            else "protocol_unsupported"
            if status == "protocol_unsupported"
            else vendor_error_code(answer, default=status)
        ),
    )


async def probe_provider_route(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    *,
    api_key: str | None = None,
    runtime_settings: Mapping[str, Any] | None = None,
    factory: Any | None = None,
    timeout: float = 15.0,
) -> RouteProbeResult:
    """Ask this route the cheapest real question there is: one token.

    The model is built the way a run builds it, because the answer is only
    worth having if the request was the one a run would send. The builder can
    be handed in — the same seam `call/pre_call_probe.py` uses — so a test can
    replay the wire without this function knowing which client it is talking to.
    """

    wire = provider_backend_for_protocol(endpoint.protocol)
    identity = route_probe_identity(endpoint, route)
    base_url = endpoint_probe_base_url(endpoint)
    backend = identity["backend"]
    if not base_url:
        return RouteProbeResult(**identity, status="error", message="Base URL is empty.")
    if not route_probe_secret(endpoint, api_key):
        return RouteProbeResult(**identity, status="invalid_key", message="API key is empty.")

    started = time.perf_counter()
    model = route_probe_model(
        endpoint,
        route,
        api_key=api_key,
        runtime_settings=runtime_settings,
        factory=factory,
        timeout=timeout,
        max_tokens=1,
    )
    try:
        await model.ainvoke([HumanMessage(content="ping")])
    except BaseException as exc:  # noqa: BLE001 - every failure is an answer about the route
        answer = answer_from_failed_call(exc)
        if answer is None:
            return _route_result(
                endpoint,
                route,
                backend,
                base_url,
                _status_without_an_answer(exc),
                started,
                message=str(exc),
            )
    else:
        return _route_result(endpoint, route, backend, base_url, "ok", started)

    status = probe_status(answer, model_not_found_status="invalid_model", probed_backend=wire)
    return RouteProbeResult(
        **identity,
        status=status,
        latency_ms=probe_elapsed_ms(started),
        message=None if status == "ok" else provider_response_message(answer),
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
            answer = _answer_from(
                await _request_official_call_method_generation(
                    client,
                    method_id,
                    api_key,
                    normalized_base_url,
                    model_id,
                    runtime_settings=runtime_settings,
                    multimodal=multimodal,
                )
            )
    except httpx.TimeoutException:
        status: ProviderProbeStatus = "timeout"
        message = None
        latency_ms = None
    except httpx.HTTPError as exc:
        status = "network_error"
        message = str(exc)
        latency_ms = probe_elapsed_ms(started)
    else:
        status = probe_status(
            answer,
            model_not_found_status="invalid_model",
            # The WIRE this probe spoke. It enables exactly one correction in
            # `probe_status`: an ERROR body that names another protocol's API in so
            # many words ("OpenAI API error: ...", see
            # `_FOREIGN_API_ERROR_SIGNATURES`) is a misroute rather than a failure
            # on this wire. That is a narrow signature check, not general
            # misroute detection — a 2xx is still taken at face value. Omitting the
            # argument turns even that off silently, and a misrouted 401 then reads
            # as "your key is invalid".
            #
            # The wire, not the vendor: `ark_anthropic_messages` and
            # `deepseek_anthropic_messages` belong to Ark and DeepSeek but speak
            # Anthropic's wire, and an OpenAI-shaped error IS native to Ark and
            # DeepSeek — passing the vendor there would keep exactly the misroutes
            # this argument exists to catch looking native. The sibling channels
            # pass a wire-derived backend for the same reason
            # (`provider_backend_for_protocol` deliberately consults no host).
            probed_backend=_official_method_wire(method_id),
        )
        message = None if status == "ok" else provider_response_message(answer)
        latency_ms = probe_elapsed_ms(started)

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


class _OneKeyCredentials:
    """The key this probe was handed, in the shape a factory asks for.

    A probe is given a secret directly — it is testing a key the user just
    typed as often as one already stored. The factory resolves keys through a
    provider, so the secret is presented as one, rather than teaching the
    factory a second way to be given a key.
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def get(self, ref: str) -> SecretStr:
        del ref
        return SecretStr(self._secret)


def _production_factory(secret: str) -> RouteChatModelFactory:
    return RouteChatModelFactory(credential_provider=_OneKeyCredentials(secret))


def _route_as_a_run_would_resolve_it(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    runtime_settings: Mapping[str, Any] | None,
) -> ResolvedRoute:
    """The route the factory would be handed if this probe were a run.

    A probe is often asked about a pairing that no stored route describes yet —
    "can this endpoint run this model" — so the object is assembled here rather
    than looked up. That is not a pretence: it is exactly the route a run would
    resolve to if the user saved this pairing and used it.
    """

    return ResolvedRoute(
        role_name="probe",
        route_id=route.route_id,
        endpoint_id=endpoint.endpoint_id,
        protocol=endpoint.protocol,
        base_url=endpoint.base_url,
        credential_ref=endpoint.credential_ref or f"endpoint:{endpoint.endpoint_id}",
        credential_fingerprint="probe",
        timeout_seconds=endpoint.timeout_seconds,
        trust_env=endpoint.trust_env,
        proxy_env=endpoint.proxy_env,
        provider_model_id=route.provider_model_id,
        canonical_id=route.provider_model_id,
        capabilities=dict(route.capabilities),
        runtime_settings=RuntimeSettings.model_validate(dict(runtime_settings or {})),
    )


def _status_without_an_answer(exc: BaseException) -> ProviderProbeStatus:
    """What to report when the provider never answered at all.

    Timeouts are named separately from other connection failures because they
    are the one failure a user can act on by waiting or raising the limit.
    """

    if isinstance(exc, TimeoutError | httpx.TimeoutException):
        return "timeout"
    return "network_error"


def _answer_from(response: httpx.Response) -> ProviderAnswer:
    """The only place a response object becomes something the judge reads."""

    return ProviderAnswer(status_code=response.status_code, body=response.text)


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
        # The name a real call uses for it — see tests/test_production_wire_contract.py.
        "max_completion_tokens": max_tokens,
    }
    if effort:
        payload["reasoning_effort"] = effort
    return await client.post(
        VersionedPath("/chat/completions").url(base_url),
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )


# 多模态探测(#11):一张 16x16 的纯色 PNG。只为验证 provider 是否**接受**图像输入
# payload —— 接受(2xx)= 该模型 input_modalities 含 image。不要求模型"看懂"图,
# 只看它收不收(与文本探测"成功=可达"同构)。
#
# 为什么不是"最小合法"的 1x1:provider 对图像 payload 另有自己的下限,1x1 会因为
# 尺寸被拒,而那次拒绝跟"认不认图"无关。实测 2026-08-11,Ark 对 1x1 回
# HTTP 400 InvalidParameter "Minimum allowed dimension: 14 pixels"。16 是留了余量
# 的整数档;探测自己的 payload 不该成为探测失败的原因。
_PROBE_TEXT = "Reply with one short word."
_PROBE_IMAGE_MEDIA_TYPE = "image/png"
_PROBE_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAEElEQVR42m"
    "NgGAWjYBTAAAADEAAB1y2EYwAAAABJRU5ErkJggg=="
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


def route_probe_secret(endpoint: ProviderEndpoint, api_key: str | None) -> str:
    """The key this probe will send: the one handed in, else the endpoint's own.

    A probe is as often testing a key the user just typed as one already stored,
    so a key given directly outranks the stored one — including an explicit
    empty string, which is a user saying "try it with nothing" and must be
    refused rather than silently swapped for the saved key.
    """
    if api_key is not None:
        return api_key
    if endpoint.api_key is None:
        return ""
    return endpoint.api_key.get_secret_value()


def route_probe_identity(endpoint: ProviderEndpoint, route: ProviderRoute) -> dict[str, Any]:
    """Which route a result is about, in the fields every route result carries.

    Assembled in one place because a probe result whose identity fields are
    filled in per call site can drift — and a measurement recorded against the
    wrong route is worse than no measurement, since nothing about it looks wrong
    later.
    """
    return {
        "endpoint_id": endpoint.endpoint_id,
        "route_id": route.route_id,
        "provider_kind": endpoint.provider_kind,
        "backend": provider_backend_for_endpoint(endpoint),
        "base_url": endpoint_probe_base_url(endpoint),
        "model_id": route.provider_model_id,
    }


def route_probe_model(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    *,
    api_key: str | None,
    runtime_settings: Mapping[str, Any] | None,
    factory: Any | None,
    timeout: float,
    max_tokens: int,
) -> Any:
    """The chat model a probe asks, built the way a run builds one.

    One home for the whole seam — which factory, which resolved route, which
    limits — so that every probe asking a route something is asking the same
    route object through the same builder. Two probes assembling it separately
    would be free to disagree about what "this route" means, and then their
    answers would not be about the same thing.
    """
    builder = factory or _production_factory(route_probe_secret(endpoint, api_key))
    return builder.build(
        _route_as_a_run_would_resolve_it(endpoint, route, runtime_settings),
        timeout_seconds=timeout,
        max_tokens=max_tokens,
    )


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
        latency_ms=probe_elapsed_ms(started),
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
        latency_ms=probe_elapsed_ms(started),
        message=message,
    )


def probe_elapsed_ms(started: float) -> int:
    """How long an attempt took, floored at zero so a clock hiccup is not evidence."""
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


def _official_method_wire(method_id: OfficialCallMethod) -> ProviderProbeBackend:
    return wire_backend_for_method(method_id)




__all__ = [
    "EndpointProbeResult",
    "OfficialCallMethod",
    "ProviderProbeBackend",
    "ProviderProbeStatus",
    "RouteProbeResult",
    "endpoint_probe_base_url",
    "probe_official_call_method",
    "probe_provider_endpoint",
    "probe_provider_route",
]
