"""The judge reads an answer, not whoever fetched it.

Its whole input is a status code and a body — it never touches anything else a
response object offers. Saying so in the type keeps a second question out of
the judgment: a probe that gets its answer from a provider SDK exception rather
than from a request of its own is answering the same question, and must not
need a second judge to do it.
"""

from __future__ import annotations

from graph_agent_gateway.probing import ProviderAnswer, probe_status


def test_a_billing_message_on_a_four_hundred_is_read_out_of_the_body() -> None:
    answer = ProviderAnswer(
        status_code=400,
        body='{"error": {"message": "Insufficient balance", "type": "invalid_request_error"}}',
    )

    assert probe_status(answer, model_not_found_status="invalid_model") == "quota_exceeded"


def test_a_body_that_is_not_json_still_gets_a_verdict() -> None:
    answer = ProviderAnswer(status_code=404, body="<html>nginx</html>")

    assert probe_status(answer, model_not_found_status="invalid_model") == "protocol_unsupported"


def test_an_answer_is_exactly_what_an_sdk_exception_can_hand_over() -> None:
    """Two fields, and the reason there are only two.

    `openai.APIStatusError` and `anthropic.APIStatusError` are constructed with
    `(message, *, response, body)`, and `google.genai.errors.APIError` with
    `(code, response_json, response, ...)`. A status and a body is the
    intersection — anything more here would be reachable for a probe that makes
    its own request and missing for one that reads a failed production call.
    """

    from dataclasses import FrozenInstanceError, fields

    assert [f.name for f in fields(ProviderAnswer)] == ["status_code", "body"]

    answer = ProviderAnswer(status_code=200, body="{}")
    try:
        answer.status_code = 500  # type: ignore[misc]
    except FrozenInstanceError:
        pass
    else:  # pragma: no cover - the assignment above must raise
        raise AssertionError("an answer already given must not be editable")


def test_a_rejected_probe_payload_is_not_a_verdict_about_the_model() -> None:
    """Ark refuses the 1x1 probe image for its size, not for being an image.

    Live 2026-08-11, ark-official × doubao-seed-2-0-pro-260215:
    HTTP 400 InvalidParameter, "Image dimensions are too small. Minimum allowed
    dimension: 14 pixels. Current dimensions: width = 1, height = 1."
    Calling that invalid_model says the model does not take images, which is a
    claim this answer does not support — the provider rejected OUR request.
    Same family as the billing and protocol-mismatch cases above.
    """
    answer = ProviderAnswer(
        status_code=400,
        body=(
            '{"error": {"code": "InvalidParameter", "message": '
            '"Image 0 failed: Image dimensions are too small. '
            'Minimum allowed dimension: 14 pixels. '
            'Current dimensions: width = 1, height = 1."}}'
        ),
    )

    assert probe_status(answer, model_not_found_status="invalid_model") == "error"


def test_the_probe_image_clears_the_smallest_dimension_a_provider_demands() -> None:
    """The probe image is a payload we control; it must not be the reason a
    probe fails. Ark's floor is 14 pixels (live 2026-08-11)."""
    import base64
    import struct

    from graph_agent_gateway.probing import wire

    png = base64.b64decode(wire._PROBE_IMAGE_BASE64)
    width, height = struct.unpack(">II", png[16:24])

    assert width >= 16 and height >= 16, f"probe image is {width}x{height}"


def test_a_model_that_says_it_only_takes_text_is_answering_the_question() -> None:
    """Ark's answer is about the model's modalities, and it is a definite no.

    Live 2026-08-11T19:00:42Z, ark-official route of the DeepSeek V4 Flash
    group: HTTP 400 InvalidParameter, "Model only support text input". The
    model is there and its text calls work — the route's status is `verified`
    to this day. Reading that as invalid_model records "there is no such model"
    from an answer that names the model's capability, and that record is
    shareable evidence.

    The mirror of `INCONCLUSIVE_PROBE_STATUSES`: that set stops "we could not
    ask" from passing as "the answer was no", and this stops "the answer was
    no" from passing as "the model is broken".
    """
    answer = ProviderAnswer(
        status_code=400,
        body='{"error": {"code": "InvalidParameter", "message": "Model only support text input"}}',
    )

    assert probe_status(answer, model_not_found_status="invalid_model") == "capability_unsupported"


def test_a_model_id_that_does_not_exist_is_still_invalid_model() -> None:
    """The new member must not swallow the case it sits next to."""
    answer = ProviderAnswer(
        status_code=404,
        body='{"error": {"message": "The model `gpt-nonexistent` does not exist", "type": "invalid_request_error"}}',
    )

    assert probe_status(answer, model_not_found_status="invalid_model") == "invalid_model"


def test_a_refusal_of_the_capability_asked_is_a_fact_about_the_route() -> None:
    """So it must not be read as an answer about the moment.

    A batch of questions is voided by an inconclusive answer, because a rate
    limit deletes nothing. A definite "it does not support this" deletes
    exactly one thing, on purpose — it belongs on the conclusive side.
    """
    from graph_agent_gateway.probing import INCONCLUSIVE_PROBE_STATUSES

    assert "capability_unsupported" not in INCONCLUSIVE_PROBE_STATUSES


GOOGLE_INVALID_KEY_BODY = """
{
  "error": {
    "code": 400,
    "message": "API key not valid. Please pass a valid API key.",
    "status": "INVALID_ARGUMENT",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "API_KEY_INVALID",
        "domain": "googleapis.com",
        "metadata": {"service": "generativelanguage.googleapis.com"}
      },
      {
        "@type": "type.googleapis.com/google.rpc.LocalizedMessage",
        "locale": "en-US",
        "message": "API key not valid. Please pass a valid API key."
      }
    ]
  }
}
"""
"""Google's answer to a bad key, captured verbatim.

Live 2026-08-12, gemini-official × gemini-3.5-flash, POST
`/v1beta/models/gemini-3.5-flash:generateContent`. Note the HTTP code: 400,
not the 401 every other configured provider uses for the same situation
(deepseek-official the same day: HTTP 401 "Authentication Fails").
"""


def test_a_bad_key_answered_as_four_hundred_is_still_a_bad_key() -> None:
    """The status convention is the provider's choice; the meaning is not.

    Before this, Google's answer fell through to `model_not_found_status` and
    a Gemini route probed with a bad key was recorded as invalid_model — "there
    is no such model" — from an answer that names the key. Same species as the
    billing table: an endpoint-wide account failure that arrives as HTTP 400
    must not be filed as a model-level verdict.
    """
    answer = ProviderAnswer(status_code=400, body=GOOGLE_INVALID_KEY_BODY)

    assert probe_status(answer, model_not_found_status="invalid_model") == "invalid_key"


def test_the_endpoint_probe_reads_a_bad_key_the_same_way() -> None:
    """The endpoint probe passes `model_not_found_status="error"`, so before
    this the same body produced a bare `error` there and `invalid_model` on the
    route probe — two names for one situation, neither of them the true one."""
    answer = ProviderAnswer(status_code=400, body=GOOGLE_INVALID_KEY_BODY)

    assert probe_status(answer, model_not_found_status="error") == "invalid_key"


def test_a_bad_key_is_read_from_the_machine_readable_reason_too() -> None:
    """`error.message` is prose for a human; `details[].reason` is Google's
    own identifier for the condition (`google.rpc.ErrorInfo`). Matching the
    identifier is what keeps the verdict from depending on wording we do not
    control — the message here is deliberately one no marker matches."""
    answer = ProviderAnswer(
        status_code=400,
        body=(
            '{"error": {"code": 400, "message": "\\u8bf7\\u6c42\\u53c2\\u6570\\u6709\\u8bef",'
            ' "status": "INVALID_ARGUMENT", "details": [{"@type":'
            ' "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}]}}'
        ),
    )

    assert probe_status(answer, model_not_found_status="invalid_model") == "invalid_key"


def test_a_bad_key_is_never_read_as_an_answer_about_the_route() -> None:
    """Which is the second half of the damage this fixes.

    `invalid_model` is conclusive, so a capability batch that hit a bad key was
    read as "these are the values the route sells". `invalid_key` is in the
    inconclusive set, so the same batch is voided instead.
    """
    from graph_agent_gateway.probing import INCONCLUSIVE_PROBE_STATUSES

    assert "invalid_key" in INCONCLUSIVE_PROBE_STATUSES
