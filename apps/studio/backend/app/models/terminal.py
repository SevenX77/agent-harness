"""Terminal session models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TerminalSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: str
    ws_url: str
    cwd: str
    ttl_seconds: int
