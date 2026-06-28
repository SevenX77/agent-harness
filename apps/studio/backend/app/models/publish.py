"""Publish request and response models."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MARKER_SAFE_RELEASE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


class PublishSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"

    @field_validator("version")
    @classmethod
    def validate_marker_safe_version(cls, value: str) -> str:
        if not _MARKER_SAFE_RELEASE_VERSION.fullmatch(value):
            raise ValueError(
                "version must be non-empty and contain only letters, numbers, '.', '_', '+', or '-'"
            )
        return value


class PublishResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    message: str
    artifact_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
