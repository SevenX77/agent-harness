"""Golden baseline models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class GoldenBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    linked_input_id: str | None = None
    created_at: datetime
    locked: bool
    content_path: str
    node_id: str | None = None
    source: str | None = None


class SetGoldenReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    node_id: str | None = None
    expected_output: Any = None
    source: str | None = None
    lock: bool = False
