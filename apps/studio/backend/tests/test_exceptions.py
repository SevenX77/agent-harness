from __future__ import annotations

import pytest
from app.core.exceptions import (
    STANDARD_ERROR_MAP,
    standard_http_exception,
    value_error_handler,
)

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

    An unrecognized prefix degrades to MANIFEST_VALIDATION_FAILED, which is the
    pre-existing behaviour for any code not in the caller-facing view — so the
    text is still not presented AS an internal-error message with a 500.
    """
    response = await value_error_handler(
        None,  # type: ignore[arg-type]
        ValueError("INTERNAL_ERROR: a database path with a secret in it"),
    )

    assert response.status_code == 422
    assert b'"error_code":"MANIFEST_VALIDATION_FAILED"' in response.body
