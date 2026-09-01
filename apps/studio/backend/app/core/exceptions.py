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
# caller-chosen message would defeat that: both routes below let a caller name a
# code AND supply the text, so `raise ValueError("STUDIO_INTERNAL_ERROR: <a path
# with a secret in it>")` would be recognized by the prefix protocol and echoed
# verbatim. It stays registered in the map above because that is where a code's
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


def error_response(
    *,
    error_code: str,
    http_status: int,
    message: str,
    retry_strategy: RetryStrategy,
    details: dict[str, Any] | None = None,
) -> ErrorResponse:
    """Build a validated Studio error response."""
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
    """The framework's answer for an exception no handler claimed."""
    definition = STANDARD_ERROR_MAP["STUDIO_INTERNAL_ERROR"]
    return error_response(
        error_code="STUDIO_INTERNAL_ERROR",
        http_status=definition.http_status,
        message=STUDIO_INTERNAL_ERROR_MESSAGE,
        details=None,
        retry_strategy=definition.retry_strategy,
    )


def _json_response(response: ErrorResponse) -> JSONResponse:
    """Project an envelope, replacing a reserved code's outright.

    Blocking the two code-SELECTION routes is not enough on its own: a caller
    can also hand-build an envelope with `error_response(...)` and raise it, or
    raise an `HTTPException` whose detail is already a full envelope, and both
    arrive here.

    The whole envelope is replaced, not just `message`. Normalizing one field
    would leave the others forgeable, and every one of them matters: an
    `STUDIO_INTERNAL_ERROR` carrying `http_status=200` is read as SUCCESS by axios,
    `details` is rendered verbatim by the frontend's diagnostic view, and
    `retry_strategy` tells the caller whether repeating a half-applied write is
    safe. A code that only the framework may answer with only ever carries the
    framework's own answer.

    This is the exit for every envelope BUILT IN THIS MODULE. It is not a
    whole-app choke point, and two things sit outside it: the loopback branch of
    `http_exception_handler` below, whose payload is a different shape entirely,
    and any router that returns its own `JSONResponse` — which is outside every
    guarantee this module makes, not just this one.
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


async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    standard_response = _standard_error_from_value_error(exc)
    if standard_response is not None:
        return _json_response(standard_response)

    response = error_response(
        error_code="MANIFEST_VALIDATION_FAILED",
        http_status=422,
        message=str(exc),
        details=None,
        retry_strategy="not_retryable",
    )
    return _json_response(response)


def _standard_error_from_value_error(exc: ValueError) -> ErrorResponse | None:
    text = str(exc)
    raw_code, separator, raw_message = text.partition(":")
    error_code = raw_code.strip()
    definition = _caller_selectable(error_code)
    if definition is None:
        return None

    return error_response(
        error_code=error_code,
        http_status=definition.http_status,
        message=raw_message.strip() if separator else _default_standard_error_message(error_code),
        details=_standard_error_details(error_code),
        retry_strategy=definition.retry_strategy,
    )


def _standard_error_details(error_code: str) -> dict[str, Any] | None:
    if error_code == "LLM_CREDENTIALS_SCHEMA":
        return {"docs_path": "docs/development/CREDENTIALS_V4_BOOTSTRAP.md"}
    return None


def _default_standard_error_message(error_code: str) -> str:
    return error_code.lower().replace("_", " ").capitalize()


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
    app.add_exception_handler(ValueError, cast(ExceptionHandler, value_error_handler))
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
