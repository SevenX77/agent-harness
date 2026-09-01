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

    *Borrowed* from ``ServerErrorMiddleware``, including the part that first
    looked wrong: the ``response_started`` flag threaded through a wrapped
    ``send``, AND the unconditional re-raise afterwards. Sending and re-raising
    are not alternatives — the response is already flushed by then, and the
    layer above sees ``response_started`` and does not try to overwrite it. So
    the caller still gets this readable, CORS-carrying 500 while the exception
    still reaches the server.

    Re-raising is not optional here. Swallowing also swallows the fail-fast that
    ``TestClient(raise_server_exceptions=True)`` gives the whole test suite: a
    route that starts crashing would answer a tidy 500 and every test that does
    not explicitly assert a status code would keep passing. Tests that mean to
    inspect this envelope opt out per-client with
    ``raise_server_exceptions=False``, which is how the suite already reads
    error responses elsewhere.
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
            # No traceback here on purpose. The re-raise below hands the
            # exception to the server, which logs the full stack itself
            # (uvicorn: "Exception in ASGI application"); `logger.exception`
            # would print a second identical copy of it. What that copy would
            # NOT contain is which request it was, so this line contributes
            # exactly that and stops.
            logger.error(
                "Unhandled exception serving %s %s",
                scope.get("method", "?"),
                scope.get("path", "?"),
            )
            if not response_started:
                # Fixed text, never the exception's own: what went wrong is a
                # server-side fact for the log, and the UI is a remote surface
                # that must not be handed stack or internal-state detail.
                envelope = internal_error_response()
                response = JSONResponse(
                    status_code=envelope.http_status,
                    content=envelope.model_dump(),
                )
                await response(scope, receive, send)
            # Always, whether or not an envelope went out: the caller has its
            # answer, and the exception must still surface to the server log and
            # to any test client that has not opted out of seeing it.
            raise


def configure_unhandled_exception_envelope(app: FastAPI) -> None:
    """Install the envelope middleware.

    Call this BEFORE :func:`configure_cors`. ``add_middleware`` prepends, so the
    LAST registration ends up outermost: registering here first and CORS second
    puts CORS outside, which is precisely what lets it decorate this
    middleware's 500 with the origin header.
    """
    app.add_middleware(UnhandledExceptionEnvelopeMiddleware)
