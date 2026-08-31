"""FastAPI middleware registration."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import CORS_ORIGINS
from app.core.exceptions import internal_error_response

logger = logging.getLogger(__name__)


def configure_cors(app: FastAPI) -> None:
    """Allow local Studio frontends to call the backend during development."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class UnhandledExceptionEnvelopeMiddleware:
    """Answer an exception no handler claimed with the standard error envelope.

    Starlette already has a last-resort handler — ``ServerErrorMiddleware``,
    installed automatically at the very OUTSIDE of the stack. That position is
    exactly the problem: it wraps every user middleware, ``CORSMiddleware``
    included, so nothing it emits can ever carry ``Access-Control-Allow-Origin``,
    and its body is ``text/plain`` "Internal Server Error" rather than the
    ``ErrorResponse`` envelope every Studio surface reads.

    Under the desktop app that missing header is not cosmetic. The webview is
    served from ``tauri://localhost`` / ``http://tauri.localhost`` while the
    sidecar answers on ``http://127.0.0.1:{port}``, so EVERY API call is
    cross-origin. A CORS-less 500 is discarded by the browser before axios can
    read it; the frontend sees only a network error, concludes the sidecar
    process is gone, and RuntimeGate's auto-restart kills a perfectly healthy
    sidecar — rotating its token and port and dropping whatever was in flight.
    One uncaught server-side bug thereby presents as a whole-backend outage.

    Registering ``app.add_exception_handler(Exception, ...)`` does NOT fix this:
    Starlette routes that particular handler into ``ServerErrorMiddleware``, so
    the response is still produced outside the CORS layer. Being real middleware
    placed INSIDE ``CORSMiddleware`` is the only position from which the reply
    gets the header.

    *Borrowed* from ``ServerErrorMiddleware`` itself: the ``response_started``
    flag threaded through a wrapped ``send``, because once response headers are
    on the wire an envelope can no longer be substituted for them.
    *Rejected*: its unconditional ``raise exc`` re-raise. It re-raises so the
    server still logs the traceback; we log it here instead, and swallowing is
    what keeps the connection answering a readable 500 rather than aborting.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception(
                "Unhandled exception serving %s %s",
                scope.get("method", "?"),
                scope.get("path", "?"),
            )
            if response_started:
                # Headers are already on the wire; there is no envelope to send
                # any more. Propagate so the server tears the connection down
                # instead of appending a second, contradictory body.
                raise
            # Fixed text, never the exception's own: what went wrong is a
            # server-side fact for the log, and the UI is a remote surface that
            # must not be handed stack or internal-state detail.
            envelope = internal_error_response()
            response = JSONResponse(
                status_code=envelope.http_status,
                content=envelope.model_dump(),
            )
            await response(scope, receive, send)


def configure_unhandled_exception_envelope(app: FastAPI) -> None:
    """Install the envelope middleware.

    Call this BEFORE :func:`configure_cors`. ``add_middleware`` prepends, so the
    LAST registration ends up outermost: registering here first and CORS second
    puts CORS outside, which is precisely what lets it decorate this
    middleware's 500 with the origin header.
    """
    app.add_middleware(UnhandledExceptionEnvelopeMiddleware)
