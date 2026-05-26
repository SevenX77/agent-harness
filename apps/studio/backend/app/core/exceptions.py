"""Structured API error handling for Studio backend."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, NoReturn, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from graph_agent.core.exceptions import SkillCompileError
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
    "TERMINAL_SPAWN_FAILED": ErrorDefinition(http_status=500, retry_strategy="idempotent"),
    "TERMINAL_LIMIT_REACHED": ErrorDefinition(http_status=503, retry_strategy="backoff"),
    "WEBSOCKET_DISCONNECTED": ErrorDefinition(http_status=499, retry_strategy="backoff"),
    "LLM_FALLBACK_EXHAUSTED": ErrorDefinition(http_status=502, retry_strategy="backoff"),
    "LLM_CREDENTIALS_SCHEMA": ErrorDefinition(http_status=422, retry_strategy="not_retryable"),
    "RESUME_CHECKPOINT_NOT_FOUND": ErrorDefinition(
        http_status=404,
        retry_strategy="not_retryable",
    ),
}


class StudioHTTPException(HTTPException):
    """HTTPException carrying a Studio error code and retry strategy."""

    def __init__(
        self,
        *,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        definition = STANDARD_ERROR_MAP[error_code]
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


def _json_response(response: ErrorResponse) -> JSONResponse:
    return JSONResponse(status_code=response.http_status, content=response.model_dump())


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize HTTPException detail payloads into ErrorResponse."""
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
    if error_code not in STANDARD_ERROR_MAP:
        return None

    definition = STANDARD_ERROR_MAP[error_code]
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


async def skill_compile_error_handler(_request: Request, exc: SkillCompileError) -> JSONResponse:
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
        SkillCompileError,
        cast(ExceptionHandler, skill_compile_error_handler),
    )
