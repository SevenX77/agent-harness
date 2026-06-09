"""Git local history API models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

GitHistoryKind = Literal["auto_run", "manual", "other", "publish"]


class GitHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str
    message: str
    author: str
    timestamp: datetime
    kind: GitHistoryKind


class RevertSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str
