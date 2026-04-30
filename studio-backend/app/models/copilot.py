"""Copilot dispatch models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class CopilotDispatchReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["gemini", "claude_code"]
    context: dict[str, Any]


class CopilotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_text: str
