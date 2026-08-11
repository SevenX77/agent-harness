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
