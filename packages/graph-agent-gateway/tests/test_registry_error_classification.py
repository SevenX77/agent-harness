"""Gateway registry error classification tests."""

from __future__ import annotations

import httpx


def test_network_timeout_and_retryable_provider_errors_allow_fallback() -> None:
    from graph_agent_gateway.registry.error_classification import classify_exception

    assert classify_exception(httpx.ConnectError("dns"), route_id="r").decision == (
        "fallback_allowed"
    )
    assert classify_exception(httpx.TimeoutException("slow"), route_id="r").decision == (
        "fallback_allowed"
    )

    response = httpx.Response(503, request=httpx.Request("POST", "https://example.test"))
    assert classify_exception(httpx.HTTPStatusError("bad", request=response.request, response=response)).decision == (
        "fallback_allowed"
    )


def test_auth_bad_request_and_unknown_errors_fail_fast() -> None:
    from graph_agent_gateway.registry.error_classification import classify_exception

    response = httpx.Response(401, request=httpx.Request("POST", "https://example.test"))
    auth = classify_exception(
        httpx.HTTPStatusError("unauthorized", request=response.request, response=response),
        route_id="r",
    )
    assert auth.decision == "fail_fast"
    assert auth.provider_status_code == 401

    unknown = classify_exception(RuntimeError("boom"), route_id="r")
    assert unknown.decision == "fail_fast_with_route_context"
    assert unknown.unclassified_default is True
