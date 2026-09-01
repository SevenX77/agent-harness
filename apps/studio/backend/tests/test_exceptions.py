from __future__ import annotations

import pytest
from app.core.exceptions import (
    STANDARD_ERROR_MAP,
    BoundaryValidationError,
    boundary_validation_error_handler,
    error_response,
    http_exception_handler,
    standard_http_exception,
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


def test_a_boundary_rejection_cannot_name_the_frameworks_internal_error_code() -> None:
    """The second caller route into the error map, refused the same way.

    `BoundaryValidationError` also lets a caller name a code AND supply the text,
    so it needs the same refusal `standard_http_exception` gets above — otherwise
    a raise site could put arbitrary internal text on screen under the one code
    whose whole point is that its message says nothing.

    This replaced a string-prefix protocol: the global `ValueError` handler read
    `str(exc)` for a `"CODE: text"` shape, which meant the reserved code was
    refused only because it was not RECOGNIZED, and the text came out anyway
    inside the MANIFEST_VALIDATION_FAILED it degraded to. Refusal at construction
    has no such degraded path.
    """
    with pytest.raises(KeyError):
        BoundaryValidationError(
            "a database path with a secret in it",
            error_code="STUDIO_INTERNAL_ERROR",
        )


def test_a_boundary_rejection_cannot_name_an_unregistered_code() -> None:
    """An unregistered code has no HTTP projection, so it cannot be answered."""
    with pytest.raises(KeyError):
        BoundaryValidationError("message", error_code="DEFINITELY_NOT_REGISTERED")


@pytest.mark.anyio
async def test_a_boundary_rejection_answers_with_its_own_message() -> None:
    """The message reaches the caller BY CONSTRUCTION, not by inspection.

    The whole point of the type: a raise site that has something the caller needs
    to read says so by choosing this class, and the handler does not parse,
    filter or guess at the text. A bare `ValueError` gets none of this — it is
    unclaimed, and answered as STUDIO_INTERNAL_ERROR by the middleware.
    """
    response = await boundary_validation_error_handler(
        None,  # type: ignore[arg-type]
        BoundaryValidationError("Invalid skill_id: ../evil"),
    )

    assert response.status_code == 422
    assert b'"error_code":"MANIFEST_VALIDATION_FAILED"' in response.body
    assert b"Invalid skill_id: ../evil" in response.body


@pytest.mark.anyio
async def test_a_boundary_rejection_projects_its_chosen_codes_status_and_details() -> None:
    """A named code brings its whole HTTP projection, not just a label.

    `http_status` and `retry_strategy` come from the one registry of code
    projections, so a raise site cannot pair a code with a status that
    contradicts it. `details` is the raiser's, which is how the credentials
    loader hands the reader the document explaining the schema it just refused.
    """
    response = await boundary_validation_error_handler(
        None,  # type: ignore[arg-type]
        BoundaryValidationError(
            "invalid v5 llm credentials schema",
            error_code="LLM_CREDENTIALS_SCHEMA",
            details={"docs_path": "docs/development/CREDENTIALS_V4_BOOTSTRAP.md"},
        ),
    )

    assert response.status_code == STANDARD_ERROR_MAP["LLM_CREDENTIALS_SCHEMA"].http_status
    assert b'"error_code":"LLM_CREDENTIALS_SCHEMA"' in response.body
    assert b"CREDENTIALS_V4_BOOTSTRAP.md" in response.body


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
