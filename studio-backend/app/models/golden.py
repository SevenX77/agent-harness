"""Golden baseline models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GoldenBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    linked_input_id: str
    created_at: datetime
    locked: bool
    content_path: str


class SetGoldenReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    lock: bool
