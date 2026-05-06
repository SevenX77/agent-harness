"""Local no-auth adapter for Studio development."""

from __future__ import annotations

from fastapi import Request


class NoAuthProvider:
    """Auth adapter that always returns the configured default user."""

    def __init__(self, default_user_id: str = "default") -> None:
        self._default_user_id = default_user_id

    async def get_current_user_id(self, request: Request) -> str:
        """Return the default local user id."""
        del request
        return self._default_user_id
