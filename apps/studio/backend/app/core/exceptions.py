"""Structured API error handling for Studio backend."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, NoReturn, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from graph_agent import GraphCompileError
from pydantic import ValidationError

from app.models.errors import ErrorResponse

RetryStrategy = Literal["idempotent", "not_retryable", "backoff"]
ExceptionHandler = Callable[[Request, Exception], JSONResponse | Awaitable[JSONResponse]]


@dataclass(frozen=True)
class ErrorDefinition:
    """HTTP projection for a stable Studio error code."""

    http_status: int
    retry_strategy: RetryStrategy


STANDARD_ERROR_MAP: dict[str, ErrorDefinition] = {
    "SKILL_NOT_FOUND": ErrorDefinition(http_status=404, retry_strategy="not_retryable"),
    "SKILL_ALREADY_EXISTS": ErrorDefinition(http_status=409, retry_strategy="not_retryable"),
    "MANIFEST_VALIDATION_FAILED": ErrorDefinition(
        http_status=422,
        retry_strategy="not_retryable",
    ),
    "COMPILE_FAILED": ErrorDefinition(http_status=200, retry_strategy="not_retryable"),
    "RUN_SPAWN_FAILED": ErrorDefinition(http_status=500, retry_strategy="idempotent"),
    "RUN_REQUIRES_PREDICT": ErrorDefinition(http_status=409, retry_strategy="not_retryable"),
    "RUN_NOT_RUNNING": ErrorDefinition(http_status=409, retry_strategy="not_retryable"),
    # The mirror of RUN_NOT_RUNNING: asked to project a run that has not reached
    # a verdict yet. Not retryable for the same reason — the caller should wait
    # for the run to end and be told, not poll a run it is already watching.
    "RUN_NOT_CONCLUDED": ErrorDefinition(http_status=409, retry_strategy="not_retryable"),
    "TERMINAL_SPAWN_FAILED": ErrorDefinition(http_status=500, retry_strategy="idempotent"),
    "TERMINAL_LIMIT_REACHED": ErrorDefinition(http_status=503, retry_strategy="backoff"),
    "WEBSOCKET_DISCONNECTED": ErrorDefinition(http_status=499, retry_strategy="backoff"),
    "LLM_FALLBACK_EXHAUSTED": ErrorDefinition(http_status=502, retry_strategy="backoff"),
    "LLM_CREDENTIALS_SCHEMA": ErrorDefinition(http_status=422, retry_strategy="not_retryable"),
    "RESUME_CHECKPOINT_NOT_FOUND": ErrorDefinition(
        http_status=404,
        retry_strategy="not_retryable",
    ),
    "RESUME_VALIDITY_FAILED": ErrorDefinition(
        http_status=422,
        retry_strategy="not_retryable",
    ),
    "TEST_INPUT_NOT_FOUND": ErrorDefinition(http_status=404, retry_strategy="not_retryable"),
    "TEST_INPUT_ALREADY_EXISTS": ErrorDefinition(http_status=409, retry_strategy="not_retryable"),
    "TEST_INPUT_VALIDATION_FAILED": ErrorDefinition(http_status=422, retry_strategy="not_retryable"),
    "SUBGRAPH_PATH_INVALID": ErrorDefinition(http_status=422, retry_strategy="not_retryable"),
    "SUBGRAPH_PATH_NOT_FOUND": ErrorDefinition(http_status=404, retry_strategy="not_retryable"),
    # The answer when NO other code applies: an exception no handler claimed.
    #
    # `not_retryable` rather than the `idempotent` the other 500s carry — those
    # two name a specific, side-effect-free spawn failure that is safe to repeat,
    # whereas an unclaimed exception is a defect at an unknown point in an
    # unknown endpoint. We cannot promise the request had no partial effect, and
    # repeating it re-runs the same defect, so the honest label is "do not retry".
    #
    # Alone in this map it carries a `STUDIO_` prefix, and the reason is that
    # every other name here is already unmistakably ours. The frontend resolves a
    # code's reader-facing sentence out of the `codes.*` table in
    # `locales/*/errors.json`, and that table is shared with the translator for
    # codes a remote LLM PROVIDER returned. A bare `INTERNAL_ERROR` is a string a
    # vendor plausibly emits, and the shared table would then answer a provider
    # outage with "the backend failed" — blaming the wrong machine. `SKILL_NOT_FOUND`
    # and its neighbours name things only Studio has, so they cannot collide.
    "STUDIO_INTERNAL_ERROR": ErrorDefinition(http_status=500, retry_strategy="not_retryable"),
}

# The one code a CALLER may not select. `STUDIO_INTERNAL_ERROR` is the framework's
# answer for an exception nobody claimed, and its message is a fixed placeholder
# precisely so that internal detail reaches the log and not the UI. A
# caller-chosen message would defeat that: every route below lets a caller name a
# code AND supply the text, so a selectable `STUDIO_INTERNAL_ERROR` would be a way
# to put `<a path with a secret in it>` on screen under the one code whose whole
# point is that its message says nothing. It stays registered in the map above
# because that is where a code's
# HTTP projection is declared and where the exhaustive test over those
# projections looks (the map is NOT the whole of Studio's error-code vocabulary:
# `NOT_IMPLEMENTED` and `HTTP_ERROR` in this file, and `UNAUTHORIZED` /
# `INVALID_TOKEN` in the auth middleware, are live codes that never enter it).
# What must not contain it is the caller-facing VIEW of the map.
_FRAMEWORK_RESERVED_ERROR_CODES = frozenset({"STUDIO_INTERNAL_ERROR"})

# The only message STUDIO_INTERNAL_ERROR is ever allowed to carry, defined once
# here because two places need it: the middleware that produces it, and the
# projection below that enforces it.
STUDIO_INTERNAL_ERROR_MESSAGE = "Internal server error"


def _caller_selectable(error_code: str) -> ErrorDefinition | None:
    """Look the code up as callers see it: reserved codes are simply absent.

    Returning "absent" rather than a distinct refusal keeps both call sites on
    the behaviour they already have for a code that is not registered at all —
    there is no second failure mode to reason about.
    """
    if error_code in _FRAMEWORK_RESERVED_ERROR_CODES:
        return None
    return STANDARD_ERROR_MAP.get(error_code)


class StudioHTTPException(HTTPException):
    """HTTPException carrying a Studio error code and retry strategy."""

    def __init__(
        self,
        *,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        definition = _caller_selectable(error_code)
        if definition is None:
            raise KeyError(error_code)
        response = ErrorResponse(
            error_code=error_code,
            http_status=definition.http_status,
            message=message,
            details=details,
            retry_strategy=definition.retry_strategy,
        )
        super().__init__(status_code=definition.http_status, detail=response.model_dump())


class BoundaryValidationError(ValueError):
    """Input that failed validation at the boundary where it entered the backend.

    This type exists to separate two things a bare ``ValueError`` cannot tell
    apart. One is "what arrived is not valid input" — a request field, a path
    segment, or a config file on disk that the user edits — which the caller has
    to be told about in words, as a 422. The other is "this code reached a state
    it declared impossible", which is a defect: its text names internal paths and
    state, belongs in the server log, and must reach the UI as nothing but
    ``STUDIO_INTERNAL_ERROR``.

    There is deliberately NO global ``ValueError`` handler, so every
    ``ValueError`` that is not this class is the second kind by default and a
    raise site opts into the first kind explicitly. The handler that used to
    claim all of them answered 422 with ``str(exc)`` verbatim, which meant an
    invariant violation anywhere in the backend presented its own internal text
    as though the user had sent bad input, and never reached
    ``UnhandledExceptionEnvelopeMiddleware`` — so it got neither the fixed safe
    message nor the traceback the server logs for an unclaimed exception.

    Which sites qualify: the raise must be the FIRST check a value from outside
    the backend meets. A defence-in-depth guard on data Studio itself produced,
    an adapter or dependency-injection construction check, and a schema check on
    data bundled inside the app are all the second kind — a caller cannot act on
    them, and a 422 would blame a request that was in fact fine.

    Subclasses ``ValueError`` rather than ``Exception``, for two reasons that
    both predate this class: the read layer already tolerates a malformed config
    file with ``except ValueError`` in a dozen places, and Pydantic converts only
    ``ValueError`` and ``AssertionError`` raised inside a validator into a
    ``ValidationError``. The ancestry costs nothing, because handler lookup is by
    type: Starlette walks ``type(exc).__mro__`` and finds this class first.

    ``error_code`` is a keyword field and NOT a prefix on the message. Its
    predecessor parsed ``str(exc)`` for a ``"CODE: text"`` shape, which handed
    the HTTP status to the message text — a sentence that happened to open with a
    capitalized word and a colon selected a code, and any prefix that matched
    nothing fell through to a 422 echoing the raw text. An unregistered or
    framework-reserved code is refused here at construction, the same way
    :class:`StudioHTTPException` refuses one, so a malformed envelope cannot be
    built and then discovered on the way out.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "MANIFEST_VALIDATION_FAILED",
        details: dict[str, Any] | None = None,
    ) -> None:
        definition = _caller_selectable(error_code)
        if definition is None:
            raise KeyError(error_code)
        super().__init__(message)
        self.error_code = error_code
        self.http_status = definition.http_status
        self.retry_strategy = definition.retry_strategy
        self.details = details


def error_response(
    *,
    error_code: str,
    http_status: int,
    message: str,
    retry_strategy: RetryStrategy,
    details: dict[str, Any] | None = None,
) -> ErrorResponse:
    """Build a validated Studio error response.

    Refuses a framework-reserved code outright rather than letting one be built
    and normalized later. Projection-time normalization (`_json_response`) only
    covers envelopes that leave through this module's handlers; a router is free
    to `return error_response(...)` from an endpoint, and that response goes
    straight out. Blocking construction is the only version of the rule that does
    not depend on which exit the envelope happens to take.
    """
    if error_code in _FRAMEWORK_RESERVED_ERROR_CODES:
        raise ValueError(
            f"{error_code} is the framework's own answer for an unclaimed exception "
            "and cannot be constructed by a caller; let the exception propagate instead",
        )
    return _validated_error_response(
        error_code=error_code,
        http_status=http_status,
        message=message,
        retry_strategy=retry_strategy,
        details=details,
    )


def _validated_error_response(
    *,
    error_code: str,
    http_status: int,
    message: str,
    retry_strategy: RetryStrategy,
    details: dict[str, Any] | None = None,
) -> ErrorResponse:
    """The unchecked builder, for the framework's own reserved-code envelope."""
    return ErrorResponse(
        error_code=error_code,
        http_status=http_status,
        message=message,
        details=details,
        retry_strategy=retry_strategy,
    )


def standard_http_exception(
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> StudioHTTPException:
    """Create a HTTPException for one of the eight Studio standard error codes."""
    return StudioHTTPException(error_code=error_code, message=message, details=details)


def raise_error_response(response: ErrorResponse) -> NoReturn:
    """Raise a FastAPI HTTPException that preserves a validated ErrorResponse."""
    raise HTTPException(status_code=response.http_status, detail=response.model_dump())


def raise_not_implemented(feature: str) -> NoReturn:
    """Return the common response for deferred endpoints."""
    response = error_response(
        error_code="NOT_IMPLEMENTED",
        http_status=501,
        message=f"{feature} is not implemented in this Studio backend phase",
        details={"feature": feature},
        retry_strategy="not_retryable",
    )
    raise HTTPException(status_code=501, detail=response.model_dump())


def internal_error_response() -> ErrorResponse:
    """The framework's answer for an exception no handler claimed.

    The one producer of this envelope, and the reason `error_response` above
    refuses the code: there is exactly one place it can come from, so there is
    exactly one message and one status it can carry.
    """
    definition = STANDARD_ERROR_MAP["STUDIO_INTERNAL_ERROR"]
    return _validated_error_response(
        error_code="STUDIO_INTERNAL_ERROR",
        http_status=definition.http_status,
        message=STUDIO_INTERNAL_ERROR_MESSAGE,
        details=None,
        retry_strategy=definition.retry_strategy,
    )


def _json_response(response: ErrorResponse) -> JSONResponse:
    """Project an envelope, replacing a reserved code's outright.

    A backstop, not the boundary. The boundary is construction: the three ways to
    NAME a code — `StudioHTTPException`, `BoundaryValidationError`, and
    `error_response` — each refuse the reserved one, so a reserved envelope
    cannot legitimately exist outside `internal_error_response`. What reaches
    here with one anyway got there by hand-building an `ErrorResponse` or a raw
    dict, i.e. by going around the module rather than through it.

    Kept anyway, and the whole envelope is replaced rather than just `message`,
    because every field decides something: `http_status=200` is read as SUCCESS
    by axios, `details` is rendered verbatim by the frontend's diagnostic view,
    and `retry_strategy` tells the caller whether repeating a possibly
    half-applied write is safe. Normalizing one and not the others would be a
    rule that looks enforced and is not.

    What this cannot reach: the loopback branch of `http_exception_handler`
    below, whose payload is a different shape carrying ENGINE error codes, and
    any router that returns its own `JSONResponse`. Neither is a hole in the
    reserved-code rule now that construction is blocked — both would require
    hand-writing the payload.
    """
    if response.error_code in _FRAMEWORK_RESERVED_ERROR_CODES:
        response = internal_error_response()
    return JSONResponse(status_code=response.http_status, content=response.model_dump())


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize HTTPException detail payloads into ErrorResponse."""
    if isinstance(exc.detail, dict) and {"schema_version", "ok", "error_code", "error_payload"}.issubset(
        exc.detail,
    ):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    if isinstance(exc.detail, dict) and {"error_code", "http_status", "message"}.issubset(
        exc.detail,
    ):
        return _json_response(ErrorResponse.model_validate(exc.detail))

    response = error_response(
        error_code="HTTP_ERROR",
        http_status=exc.status_code,
        message=str(exc.detail),
        details=None,
        retry_strategy="not_retryable",
    )
    return _json_response(response)


async def boundary_validation_error_handler(
    _request: Request,
    exc: BoundaryValidationError,
) -> JSONResponse:
    """Project a boundary rejection, message included.

    The message is safe to send BY CONSTRUCTION rather than by inspection: the
    only way to reach this handler is to raise the class above, and the class is
    documented as the one a raise site picks when it has something the caller
    needs to read. Nothing here parses, filters or guesses at the text.
    """
    return _json_response(
        error_response(
            error_code=exc.error_code,
            http_status=exc.http_status,
            message=str(exc),
            details=exc.details,
            retry_strategy=exc.retry_strategy,
        ),
    )


async def file_not_found_handler(_request: Request, exc: FileNotFoundError) -> JSONResponse:
    response = error_response(
        error_code="SKILL_NOT_FOUND",
        http_status=404,
        message=str(exc),
        details=None,
        retry_strategy="not_retryable",
    )
    return _json_response(response)


async def validation_error_handler(_request: Request, exc: ValidationError) -> JSONResponse:
    response = error_response(
        error_code="MANIFEST_VALIDATION_FAILED",
        http_status=422,
        message="Manifest validation failed",
        details={"errors": jsonable_encoder(exc.errors())},
        retry_strategy="not_retryable",
    )
    return _json_response(response)


async def request_validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    response = error_response(
        error_code="MANIFEST_VALIDATION_FAILED",
        http_status=422,
        message="Request validation failed",
        details={"errors": jsonable_encoder(exc.errors())},
        retry_strategy="not_retryable",
    )
    return _json_response(response)


async def skill_compile_error_handler(_request: Request, exc: GraphCompileError) -> JSONResponse:
    definition = STANDARD_ERROR_MAP["COMPILE_FAILED"]
    response = error_response(
        error_code="COMPILE_FAILED",
        http_status=definition.http_status,
        message=str(exc),
        details={"context": jsonable_encoder(exc.context)},
        retry_strategy=definition.retry_strategy,
    )
    return _json_response(response)


def register_exception_handlers(app: FastAPI) -> None:
    """Install all Studio exception handlers on a FastAPI app."""
    app.add_exception_handler(HTTPException, cast(ExceptionHandler, http_exception_handler))
    app.add_exception_handler(
        BoundaryValidationError,
        cast(ExceptionHandler, boundary_validation_error_handler),
    )
    app.add_exception_handler(FileNotFoundError, cast(ExceptionHandler, file_not_found_handler))
    app.add_exception_handler(ValidationError, cast(ExceptionHandler, validation_error_handler))
    app.add_exception_handler(
        RequestValidationError,
        cast(ExceptionHandler, request_validation_error_handler),
    )
    app.add_exception_handler(
        GraphCompileError,
        cast(ExceptionHandler, skill_compile_error_handler),
    )
