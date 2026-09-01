from __future__ import annotations

import pytest
from app.core.exceptions import (
    STANDARD_ERROR_MAP,
    error_response,
    http_exception_handler,
    standard_http_exception,
    value_error_handler,
)
from app.models.errors import ErrorResponse
from fastapi import HTTPException

# Codes only the framework may answer with; a caller naming one is refused. Kept
# as a literal here rather than imported so the test states the expectation
# independently of the module it is checking.
FRAMEWORK_RESERVED = {"STUDIO_INTERNAL_ERROR"}


def test_standard_error_codes_map_to_http_exceptions() -> None:
    expected = {
        "SKILL_NOT_FOUND": 404,
        "SKILL_ALREADY_EXISTS": 409,
        "MANIFEST_VALIDATION_FAILED": 422,
        "COMPILE_FAILED": 200,
        "RUN_SPAWN_FAILED": 500,
        "TERMINAL_SPAWN_FAILED": 500,
        "TERMINAL_LIMIT_REACHED": 503,
        "WEBSOCKET_DISCONNECTED": 499,
        "LLM_FALLBACK_EXHAUSTED": 502,
        "LLM_CREDENTIALS_SCHEMA": 422,
        "RESUME_CHECKPOINT_NOT_FOUND": 404,
        "RESUME_VALIDITY_FAILED": 422,
        "TEST_INPUT_NOT_FOUND": 404,
        "TEST_INPUT_ALREADY_EXISTS": 409,
        "TEST_INPUT_VALIDATION_FAILED": 422,
        "SUBGRAPH_PATH_INVALID": 422,
        "SUBGRAPH_PATH_NOT_FOUND": 404,
        "RUN_REQUIRES_PREDICT": 409,
        "RUN_NOT_RUNNING": 409,
        "RUN_NOT_CONCLUDED": 409,
        "STUDIO_INTERNAL_ERROR": 500,
    }

    assert set(STANDARD_ERROR_MAP) == set(expected)
    for error_code, http_status in expected.items():
        if error_code in FRAMEWORK_RESERVED:
            continue
        exc = standard_http_exception(error_code, "message")
        assert exc.status_code == http_status
        assert exc.detail["error_code"] == error_code
        assert exc.detail["http_status"] == http_status


def test_resume_validity_failed_is_not_retryable() -> None:
    assert STANDARD_ERROR_MAP["RESUME_VALIDITY_FAILED"].retry_strategy == "not_retryable"


def test_unregistered_error_code_fails_loudly_instead_of_slipping_through() -> None:
    """An unregistered code must raise at construction, never produce a malformed response."""
    with pytest.raises(KeyError):
        standard_http_exception("DEFINITELY_NOT_REGISTERED", "message")


def test_a_caller_cannot_select_the_frameworks_internal_error_code() -> None:
    """STUDIO_INTERNAL_ERROR's fixed message is the reason it exists — a caller must not set it.

    Both caller routes into the error map let the caller name a code AND supply
    the text, so a selectable STUDIO_INTERNAL_ERROR would be a way to put arbitrary
    internal text on screen under the one code whose whole point is that its
    message says nothing. Registered, but not caller-selectable.
    """
    with pytest.raises(KeyError):
        standard_http_exception("STUDIO_INTERNAL_ERROR", "a database path with a secret in it")


@pytest.mark.anyio
async def test_the_value_error_prefix_protocol_does_not_honour_internal_error() -> None:
    """The other caller route: `raise ValueError("CODE: text")`.

    The reserved code is not recognized as a code, so it degrades to the same
    MANIFEST_VALIDATION_FAILED any unregistered prefix produces.

    The second assertion records a PRE-EXISTING DEFECT, not a desired property,
    and is written down so the boundary of this change cannot be misread. The
    global ValueError handler puts `str(exc)` into a 422 for every unclaimed
    ValueError, so a programming bug anywhere that raises one — a parse failure
    deep in a library, say — surfaces its internal text to the UI as though the
    user had sent bad input, never reaching the 500 middleware or its log. Fixing
    that means giving boundary validation its own exception type and letting
    unknown ValueErrors propagate, which changes the response of many endpoints
    and is a decision of its own, not a rider on this one.

    What IS guaranteed here is exact and narrow: the reserved CODE cannot be
    selected, so no caller text can be presented as a 500 STUDIO_INTERNAL_ERROR.
    """
    response = await value_error_handler(
        None,  # type: ignore[arg-type]
        ValueError("STUDIO_INTERNAL_ERROR: a database path with a secret in it"),
    )

    assert response.status_code == 422
    assert b'"error_code":"MANIFEST_VALIDATION_FAILED"' in response.body
    # Nothing here asserts what happens to the caller's TEXT. Today it is echoed,
    # and that is the leak described above — pinning it with an assertion would
    # turn a defect into a promise, and would put this test in the way of the
    # change that fixes it.


def test_the_envelope_builder_refuses_the_frameworks_own_code() -> None:
    """The rule is enforced where the envelope is BUILT, not only where it exits.

    Projection-time normalization is not enough on its own, because not every
    envelope goes through a handler: a router may `return error_response(...)`
    from an endpoint and FastAPI serializes it directly. So the builder refuses
    the code, which makes the envelope impossible to have rather than harmless to
    have.
    """
    with pytest.raises(ValueError, match="STUDIO_INTERNAL_ERROR"):
        error_response(
            error_code="STUDIO_INTERNAL_ERROR",
            http_status=200,
            message="a database path with a secret in it",
            retry_strategy="idempotent",
        )


@pytest.mark.anyio
async def test_a_hand_built_internal_error_envelope_cannot_carry_caller_text() -> None:
    """And the way out normalizes one that skipped the builder entirely.

    Constructing `ErrorResponse` directly goes around `error_response` and its
    refusal above — nothing can stop that, since it is the shared model every
    envelope is made of. What can be stopped is such an envelope REACHING a
    reader, which is what `_json_response` does for anything leaving through
    this module's handlers.
    """
    # Every field is forged, not just the message, because normalizing one would
    # leave the others: `http_status=200` is read as SUCCESS by axios, `details`
    # is rendered verbatim by the frontend's diagnostic view, and
    # `retry_strategy` would invite repeating a possibly half-applied write.
    smuggled = ErrorResponse(
        error_code="STUDIO_INTERNAL_ERROR",
        http_status=200,
        message="a database path with a secret in it",
        details={"token": "another secret"},
        retry_strategy="idempotent",
    )

    response = await http_exception_handler(
        None,  # type: ignore[arg-type]
        HTTPException(status_code=200, detail=smuggled.model_dump()),
    )

    assert response.status_code == 500
    assert b'"message":"Internal server error"' in response.body
    assert b'"retry_strategy":"not_retryable"' in response.body
    assert b'"details":null' in response.body
    assert b"secret" not in response.body
