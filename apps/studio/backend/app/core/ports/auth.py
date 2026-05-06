"""Authentication port for Studio backend callers."""

from __future__ import annotations

from typing import Protocol

from fastapi import Request


class AuthProvider(Protocol):
    """Resolve the current Studio user from an incoming request."""

    async def get_current_user_id(self, request: Request) -> str:
        """Return the authenticated user id for the request."""
        ...
