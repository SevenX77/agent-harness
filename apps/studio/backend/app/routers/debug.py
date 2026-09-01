"""The shipped app's one smoke endpoint for the unclaimed-exception envelope.

Kept out of the OpenAPI schema, but present in packaged builds on purpose: it is
the only way to ask a real installed sidecar for an error envelope — including
its CORS headers, which is the part that decides whether the desktop webview can
read a 500 at all — without mounting a route that does not ship.

It raises a bare ``ValueError`` because that is now an exception NO handler
claims, so the reply comes from ``UnhandledExceptionEnvelopeMiddleware``: a 500
``STUDIO_INTERNAL_ERROR`` whose message is fixed and whose text below never
appears in the response. While a global ``ValueError`` handler existed this
endpoint exercised that handler instead, and so covered every path except the
fallback one it was here to smoke-test.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/_debug", tags=["debug"], include_in_schema=False)


@router.get("/value-error")
async def raise_value_error() -> None:
    raise ValueError("Studio debug ValueError")
