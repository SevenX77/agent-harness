"""Test input metadata models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TestInputMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    created_at: datetime
    size_bytes: int
    content_preview: str


class TestInputCreateRequest(BaseModel):
    """Payload to save a named test input (the JSON fed to Predict/Run)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    content: dict[str, object]


class TestInputDetail(BaseModel):
    """A test input plus its full JSON content (for Predict/Run input selection)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    content: dict[str, object]
