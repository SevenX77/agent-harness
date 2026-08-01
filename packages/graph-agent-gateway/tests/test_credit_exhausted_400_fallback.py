"""Anthropic reports account-credit exhaustion as HTTP 400 invalid_request_error,
not 402 — semantically it is an endpoint-level billing failure that the next
route in the fallback chain (a different account/provider) can absorb. The
classifier must not lump it in with genuine malformed-request 400s.

Field evidence: run 2026-08-01T07-12-52 (skill exp-a-round1) crashed after a
single probe_fail on anthropic-official although the role had four enabled
fallback routes.
"""

from __future__ import annotations


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _ProviderError(Exception):
    """Mirrors the anthropic SDK error shape: .status_code + .response with a JSON body."""

    def __init__(self, message: str, status_code: int, payload: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        if payload is not None:
            self.response = _FakeResponse(payload)


_ANTHROPIC_CREDIT_PAYLOAD = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": (
            "Your credit balance is too low to access the Anthropic API. "
            "Please go to Plans & Billing to upgrade or purchase credits."
        ),
    },
}


def test_credit_exhausted_400_allows_fallback() -> None:
    from graph_agent_gateway.registry.error_classification import classify_exception

    result = classify_exception(
        _ProviderError("bad request", 400, _ANTHROPIC_CREDIT_PAYLOAD), route_id="r"
    )

    assert result.decision == "fallback_allowed"
    assert result.action == "fallback_route"
    assert result.scope == "credential"
    assert result.provider_status_code == 400


def test_plain_bad_request_400_still_fails_fast() -> None:
    from graph_agent_gateway.registry.error_classification import classify_exception

    result = classify_exception(
        _ProviderError("Error code: 400 - malformed request body", 400), route_id="r"
    )

    assert result.action == "fail_request"
    assert result.decision == "fail_fast"
