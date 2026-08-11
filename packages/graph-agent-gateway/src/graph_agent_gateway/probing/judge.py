"""What a provider's answer means.

One reading of one response, shared by every probe: a status, and the few
things worth lifting out of the body. Each probe asks its own question, but
they must not each decide separately what a 404 or a 402 means — that is how
one surface reports a dead route and another reports a missing model.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx

from graph_agent_gateway.registry import ProviderProbeBackend

ProviderProbeStatus = Literal[
    "ok",
    "invalid_key",
    "invalid_model",
    "protocol_unsupported",
    "rate_limited",
    "quota_exceeded",
    "network_error",
    "timeout",
    "error",
]


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


# A URL that does not serve the probed protocol at all answers with wrong-path
# signatures instead of a provider-shaped model error. Two observed families
# (design §1.2 protocol matrix, live-verified on qiniu): explicit guidance to the
# correct path ("Use /v1/messages instead", any HTTP status) and bare path-level
# 404/405 text ("not found or method not allowed"). These are protocol-level
# facts about the (URL, protocol) combination — classifying them as
# invalid_model conflates "this URL cannot speak the protocol" with "the model
# id is wrong" and poisons every consumer downstream.
_PROTOCOL_MISMATCH_MARKERS = (
    "use /v1/messages",
    "use /v1/chat/completions",
    "method not allowed",
    # A host with no handler for the probed protocol's path answers with a
    # route-level rejection (live 2026-07-02, anthropic.qnaigc.com × google:
    # GET /v1beta/models -> HTTP 500 "Unsupported fixed route: /v1beta/models").
    "unsupported fixed route",
    "unknown route",
    "route not found",
)


def _has_protocol_mismatch_guidance(response: httpx.Response) -> bool:
    text = response.text.lower()
    return any(marker in text for marker in _PROTOCOL_MISMATCH_MARKERS)


# A host with no backend for the probed protocol may silently MISROUTE the
# request to a different protocol's upstream and surface that upstream's error
# verbatim (live 2026-07-02, anthropic.qnaigc.com × google: the gemini probe
# 500s wrapping "OpenAI API error: 401 invalid api key"). A probe for backend X
# that comes back describing backend Y's API is proof the host does not speak X.
# Each marker maps to the backends for which it is NATIVE — seeing it on any
# OTHER backend is a protocol mismatch, not a transient error or a real auth
# failure on the matching protocol.
_FOREIGN_API_ERROR_SIGNATURES: dict[str, tuple[ProviderProbeBackend, ...]] = {
    "openai api error": ("openai", "deepseek", "ark"),
    "anthropic api error": ("claude",),
    "gemini api error": ("gemini",),
    "google api error": ("gemini",),
}


def _has_foreign_protocol_error(
    response: httpx.Response,
    probed_backend: ProviderProbeBackend,
) -> bool:
    text = response.text.lower()
    return any(
        marker in text and probed_backend not in native_backends
        for marker, native_backends in _FOREIGN_API_ERROR_SIGNATURES.items()
    )


def _is_provider_error_payload(response: httpx.Response) -> bool:
    """True when the body is the protocol's own structured error schema.

    Every supported protocol (openai / anthropic / google / ark) wraps request
    errors in a JSON object with an ``error`` member. A 404 carrying that shape
    proves the protocol handler answered — the failure is about the request
    (model id), not about the URL not speaking the protocol.
    """
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("error") is not None


def probe_status(
    response: httpx.Response,
    *,
    model_not_found_status: Literal["invalid_model", "error"],
    probed_backend: ProviderProbeBackend | None = None,
) -> ProviderProbeStatus:
    code = response.status_code
    if 200 <= code < 300:
        return "ok"
    if code == 405 or _has_protocol_mismatch_guidance(response):
        return "protocol_unsupported"
    if probed_backend is not None and _has_foreign_protocol_error(response, probed_backend):
        # Misrouted to a different protocol's upstream — the (URL, protocol) cell
        # cannot speak the probed protocol. This precedes the 401 branch so a
        # foreign-protocol auth error is not mistaken for THIS key being invalid.
        return "protocol_unsupported"
    if code == 401:
        return "invalid_key"
    if code == 429:
        return "rate_limited"
    if code in (402, 403):
        return "quota_exceeded"
    if code in (400, 404):
        if _is_billing_error(response):
            return "quota_exceeded"
        if code == 404 and not _is_provider_error_payload(response):
            return "protocol_unsupported"
        return model_not_found_status
    return "error"


def model_ids(response: httpx.Response) -> tuple[str, ...]:
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


def model_capabilities(response: httpx.Response) -> dict[str, dict[str, Any]]:
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


def provider_response_message(response: httpx.Response) -> str:
    error_code = vendor_error_code(response, default="")
    vendor_message = _extract_vendor_error_message(response)
    if error_code:
        message = f"Provider returned HTTP {response.status_code} ({error_code})."
    else:
        message = f"Provider returned HTTP {response.status_code}."
    if vendor_message:
        message = f"{message} {vendor_message}"
    return message


def vendor_error_code(response: httpx.Response, *, default: str) -> str:
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
