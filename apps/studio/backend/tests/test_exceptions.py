from __future__ import annotations

import pytest
from app.core.exceptions import (
    STANDARD_ERROR_MAP,
    error_response,
    http_exception_handler,
    standard_http_exception,
    value_error_handler,
)
from fastapi import HTTPException

# Codes only the framework may answer with; a caller naming one is refused. Kept
# as a literal here rather than imported so the test states the expectation
# independently of the module it is checking.
FRAMEWORK_RESERVED = {"INTERNAL_ERROR"}


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
        "INTERNAL_ERROR": 500,
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
    """INTERNAL_ERROR's fixed message is the reason it exists — a caller must not set it.

    Both caller routes into the error map let the caller name a code AND supply
    the text, so a selectable INTERNAL_ERROR would be a way to put arbitrary
    internal text on screen under the one code whose whole point is that its
    message says nothing. Registered, but not caller-selectable.
    """
    with pytest.raises(KeyError):
        standard_http_exception("INTERNAL_ERROR", "a database path with a secret in it")


@pytest.mark.anyio
async def test_the_value_error_prefix_protocol_does_not_honour_internal_error() -> None:
    """The other caller route: `raise ValueError("CODE: text")`.

    The reserved code is not recognized as a code, so it degrades to the same
    MANIFEST_VALIDATION_FAILED any unregistered prefix produces.

    What that does NOT do — and this test says so out loud rather than leaving a
    reader to assume otherwise — is scrub the ValueError's own text. The generic
    fallback puts `str(exc)` in the message, as it does for EVERY ValueError, so
    a caller who writes a secret into one still surfaces it in the 422. That is
    unchanged, pre-existing behaviour of how validation failures are reported;
    the guarantee being added here is narrower and exact: the reserved CODE
    cannot be selected, so nothing can present caller text as a 500
    INTERNAL_ERROR.
    """
    response = await value_error_handler(
        None,  # type: ignore[arg-type]
        ValueError("INTERNAL_ERROR: a database path with a secret in it"),
    )

    assert response.status_code == 422
    assert b'"error_code":"MANIFEST_VALIDATION_FAILED"' in response.body
    assert b"a database path with a secret in it" in response.body


@pytest.mark.anyio
async def test_a_hand_built_internal_error_envelope_cannot_carry_caller_text() -> None:
    """The reserved-code rule is enforced at the way OUT, not only at the ways in.

    Blocking the two code-selection routes leaves others open: a caller can
    hand-build an envelope with `error_response(...)` and raise it, which arrives
    as an `HTTPException` whose detail is already a complete envelope. Every one
    of those still leaves through `_json_response`, so that is where the fixed
    message is imposed.
    """
    smuggled = error_response(
        error_code="INTERNAL_ERROR",
        http_status=500,
        message="a database path with a secret in it",
        details=None,
        retry_strategy="not_retryable",
    )

    response = await http_exception_handler(
        None,  # type: ignore[arg-type]
        HTTPException(status_code=500, detail=smuggled.model_dump()),
    )

    assert response.status_code == 500
    assert b'"message":"Internal server error"' in response.body
    assert b"a database path with a secret in it" not in response.body
