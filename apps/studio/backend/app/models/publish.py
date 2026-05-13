"""Publish request and response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PublishSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"


class PublishResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    message: str
    artifact_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
