"""Git local history API models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

GitHistoryKind = Literal["auto_run", "manual", "other", "release"]
GitHistorySource = Literal["git", "manifest"]


class GitHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str
    message: str
    author: str
    timestamp: datetime
    kind: GitHistoryKind
    source: GitHistorySource = "git"
    revertable: bool = True
    release_version: str | None = None
    artifact_id: str | None = None
    content_hash: str | None = None
    manifest_ref: str | None = None


class RevertSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str
