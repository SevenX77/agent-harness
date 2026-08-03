"""Runtime-config request contracts shared by every writer of that config.

The output-artifact declaration had exactly one writer — the I/O panel's HTTP
route — so a CLI session that needed to declare a run product had no way in and
had to stop and ask a human to click (exp-b-round3, 2026-08-03). Giving copilot
its own tool means two callers, and two callers must not carry two schemas: the
shape lives here so the panel route and the MCP tool validate identically.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RuntimeArtifact(BaseModel):
    """One declared run product.

    The engine writes `<stem>_latest_<timestamp>.<ext>` into the run's
    `artifacts/` directory, carrying the blackboard fields named here.
    """

    stem: str
    mode: Literal["single", "per-item"] = "single"
    format: Literal["json", "md"] = "json"
    fields: list[str] = Field(default_factory=list)


class RuntimeArtifactsRequest(BaseModel):
    artifacts: list[RuntimeArtifact] = Field(default_factory=list)
