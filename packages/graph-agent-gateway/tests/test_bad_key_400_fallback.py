"""Google reports a rejected key as HTTP 400 INVALID_ARGUMENT, not 401.

Same story as `test_credit_exhausted_400_fallback.py` one field over: the
design's own rule is that a credential failure is fallback-eligible with
credential scope (`docs/graph-agent-gateway/mvp1/06-orch-error-classification/
mvp1-alignment.md`, "401/402/403 → fallback（credential scope）"), and the
classifier honoured it only for providers that use the conventional status
code. A role whose first route is a Gemini one with a dead key therefore failed
the whole request instead of trying the next route in its chain.

Field evidence: live probe 2026-08-12, gemini-official × gemini-3.5-flash.
"""

from __future__ import annotations


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _ProviderError(Exception):
    """The google SDK error shape: .status_code + .response with a JSON body."""

    def __init__(self, message: str, status_code: int, payload: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        if payload is not None:
            self.response = _FakeResponse(payload)


_GOOGLE_BAD_KEY_PAYLOAD = {
    "error": {
        "code": 400,
        "message": "API key not valid. Please pass a valid API key.",
        "status": "INVALID_ARGUMENT",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                "reason": "API_KEY_INVALID",
                "domain": "googleapis.com",
            }
        ],
    }
}


def test_a_rejected_key_answered_as_400_still_allows_fallback() -> None:
    from graph_agent_gateway.resolve import classify_exception

    result = classify_exception(
        _ProviderError("bad request", 400, _GOOGLE_BAD_KEY_PAYLOAD), route_id="r"
    )

    assert result.decision == "fallback_allowed"
    assert result.action == "fallback_route"
    assert result.scope == "credential"
    assert result.provider_status_code == 400


def test_a_genuinely_malformed_request_still_fails_fast() -> None:
    """The new branch must not swallow the case it sits next to: a 400 that is
    about the request has nothing the next route could do better."""
    from graph_agent_gateway.resolve import classify_exception

    result = classify_exception(
        _ProviderError(
            "bad request",
            400,
            {"error": {"type": "invalid_request_error", "message": "messages: field required"}},
        ),
        route_id="r",
    )

    assert result.action == "fail_request"


def test_the_two_readers_of_a_billing_message_had_drifted_apart() -> None:
    """One condition, two readers, and each carried its own word list.

    "purchase credits" was only in the runtime classifier's copy and "quota
    exceeded" only in the probe judge's, so the same message meant different
    things depending on which one saw it. Both now read one vocabulary, and
    this pins the two words that used to be missing from one side each.
    """
    from graph_agent_gateway.probing import ProviderAnswer, probe_status
    from graph_agent_gateway.resolve import classify_exception

    judge_verdict = probe_status(
        ProviderAnswer(
            status_code=400,
            body='{"error": {"message": "Please purchase credits to continue."}}',
        ),
        model_not_found_status="invalid_model",
    )
    assert judge_verdict == "quota_exceeded"

    runtime_verdict = classify_exception(
        _ProviderError(
            "bad request", 400, {"error": {"message": "Quota exceeded for this project."}}
        ),
        route_id="r",
    )
    assert runtime_verdict.action == "fallback_route"
    assert runtime_verdict.scope == "credential"
