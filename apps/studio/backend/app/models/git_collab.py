"""Git collaboration API request models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SyncSkillReq(BaseModel):
    """Request body for skill L2 collaboration sync actions."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["save_to_team", "sync_from_team", "submit_for_review"]
    branch: str = "main"
    dev_branch: str | None = None
    pr_title: str | None = None
