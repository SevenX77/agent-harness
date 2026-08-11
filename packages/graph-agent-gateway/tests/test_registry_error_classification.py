"""Gateway registry error classification tests."""

from __future__ import annotations

import httpx


def test_network_timeout_and_retryable_provider_errors_allow_fallback() -> None:
    from graph_agent_gateway.resolve import classify_exception

    connect = classify_exception(httpx.ConnectError("dns"), route_id="r")
    timeout = classify_exception(httpx.TimeoutException("slow"), route_id="r")

    assert connect.decision == "fallback_allowed"
    assert connect.action == "retry_same_route"
    assert timeout.decision == "fallback_allowed"
    assert timeout.action == "retry_same_route"

    response = httpx.Response(503, request=httpx.Request("POST", "https://example.test"))
    result = classify_exception(httpx.HTTPStatusError("bad", request=response.request, response=response))
    assert result.decision == "fallback_allowed"
    assert result.action == "retry_same_route"


def test_endpoint_scoped_errors_allow_fallback_but_bad_requests_fail() -> None:
    from graph_agent_gateway.resolve import classify_exception

    response = httpx.Response(401, request=httpx.Request("POST", "https://example.test"))
    auth = classify_exception(
        httpx.HTTPStatusError("unauthorized", request=response.request, response=response),
        route_id="r",
    )
    assert auth.decision == "fallback_allowed"
    assert auth.action == "fallback_route"
    assert auth.scope == "credential"
    assert auth.provider_status_code == 401

    payment = httpx.Response(402, request=httpx.Request("POST", "https://example.test"))
    assert classify_exception(
        httpx.HTTPStatusError("billing", request=payment.request, response=payment),
        route_id="r",
    ).decision == "fallback_allowed"

    too_large = httpx.Response(413, request=httpx.Request("POST", "https://example.test"))
    request_too_large = classify_exception(
        httpx.HTTPStatusError("large", request=too_large.request, response=too_large),
        route_id="r",
    )
    assert request_too_large.decision == "fail_fast"
    assert request_too_large.action == "fail_request"

    unknown = classify_exception(RuntimeError("boom"), route_id="r")
    assert unknown.decision == "fail_fast_with_route_context"
    assert unknown.unclassified_default is True


def test_provider_sdk_status_code_attribute_is_classified() -> None:
    from graph_agent_gateway.resolve import classify_exception

    class ProviderStatusError(RuntimeError):
        status_code = 404

    result = classify_exception(ProviderStatusError("model not found"), route_id="r")

    assert result.decision == "fallback_allowed"
    assert result.action == "fallback_route"
    assert result.scope == "route"
    assert result.provider_status_code == 404


def test_wrapped_network_error_allows_fallback() -> None:
    from graph_agent_gateway.resolve import classify_exception

    try:
        raise RuntimeError("Connection error.") from httpx.ConnectError("connection refused")
    except RuntimeError as exc:
        result = classify_exception(exc, route_id="r")

    assert result.decision == "fallback_allowed"


def test_error_context_classifies_stream_and_unsupported_parameter() -> None:
    from graph_agent_gateway.resolve import (
        ErrorContext,
        classify_error_context,
    )

    stream = classify_error_context(
        RuntimeError("stream broke"),
        ErrorContext(route_id="r", stream_phase="after_200_sse"),
    )
    assert stream.action == "fallback_route"
    assert stream.scope == "stream"

    response = httpx.Response(
        400,
        json={"error": {"type": "invalid_request_error", "message": "unsupported parameter"}},
        request=httpx.Request("POST", "https://example.test"),
    )
    unsupported = classify_error_context(
        httpx.HTTPStatusError("bad", request=response.request, response=response),
        ErrorContext(route_id="r", endpoint_id="e"),
    )
    assert unsupported.action == "fallback_route"
    assert unsupported.scope == "route"
